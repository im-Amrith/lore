"""Navigator: answers a question with a traced path, reaching the graph only through lore-mcp.

The 7-step loop (docs/PLAN.md "Navigator's loop"):
  1. classify the intent (keyword rules: cheap, repeatable, and only a hint to the LLM)
  2. resolve names to node ids: find_entities is always the first tool call
  3. the LLM picks the tool for the intent from the tools lore-mcp lists (MCP tool selection)
  4. it may expand with more tools, up to NAVIGATOR_MAX_TOOL_CALLS in total (find_entities included)
  5. it writes the answer as JSON sentences, each citing node ids; ids that no tool returned are
     dropped, and a sentence left with no valid id is never shown
  6. return the answer, the subgraph (node and edge ids) and the Cypher every tool ran
  7. store the question, answer and CITED edges with the remember tool

The MCP session is a real client over stdio (python -m lore.mcp_server), so every tool call the
answer depends on is a call the server logged. Tests may pass an in-process Client instead.
`org` and `user_id` are hidden from the LLM and filled in by code, so a question can't read
another org's graph or another user's memory.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from typing import Any

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from lore.config import BACKEND_DIR, NAVIGATOR_MAX_TOOL_CALLS
from lore.llm.agent import agent_chat, flatten

# Tools the LLM may choose. remember (step 7) is called by code; post_triage belongs to Steward.
AGENT_TOOLS = ("find_entities", "trace_decision", "find_experts", "module_owners", "knowledge_risk",
               "related_work", "impact_radius", "recall")
HIDDEN_ARGS = ("org", "user_id")

# Step 1. Checked in order; the first rule with a matching phrase wins.
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("changed", ("what changed", "since i last", "since last time", "what did i ask")),
    ("impact", ("what else", "impact", "if we change", "if i change", "break if", "ripple")),
    ("risk", ("single person", "one person", "bus factor", "depend on", "knowledge risk", "who would we lose")),
    ("owns", ("own", "codeowners", "responsible for")),
    ("who-knows", ("who knows", "who should i ask", "who to ask", "expert", "who works", "who wrote")),
    ("onboarding", ("new to", "onboard", "get started", "where do i start", "where should i start")),
    ("why", ("why", "reason", "decided", "decision", "rationale")),
]
INTENT_TOOL = {"why": "trace_decision", "who-knows": "find_experts", "owns": "module_owners",
               "risk": "knowledge_risk", "impact": "impact_radius", "changed": "recall",
               "onboarding": "find_experts", "general": "trace_decision"}

SYSTEM = """You are Lore's Navigator. You answer questions about the history of the {org} GitHub org
using only lore-mcp tool results. The org and the user id are filled in for you; never pass them.

How to work:
- find_entities has already run for this question (result below). Use the ids it returned.
- The intent looks like "{intent}"; the usual tool is {tool}.
  why: trace_decision with the best matching decision id, or the PR / issue it was decided in.
  who-knows: find_experts with a module path (e.g. graph/src/index) or a topic name.
  owns: module_owners (it also lists the active experts). risk: knowledge_risk.
  impact: impact_radius. What changed / my past questions: recall.
- If the result doesn't answer the question, you may call another tool. At most {left} more tool calls.
- When the results are enough (or nothing more can help), stop calling tools and reply: done.

{rules}"""

ANSWER_RULES = """Answer rules:
- Use only facts in the tool results. Never add outside knowledge.
- Every sentence cites one or more ids copied exactly from the tool results (decision:..., pr:...,
  issue:..., person:..., module:..., doc:..., chunk:..., team:..., commit:..., or "codeowners").
  Put ids only in cites, never in the sentence text; in text say "PR #2678", "issue #1", a login.
- For why questions give the reason (rationale), what problem it fixed (the issues), rejected
  alternatives if any, and who proposed and who approved it.
- `decisions` are current. A `pending_proposals` entry is never current: say "a draft PR proposes
  changing this; it is not merged". `history` is superseded: say so and say what replaced it.
  A decision with "parity": true was chosen to match the C engine (or openCypher): say so.
