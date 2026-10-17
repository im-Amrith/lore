"""Navigator: answers a question with a traced path, reaching the graph only through lore-mcp.

The 7-step loop (docs/PLAN.md "Navigator's loop"):
  1. classify the intent (keyword rules: cheap, repeatable, and only a hint to the LLM)
  2. resolve names to node ids: find_entities is always the first tool call
  3. LLM call 1 picks the tools for the intent from the tools lore-mcp lists (MCP tool
     selection), several at once if it needs them; they all run
  4. only if every result came back empty does call 2 pick again (thin results); the budget is
     NAVIGATOR_MAX_TOOL_CALLS tool calls in total, find_entities included
  5. the next call writes the answer as JSON sentences, each citing node ids; ids that no tool
     returned are dropped, and a sentence left with no valid id is never shown
So a question usually costs two LLM calls, three when the first tools find nothing.
  6. return the answer, the subgraph (node and edge ids) and the Cypher every tool ran
  7. store the question, answer and CITED edges with the remember tool

The MCP session is a real client over stdio (python -m lore.mcp_server), so every tool call the
answer depends on is a call the server logged. Tests may pass an in-process Client instead.
`org` and `user_id` are hidden from the LLM and filled in by code, so a question can't read
another org's graph or another user's memory. trace_decision also gets the user's question,
verbatim, to rank the issues linked to a decision.

Answer cache: an answer is stored under the normalized question + org + the graph's data
version (the data_version tool, query 93) + a hash of the prompts and caps below, and reused
while all four hold. A hit still goes through remember, so memory sees every question.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Callable

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from lore.config import ANSWER_CACHE_DIR, BACKEND_DIR, NAVIGATOR_MAX_TOOL_CALLS
from lore.llm.agent import agent_chat, flatten

# Tools the LLM may choose. remember (step 7) is called by code; post_triage belongs to Steward.
AGENT_TOOLS = ("find_entities", "trace_decision", "find_experts", "module_owners", "knowledge_risk",
               "related_work", "impact_radius", "recall")
# question: trace_decision ranks linked issues by it. min_score (find_experts) is Steward's.
HIDDEN_ARGS = ("org", "user_id", "question", "min_score")

# Step 1. Checked in order; the first rule with a matching phrase wins.
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("triage", ("new issue", "related to this issue", "related past work", "this bug report")),
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
               "onboarding": "find_experts", "general": "trace_decision", "triage": "related_work"}

SYSTEM = """You are Lore's Navigator. You answer questions about the history of the {org} GitHub org
using only lore-mcp tool results. The org and the user id are filled in for you; never pass them.