- Name people by login (and name when given). Quote scores and shares as given, rounded.
- For owns questions say whether CODEOWNERS lists an owner; if listed_owner is false, say
  "no owner is listed in CODEOWNERS", then who actually does the work.
- If no result answers the question (e.g. the matching PR has no recorded decision or reason),
  set found to false, say what is missing in not_found, and use sentences only for the nearest
  evidence (what the PR or issue did), never a guessed reason.
- 2 to 6 sentences."""

COMPOSE = """Write the final answer to the question now, as JSON: intent (why, who-knows, owns, risk,
impact, onboarding, changed or general), found, not_found ("" when found), and sentences, each
with its text and the ids it cites.

""" + ANSWER_RULES

# Step 5 is its own call: no tools, strict JSON schema. (gpt-oss on Groq loses a nested
# answer written as a tool call: the reply comes back empty.)
ANSWER_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["intent", "found", "not_found", "sentences"], "properties": {
                     "intent": {"type": "string"},
                     "found": {"type": "boolean"},
                     "not_found": {"type": "string"},
                     "sentences": {"type": "array", "items": {
                         "type": "object", "additionalProperties": False, "required": ["text", "cites"],
                         "properties": {"text": {"type": "string"},
                                        "cites": {"type": "array", "items": {"type": "string"}}}}}}}

# What the LLM sees of a tool result: results only (no cypher, node or edge lists), long strings
# cut, lists capped (tighter when nested), URLs replaced by node ids. impact_radius on the
# parser is ~60K characters raw and ~5K after this.
DROP_KEYS = {"source_url", "url", "rank", "distance", "activity", "confidence", "thresholds", "valid_from",
             "valid_to", "evidence_commits", "share_pct_raw"}
MAX_STR = 400
MAX_LIST = (10, 6, 3)  # by nesting depth of the list: top-level, inside one list, deeper

_URL_ID = [(re.compile(r"^https://github\.com/([^/]+/[^/]+)/pull/(\d+)$"), "pr:{}#{}"),
           (re.compile(r"^https://github\.com/([^/]+/[^/]+)/issues/(\d+)$"), "issue:{}#{}")]


def classify_intent(question: str) -> str:
    q = " " + question.lower() + " "
    for intent, phrases in INTENT_RULES:
        if any((" " + p) in q for p in phrases):
            return intent
    return "general"


def _url_to_id(s: str) -> str:
    for rx, fmt in _URL_ID:
        if m := rx.match(s):
            return fmt.format(*m.groups())
    return s


def compact(value: Any, depth: int = 0) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS or v is None or v == [] or v == "" or (k == "parity" and v is False):
                continue
            out[k] = compact(v, depth)
        return out
    if isinstance(value, list):
        cap = MAX_LIST[min(depth, len(MAX_LIST) - 1)]
        items = [compact(v, depth + 1) for v in value[:cap]]
        if len(value) > cap:
            items.append(f"... {len(value) - cap} more")
        return items
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, str):
        value = _url_to_id(value)
        return value if len(value) <= MAX_STR else value[:MAX_STR] + "..."
    return value


def server_params() -> StdioServerParameters:
    """lore-mcp as a subprocess, exactly as any MCP host would start it."""
    return StdioServerParameters(command=sys.executable, args=["-m", "lore.mcp_server"], cwd=str(BACKEND_DIR),
                                 env={**os.environ, "PYTHONPATH": str(BACKEND_DIR)})


def llm_tools(listed: Any) -> list[dict[str, Any]]:
    """MCP tool list -> OpenAI tool schemas, minus the args code fills in."""
    out = []
    for t in listed.tools:
        if t.name not in AGENT_TOOLS:
            continue
        schema = copy.deepcopy(t.input_schema)
        for k in HIDDEN_ARGS:
            schema.get("properties", {}).pop(k, None)
        schema["required"] = [r for r in schema.get("required", []) if r not in HIDDEN_ARGS]
        out.append({"type": "function",
                    "function": {"name": t.name, "description": t.description or "", "parameters": schema}})
    return out


def _parse_answer(content: str) -> dict[str, Any] | None:
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        out = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) and isinstance(out.get("sentences"), list) else None


class _Evidence:
    """Everything this question's tool calls returned: allowed citation ids, URLs, subgraph, Cypher."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.nodes: dict[str, None] = {}
        self.edges: dict[str, dict[str, str]] = {}
        self.sources: dict[str, str] = {}
        self.cypher: list[dict[str, Any]] = []
        self.first: dict[str, Any] = {}  # find_entities results, for the not-found fallback

    def add(self, tool: str, args: dict[str, Any], env: dict[str, Any] | None, error: str | None) -> None:
        self.calls.append({"tool": tool, "args": args, "error": error})
        if not env:
            return
        for n in env.get("nodes", []):
            self.nodes[n] = None
        for e in env.get("edges", []):
            self.edges[e["id"]] = e
            self.nodes.setdefault(e["source"])
            self.nodes.setdefault(e["target"])
        self.sources.update(env.get("sources", {}))
        self.cypher += [{"tool": tool, **c} for c in env.get("cypher", [])]
        if tool == "find_entities" and not self.first:
            self.first = env.get("results", {})

    def resolve(self, cite: str) -> str | None:
        """A cited id (or a URL the model copied) -> an id some tool returned, else None."""
        c = (cite or "").strip()
        if c in self.nodes or c in self.sources:
            return c
        c = _url_to_id(c)
        if c in self.nodes or c in self.sources:
            return c
        by_url = {u: k for k, u in self.sources.items()}
        return by_url.get(cite.strip())


async def _call(client: Client, ev: _Evidence, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """One lore-mcp call; returns what the LLM sees (compacted results or the error)."""
    r = await client.call_tool(tool, args)
    if r.is_error:
        err = " ".join(getattr(c, "text", "") for c in r.content) or "tool error"
        ev.add(tool, args, None, err)
        return {"error": err}
    env = r.structured_content or {}
    ev.add(tool, args, env, None)
    return compact(env.get("results", {}))


def _nearest(ev: _Evidence) -> list[dict[str, Any]]:
    """Not-found fallback: the top PR, issue and decision find_entities returned."""
    out = []
    for key, field in (("prs", "title"), ("issues", "title"), ("decisions", "statement")):
        for r in ev.first.get(key, [])[:1]:
            if r.get("id") in ev.nodes:
                out.append({"text": f"Nearest {key[:-1] if key != 'prs' else 'PR'}: {r.get(field)}",
                            "cites": [r["id"]]})
    return out


async def ask(question: str, org: str, user: str, client: Client, *, session_id: str | None = None,
              remember: bool = True, use_cache: bool = True, verbose: bool = False) -> dict[str, Any]:
    intent = classify_intent(question)
    tools = llm_tools(await client.list_tools())
    ev = _Evidence()
    log = print if verbose else (lambda *a, **k: None)

    # Step 2: resolve names. Shown to the LLM as its own first tool call.
    args = {"text": question}
    first = await _call(client, ev, "find_entities", {"org": org, **args})
    log(f"  [tool 1] find_entities {args}")
    used = 1
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM.format(org=org, intent=intent, tool=INTENT_TOOL[intent],
                                                    left=NAVIGATOR_MAX_TOOL_CALLS - 1, rules=ANSWER_RULES)},
        {"role": "user", "content": question},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function", "function": {"name": "find_entities", "arguments": json.dumps(args)}}]},
        {"role": "tool", "tool_call_id": "call_0", "content": json.dumps(first, default=str)},
    ]

    # Steps 3-4: the LLM picks tools until it stops asking or the budget is spent.
    model = ""
    while used < NAVIGATOR_MAX_TOOL_CALLS:
        reply = agent_chat(messages, tools, use_cache=use_cache)
        model = reply["model"]
        if not reply["tool_calls"]:
            break
        messages.append({"role": "assistant", "content": reply["content"], "tool_calls": [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
            for tc in reply["tool_calls"]]})
        for tc in reply["tool_calls"]:
            if used >= NAVIGATOR_MAX_TOOL_CALLS:
                result: dict[str, Any] = {"error": f"skipped: at most {NAVIGATOR_MAX_TOOL_CALLS} tool calls per question"}
            elif tc["name"] not in AGENT_TOOLS:
                result = {"error": f"unknown tool {tc['name']}"}
            else:
                try:
                    targs = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    targs = None
                if not isinstance(targs, dict):
                    result = {"error": "arguments are not a JSON object"}
                else:
                    targs = {k: v for k, v in targs.items() if k not in HIDDEN_ARGS}
                    full = {**targs, "org": org, **({"user_id": user} if tc["name"] == "recall" else {})}
                    used += 1
                    log(f"  [tool {used}] {tc['name']} {targs}")
                    result = await _call(client, ev, tc["name"], full)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, default=str)})

    # Step 5: compose from the tool results (no tools offered), then keep only cites a tool returned.
    compose = [{"role": "system", "content": COMPOSE}, *flatten(messages[1:])]
    reply = agent_chat(compose, json_schema=ANSWER_SCHEMA, use_cache=use_cache)
    model = model or reply["model"]
    parsed = _parse_answer(reply["content"]) or {
        "sentences": [], "found": False, "not_found": "the model returned no readable answer"}
    sentences, dropped = [], []
    for s in parsed.get("sentences", []):
        if not isinstance(s, dict) or not str(s.get("text", "")).strip():
            continue
        raw = [c for c in (s.get("cites") or []) if isinstance(c, str)]
        good = list(dict.fromkeys(r for c in raw if (r := ev.resolve(c))))
        bad = [c for c in raw if not ev.resolve(c)]
        if good:
            sentences.append({"text": s["text"].strip(), "cites": good, **({"rejected_cites": bad} if bad else {})})
        else:
            dropped.append({"text": s["text"].strip(), "cites": raw})
    found = bool(parsed.get("found", True)) and bool(sentences)
    not_found = str(parsed.get("not_found") or "").strip()
    if not found and not sentences:
        sentences = _nearest(ev)
    if not found and not not_found:
        not_found = "no tool result answers this question"

    # Step 6: citations, rendered text, subgraph, path (edges touching a cited node), Cypher.
    cited: list[str] = list(dict.fromkeys(c for s in sentences for c in s["cites"]))
    number = {c: i + 1 for i, c in enumerate(cited)}
    citations = [{"n": number[c], "id": c, "url": ev.sources.get(c)} for c in cited]
    body = " ".join(f"{s['text']} {''.join(f'[{number[c]}]' for c in s['cites'])}" for s in sentences)
    text = (f"Not found: {not_found}." + (f" Nearest evidence: {body}" if body else "")) if not found else body
    cited_set = set(cited)
    path = [e for e in ev.edges.values() if e["source"] in cited_set or e["target"] in cited_set]

    out: dict[str, Any] = {
        "question": question, "org": org, "user": user, "intent": parsed.get("intent") or intent,
        "intent_rule": intent, "found": found, "not_found": not_found if not found else "",
        "answer": text, "sentences": sentences, "dropped": dropped, "citations": citations,
        "subgraph": {"nodes": list(ev.nodes), "edges": list(ev.edges.values())}, "path": path,
        "sources": ev.sources, "cypher": ev.cypher, "tool_calls": ev.calls, "model": model, "session_id": session_id,
    }

    # Step 7: memory, through MCP like every other graph access.
    if remember:
        r = await client.call_tool("remember", {
            "org": org, "user_id": user, "question": question, "answer": text, "cited_ids": cited,
            "cypher": "\n\n".join(f"// {c['query']}\n{c['cypher']}" for c in ev.cypher),
            "intent": out["intent"], **({"session_id": session_id} if session_id else {})})
        if not r.is_error and r.structured_content:
            res = r.structured_content["results"]
            out["session_id"] = res["session_id"]
            out["memory"] = {k: res[k] for k in ("question_id", "answer_id", "cited")}
    return out


def ask_sync(question: str, org: str, user: str, **kwargs: Any) -> dict[str, Any]:
    """ask() with its own lore-mcp session (one subprocess per call)."""
    async def run() -> dict[str, Any]:
        async with Client(server_params()) as client:
            return await ask(question, org, user, client, **kwargs)
    return anyio.run(run)