How to work:
- find_entities has already run for this question (result below). Use the ids it returned.
- The intent looks like "{intent}"; the usual tool is {tool}.
  why: trace_decision with the best matching decision id, or the PR / issue it was decided in.
  who-knows: find_experts with a module path (e.g. graph/src/index) or a topic name.
  owns: module_owners (it also lists the active experts). risk: knowledge_risk.
  impact: impact_radius. triage (a new issue's text): related_work with that text.
  What changed / my past questions: recall.
- Call every tool the answer needs NOW, in this one turn: you may call several at once (at
  most {left}). You get another turn only if all of them come back empty. If find_entities
  already answers the question, call nothing.
- The answer is written in the next step and must cite ids from the results, so fetch the
  evidence it needs (experts' PRs, the decision's sources) rather than guessing.
- Tool results use short field names: stmt = decision statement, why = rationale, src = where
  it was decided, prs = evidence PRs, ids = person ids."""

ANSWER_RULES = """Answer rules:
- Use only facts in the tool results. Never add outside knowledge.
- Every sentence cites one or more ids copied exactly from the tool results (decision:..., pr:...,
  issue:..., person:..., module:..., doc:..., chunk:..., team:..., commit:..., or "codeowners").
  Put ids only in cites, never in the sentence text; in text say "PR #2678", "issue #1", a login.
- Cite the evidence the tools return: when you name an expert, also cite their evidence PRs
  (pr:... ids); whenever you mention CODEOWNERS (an owner listed or not), cite "codeowners".
- Name modules by their exact path as returned (graph/src/index), never a paraphrase ("the
  index module"). Keep the decision's own technical terms from its statement, rationale, quote
  and alternatives (e.g. "content-addressed cache", "delta"); don't swap them for synonyms.
- For why questions give the reason (rationale), what problem it fixed (the issues), rejected
  alternatives if any, and who proposed and who approved it.
- `decisions` are current. A `pending_proposals` entry is never current: say "a draft PR proposes
  changing this; it is not merged". `history` is superseded: say so and say what replaced it.
  A decision with "parity": true was chosen to match the C engine (or openCypher): say so.
- Why questions: the first sentence states the decision in the words of its statement (stmt),
  keeping its key terms (e.g. "native-deps crate", "content-addressed cache", "fold", "delta").
- Who, owns and risk questions: always write the exact module path (graph/src/index, analytics,
  storage) in the text, and name the people who actually do the work (the experts), including
  commit-only authors without a GitHub login (ids like person:name:priya-raman): write their
  name as given (Priya Raman). Name people with a login by login (and name when given). Quote
  scores and shares as given, rounded.
- Owns questions: say whether CODEOWNERS lists an owner; if listed_owner is false, say
  "no owner is listed in CODEOWNERS". Then say who actually does the work, and if the listed
  owner is not among the experts (paper owner), say so.
- Risk questions: for each single-expert module, write its path and name its single expert.
- If no result answers the question (e.g. the matching PR has no recorded decision or reason),
  set found to false, say what is missing in not_found, and use sentences only for the nearest
  evidence (what the PR or issue did), never a guessed reason.
- 2 to 6 sentences.

Tool results use short field names: stmt = decision statement, why = rationale, rejected =
alternatives considered, src = the PR / issue / doc it was decided in, prs = evidence PRs,
reviewed = PRs reviewed, share = % share, ids = person ids (same order as experts)."""

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

# What the LLM sees of a tool result (the full envelope still goes to the UI and the eval):
# results only (no Cypher, embeddings, node or edge lists), noise fields dropped, field names
# shortened, URLs replaced by node ids, strings cut, and lists capped by what they hold. Every
# call stays under ~4K tokens (impact_radius on the parser: ~60K characters raw).
DROP_KEYS = {"source_url", "url", "codeowners_url", "rank", "distance", "activity", "confidence", "thresholds",
             "valid_from", "valid_to", "evidence_commits", "last_touch", "authored", "kind", "members", "repo",
             "module_commits", "total_score", "other_matches", "since", "via", "rels", "links_back", "label",
             "number", "member_ids", "sources", "term", "doc_id", "would_change", "shared_topics",
             "shared_modules", "source_draft", "source_state", "embedding", "cypher", "nodes", "edges"}
RENAME = {"statement": "stmt", "rationale": "why", "alternatives": "rejected", "source_id": "src",
          "person_id": "id", "module_id": "id", "person": "who", "evidence": "prs",
          "evidence_reviews": "reviewed", "share_pct": "share", "expert_ids": "ids"}
LIST_CAPS = {"experts": 5, "active_experts": 5, "bridge_people": 5, "owners": 5, "people": 6,
             "evidence": 3, "evidence_reviews": 2, "issues": 3, "similar_issues": 5, "decisions": 4,
             "pending_proposals": 3, "history": 3, "co_changed": 5, "modules": 12, "working_groups": 3,
             "docs": 3, "prs": 4, "alternatives": 3, "questions": 5, "changes": 5}
# Inside a list item: the decisions under each co-changed module get 2; the issues linked to a
# traced decision keep the 6 query 03 ranked (top-level find_entities issues get 3).
NESTED_LIST_CAPS = {"decisions": 2, "pending_proposals": 2, "history": 2, "issues": 6}
DEFAULT_LIST_CAP = 6
MAX_STR = 300
STR_CAPS = {"snippet": 160, "title": 120}

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


def compact(value: Any, key: str = "", nested: bool = False) -> Any:
    """A tool result as the LLM sees it. key is the field holding value; nested is True inside
    a list item, where lists of decisions get NESTED_LIST_CAP instead of their own cap."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS or v is None or v == [] or v == "" or (k == "parity" and v is False):
                continue
            out[RENAME.get(k, k)] = compact(v, k, nested)
        return out
    if isinstance(value, list):
        cap = (nested and NESTED_LIST_CAPS.get(key)) or LIST_CAPS.get(key, DEFAULT_LIST_CAP)
        items = [compact(v, key, True) for v in value[:cap]]
        if len(value) > cap:
            items.append(f"+{len(value) - cap} more")
        return items
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, str):
        value = _url_to_id(value)
        cap = STR_CAPS.get(key, MAX_STR)
        return value if len(value) <= cap else value[:cap] + "..."
    return value


def server_params() -> StdioServerParameters:
    """lore-mcp as a subprocess, exactly as any MCP host would start it."""
    return StdioServerParameters(command=sys.executable, args=["-m", "lore.mcp_server"], cwd=str(BACKEND_DIR),
                                 env={**os.environ, "PYTHONPATH": str(BACKEND_DIR)})


def _slim(schema: Any) -> Any:
    """Drop pydantic's per-field titles and null defaults; anyOf [X, null] -> X. ~400 tokens a call."""
    if isinstance(schema, dict):
        if "anyOf" in schema:
            kinds = [k for k in schema["anyOf"] if k.get("type") != "null"]
            if len(kinds) == 1:
                schema = {**{k: v for k, v in schema.items() if k != "anyOf"}, **kinds[0]}
        return {k: _slim(v) for k, v in schema.items()
                if k != "title" and not (k == "default" and schema[k] is None)}
    if isinstance(schema, list):
        return [_slim(x) for x in schema]
    return schema


def llm_tools(listed: Any) -> list[dict[str, Any]]:
    """MCP tool list -> OpenAI tool schemas, minus the args code fills in."""
    out = []
    for t in listed.tools:
        if t.name not in AGENT_TOOLS:
            continue
        schema = _slim(copy.deepcopy(t.input_schema))
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
        self.labels: dict[str, str] = {}  # node id -> a short human label (title, statement, login, path)
        self.decision_status: dict[str, str] = {}  # decision id -> active / proposed / superseded
        self.pending: set[str] = set()  # proposed decisions and the open/draft PRs they come from

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
        self._walk(env.get("results", {}))

    LABEL_KEYS = ("title", "statement", "person", "login", "path", "module", "name")

    def _walk(self, value: Any) -> None:
        """Labels and decision statuses from anything in a tool result that carries an id."""
        if isinstance(value, dict):
            nid = value.get("id") or value.get("person_id") or value.get("module_id")
            if isinstance(nid, str) and ":" in nid:
                label = next((value[k] for k in self.LABEL_KEYS if isinstance(value.get(k), str) and value[k]), None)
                if label:
                    self.labels.setdefault(nid, label[:200])
                if nid.startswith("decision:") and value.get("status"):
                    self.decision_status[nid] = value["status"]
                    if value["status"] == "proposed":
                        self.pending.add(nid)
                        if value.get("source_id"):
                            self.pending.add(value["source_id"])
            for v in value.values():
                self._walk(v)
        elif isinstance(value, list):
            for v in value:
                self._walk(v)

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


def normalize_question(question: str) -> str:
    """Case, spacing and trailing punctuation don't make a different question."""
    return re.sub(r"\s+", " ", question.strip().lower()).rstrip(" ?.!")


# Any change to what the LLM is told or shown makes cached answers stale.
PROMPT_VERSION = hashlib.sha256(json.dumps(
    [SYSTEM, ANSWER_RULES, COMPOSE, ANSWER_SCHEMA, sorted(DROP_KEYS), RENAME, LIST_CAPS, NESTED_LIST_CAPS,
     STR_CAPS, MAX_STR, NAVIGATOR_MAX_TOOL_CALLS], sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def _cache_path(question: str, org: str, data_version: str):
    key = hashlib.sha256(json.dumps([normalize_question(question), org.lower(), data_version, PROMPT_VERSION])
                         .encode("utf-8")).hexdigest()
    return ANSWER_CACHE_DIR / key[:2] / f"{key}.json"


def _thin(result: dict[str, Any]) -> bool:
    """A tool result with nothing to answer from: an error, a not-found, or no data at all."""
    if not result or "error" in result or result.get("found") is False:
        return True
    if str(result.get("message", "")).startswith("not found"):
        return True
    return not any(isinstance(v, (list, dict)) and v for v in result.values())


async def _remember(client: Client, out: dict[str, Any], session_id: str | None) -> None:
    """Step 7, through MCP like every other graph access."""
    r = await client.call_tool("remember", {
        "org": out["org"], "user_id": out["user"], "question": out["question"], "answer": out["answer"],
        "cited_ids": [c["id"] for c in out["citations"]],
        "cypher": "\n\n".join(f"// {c['query']}\n{c['cypher']}" for c in out["cypher"]),
        "intent": out["intent"], **({"session_id": session_id} if session_id else {})})
    if not r.is_error and r.structured_content:
        res = r.structured_content["results"]
        out["session_id"] = res["session_id"]
        out["memory"] = {k: res[k] for k in ("question_id", "answer_id", "cited")}


async def ask(question: str, org: str, user: str, client: Client, *, session_id: str | None = None,
              remember: bool = True, use_cache: bool = True, verbose: bool = False,
              on_event: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """on_event gets progress as it happens (the API streams it to the UI): {"type": "tool",
    "n", "tool", "args"}, {"type": "llm", "step"}, {"type": "llm_done", "step", "endpoint",
    "seconds", "cached"}, {"type": "cache"} on an answer-cache hit."""
    started = time.monotonic()
    log = print if verbose else (lambda *a, **k: None)
    emit = on_event or (lambda e: None)

    # The answer cache, keyed on the graph's current data version.
    cache_file = None
    if use_cache:
        dv = await client.call_tool("data_version", {"org": org})
        if not dv.is_error and dv.structured_content:
            cache_file = _cache_path(question, org, dv.structured_content["results"]["version"])
            if cache_file.exists():
                out = {**json.loads(cache_file.read_text(encoding="utf-8")), "user": user,
                       "question": question, "session_id": session_id, "answer_cache": True}
                log(f"  [answer cache] hit {cache_file.name[:12]}")
                emit({"type": "cache"})
                if remember:
                    await _remember(client, out, session_id)
                out["seconds"] = round(time.monotonic() - started, 1)
                return out

    intent = classify_intent(question)
    tools = llm_tools(await client.list_tools())
    llm_calls: list[dict[str, Any]] = []

    async def chat(*args: Any, step: str = "", **kwargs: Any) -> dict[str, Any]:
        emit({"type": "llm", "step": step})
        # The OpenAI client blocks; a worker thread keeps the API's event loop free meanwhile.
        r = await anyio.to_thread.run_sync(lambda: agent_chat(*args, **kwargs))
        emit({"type": "llm_done", "step": step, "endpoint": r.get("endpoint"), "seconds": r.get("seconds"),
              "cached": bool(r.get("cached"))})
        llm_calls.append({k: r.get(k) for k in ("model", "endpoint", "prompt_tokens", "seconds", "cached")})
        return r
    ev = _Evidence()

    # Step 2: resolve names. Shown to the LLM as its own first tool call.
    args = {"text": question}
    emit({"type": "tool", "n": 1, "tool": "find_entities", "args": args})
    first = await _call(client, ev, "find_entities", {"org": org, **args})
    log(f"  [tool 1] find_entities {args}")
    used = 1
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM.format(org=org, intent=intent, tool=INTENT_TOOL[intent],
                                                    left=NAVIGATOR_MAX_TOOL_CALLS - 1)},
        {"role": "user", "content": question},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function", "function": {"name": "find_entities", "arguments": json.dumps(args)}}]},
        {"role": "tool", "tool_call_id": "call_0", "content": json.dumps(first, default=str)},
    ]

    async def run_calls(reply: dict[str, Any]) -> list[dict[str, Any]]:
        """Run every tool the LLM picked in one turn (within the budget); return their results."""
        nonlocal used
        messages.append({"role": "assistant", "content": reply["content"], "tool_calls": [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
            for tc in reply["tool_calls"]]})
        results = []
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
                    full = {**targs, "org": org, **({"user_id": user} if tc["name"] == "recall" else {}),
                            **({"question": question} if tc["name"] == "trace_decision" else {})}
                    used += 1
                    log(f"  [tool {used}] {tc['name']} {targs}")
                    emit({"type": "tool", "n": used, "tool": tc["name"], "args": targs})
                    result = await _call(client, ev, tc["name"], full)
            results.append(result)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, default=str)})
        return results

    # Step 3: call 1 picks every tool it needs, in one turn.
    model = ""
    reply = await chat(messages, tools, step="pick tools", use_cache=use_cache)
    model = reply["model"]
    if reply["tool_calls"]:
        results = await run_calls(reply)
        # Step 4: one more pick only when everything came back empty.
        if all(_thin(r) for r in results) and used < NAVIGATOR_MAX_TOOL_CALLS:
            messages.append({"role": "user", "content": "Those results are empty. Try other tools or arguments "
                                                        f"(at most {NAVIGATOR_MAX_TOOL_CALLS - used} calls), or call nothing."})
            reply = await chat(messages, tools, step="pick again", use_cache=use_cache)
            if reply["tool_calls"]:
                await run_calls(reply)

    # Step 5: compose from the tool results (no tools offered), then keep only cites a tool returned.
    compose = [{"role": "system", "content": COMPOSE}, *flatten(messages[1:])]
    reply = await chat(compose, json_schema=ANSWER_SCHEMA, step="write answer", use_cache=use_cache)
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
            sentences.append({"text": s["text"].strip(), "cites": good,
                              "pending": any(c in ev.pending for c in good),  # rests on an unmerged proposal
                              **({"rejected_cites": bad} if bad else {})})
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
        "sources": ev.sources, "cypher": ev.cypher, "tool_calls": ev.calls, "model": model,
        "llm_calls": llm_calls, "session_id": session_id,
        "labels": {n: ev.labels[n] for n in ev.nodes if n in ev.labels},
        "decision_status": ev.decision_status,
    }

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, default=str), encoding="utf-8")

    # Step 7: memory.
    if remember:
        await _remember(client, out, session_id)
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def ask_sync(question: str, org: str, user: str, **kwargs: Any) -> dict[str, Any]:
    """ask() with its own lore-mcp session (one subprocess per call)."""
    async def run() -> dict[str, Any]:
        async with Client(server_params()) as client:
            return await ask(question, org, user, client, **kwargs)
    return anyio.run(run)
