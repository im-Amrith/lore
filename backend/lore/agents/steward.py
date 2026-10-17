"""Steward: drafts a triage comment for each new sandbox issue, from the graph, for a human to approve.

The loop (docs/PLAN.md F5 and "Agents coordinate through the graph"):
  1. open_tasks lists the work board; claim_task takes one with the atomic claim query, so two
     workers (or the poll and the webhook) never draft the same issue
  2. related_work: similar past issues, the PRs that fixed them, the modules they touched, and
     the decisions on those modules
  3. module_owners on the main module (the fix's module, not tests/ or docs/): CODEOWNERS owners
     vs the people who do the work, with paper-owner flags
  4. find_experts on it with a low threshold: the reviewer candidates
  5. trace_decision on the decision made in the earlier fix: its rationale
  6. code picks the facts (related issues, owner, paper-owner warning, reviewer, links); the LLM
     only writes them up as a comment, following the Playbook's steps (get_playbook), including
     rules learned from earlier human edits
  7. links the draft makes up are stripped; save_draft stores the draft and its facts on the Task
     (status drafted). A failure releases the Task back to open with the reason.

Nothing is posted here: posting is post_triage, called only by the API's approve route with a token
minted by the human's click. Every graph access goes through lore-mcp (a Client session).

learn_rule() turns a human's edit of a draft into one Playbook rule (the API stores it as Feedback).
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from typing import Any

import anyio
from mcp.client import Client

from lore.config import (
    PLAYBOOK_NAME,
    RELATED_MAX_DISTANCE,
    REVIEWER_MIN_SCORE,
    STEWARD_MAX_ATTEMPTS,
    TRIAGE_SKIP_MODULES,
)
from lore.llm.agent import agent_chat
from lore.mcp_server.tools import id_from_url


class StewardError(RuntimeError):
    pass


def agent_name() -> str:
    """claimed_by on a Task: which worker took it."""
    return f"steward:{socket.gethostname()}:{os.getpid()}"


async def _tool(client: Client, name: str, args: dict[str, Any]) -> dict[str, Any]:
    r = await client.call_tool(name, args)
    if r.is_error:
        raise StewardError(f"{name}: " + (" ".join(getattr(c, "text", "") for c in r.content) or "tool error"))
    return r.structured_content or {}


# ---------------------------------------------------------------- picking the facts (no LLM)

def _short(node_id: str | None) -> str:
    """pr:<repo>#11 -> PR #11, issue:<repo>#3 -> #3."""
    if m := re.match(r"^(pr|issue):.+#(\d+)$", node_id or ""):
        return f"PR #{m.group(2)}" if m.group(1) == "pr" else f"#{m.group(2)}"
    return node_id or ""


def person(pid: str, label: str | None = None) -> dict[str, Any]:
    """A person as the comment names them: @login when they have a GitHub login, else their name
    (commit-only authors like person:name:priya-raman can't be @-mentioned)."""
    if pid.startswith("person:name:"):
        name = label or pid.removeprefix("person:name:").replace("-", " ").title()
        return {"id": pid, "name": name, "login": None, "mention": name}
    login = pid.removeprefix("person:")
    return {"id": pid, "name": label or login, "login": login, "mention": f"@{login}"}


def primary_module(modules: list[str]) -> str | None:
    """The module a bug most likely lives in: the first one the nearest fixes touched that isn't a
    test or doc folder (every fix touches tests/)."""
    for m in modules:
        if m.rsplit(":", 1)[-1] not in TRIAGE_SKIP_MODULES:
            return m
    return modules[0] if modules else None


def pick_related(similar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Similar issues worth naming: the nearest always, others within RELATED_MAX_DISTANCE."""
    out = []
    for i, s in enumerate(similar):
        if i == 0 or s["distance"] <= RELATED_MAX_DISTANCE:
            out.append({"id": s["id"], "number": s["number"], "title": s["title"], "url": s["url"],
                        "state": s["state"], "distance": round(s["distance"], 3),
                        "duplicate": bool(s.get("duplicate_candidate")),
                        "fixed_by": [{"id": id_from_url(u), "url": u} for u in s.get("fixes") or []]})
    return out


def pick_owner(owners: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(suggested owner, paper-owner warnings) from module_owners results. The owner is the top
    active expert (who does the work); a CODEOWNERS owner is only suggested when no one is active."""
    path = owners["module"]["path"]
    experts = owners.get("active_experts") or []
    listed = [o for o in owners.get("owners") or [] if o.get("kind") == "Person"]
    warnings = []
    for o in owners.get("owners") or []:
        if o.get("paper"):
            p = person(o["id"], o.get("name"))
            doer = person(experts[0]["id"], experts[0].get("person")) if experts else None
            warnings.append({**p, "text": f"CODEOWNERS lists {p['mention']} for {path}, but they have no "
                                          f"commits or reviews there in the last 12 months"
                                          + (f"; {doer['name']} does the work there" if doer else "")})
    if experts:
        top = experts[0]
        p = person(top["id"], top.get("person"))
        is_listed = any(o["id"] == top["id"] for o in owners.get("owners") or [])
        why = (f"listed in CODEOWNERS for {path} and its most active contributor" if is_listed
               else f"does the work on {path}" + (" (not listed in CODEOWNERS)" if owners.get("listed_owner") else ""))
        return ({**p, "why": why, "score": round(top.get("score") or 0, 2), "codeowner": is_listed,
                 "evidence": [{"id": id_from_url(u), "url": u} for u in top.get("evidence") or []]}, warnings)
    if listed:
        p = person(listed[0]["id"], listed[0].get("name"))
        return {**p, "why": f"listed in CODEOWNERS for {path} (no one has worked there recently)",
                "codeowner": True, "evidence": []}, warnings
    return None, warnings


def pick_reviewer(owner: dict[str, Any] | None, experts: list[dict[str, Any]],
                  owners: dict[str, Any]) -> dict[str, Any] | None:
    """Someone other than the owner: the next person by expertise (reviews count), else a
    CODEOWNERS owner, whose approval GitHub requires anyway."""
    path = owners["module"]["path"]
    skip = {owner["id"]} if owner else set()
    for e in experts:
        if e["person_id"] in skip:
            continue
        p = person(e["person_id"], e.get("person"))
        reviews = e.get("evidence_reviews") or []
        if reviews:
            why = f"reviewed {', '.join(_short(id_from_url(u)) for u in reviews[:2])} on {path}"
        else:
            why = f"has also worked on {path}"
        return {**p, "why": why, "evidence": [{"id": id_from_url(u), "url": u}
                                              for u in (reviews or e.get("evidence") or [])[:2]]}
    for o in owners.get("owners") or []:
        if o.get("kind") == "Person" and o["id"] not in skip:
            p = person(o["id"], o.get("name"))
            return {**p, "why": f"listed in CODEOWNERS for {path}, so GitHub asks for their approval",
                    "evidence": []}
    return None


def pick_decision(related: list[dict[str, Any]], decisions: list[dict[str, Any]],
                  trace: dict[str, Any] | None) -> dict[str, Any] | None:
    """The decision made in the PR that fixed a related issue (related_work ranks those first)."""
    fixes = {f["id"] for r in related for f in r["fixed_by"]}
    d = next((d for d in decisions if d.get("source_id") in fixes), None)
    if not d:
        return None
    traced = next((t for t in (trace or {}).get("decisions", []) if t["id"] == d["id"]), {})
    return {"id": d["id"], "statement": d["statement"], "rationale": traced.get("rationale"),
            "alternatives": traced.get("alternatives") or [], "source_id": d["source_id"], "url": d.get("source_url")}


def allowed_links(facts: dict[str, Any]) -> set[str]:
    """Every URL the facts carry: the only links a draft may contain."""
    urls: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("url", "codeowners_url") and isinstance(x, str) and x.startswith("http"):
                    urls.add(x)
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(facts)
    return urls


_MD_LINK = re.compile(r"\[([^\]]*)\]\((\S+?)\)")
_BARE_URL = re.compile(r"(?<![(\[])https?://[^\s)\]>]+")


def clean_draft(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Drop links that no tool returned: a markdown link keeps its text, a bare URL goes."""
    rejected: list[str] = []

    def norm(u: str) -> str:
        return u.rstrip(".,;:")

    def md(m: re.Match) -> str:
        if norm(m.group(2)) in allowed:
            return m.group(0)
        rejected.append(m.group(2))
        return m.group(1)

    def bare(m: re.Match) -> str:
        if norm(m.group(0)) in allowed:
            return m.group(0)
        rejected.append(m.group(0))
        return ""
    text = _MD_LINK.sub(md, text)
    text = _BARE_URL.sub(bare, text)
    return re.sub(r"[ \t]+\n", "\n", text).strip(), rejected


# ---------------------------------------------------------------- gathering (MCP tools)

async def gather(client: Client, org: str, issue_id: str) -> dict[str, Any]:
    """Steps 2-5: the facts a draft is written from, and the tools that ran."""
    calls = []

    async def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        env = await _tool(client, name, {"org": org, **args})
        calls.append({"tool": name, "args": args, "queries": [c["query"] for c in env.get("cypher", [])]})
        return env.get("results", {})

    rw = await call("related_work", {"issue_id": issue_id})
    if str(rw.get("message", "")).startswith("not found"):
        raise StewardError(rw["message"])
    related = pick_related(rw.get("similar_issues") or [])
    module = primary_module(rw.get("modules") or [])
    owner = reviewer = None
    warnings: list[dict[str, Any]] = []
    owners: dict[str, Any] = {}
    if module:
        owners = await call("module_owners", {"module": module})
        if owners.get("module"):
            owner, warnings = pick_owner(owners)
            experts = await call("find_experts", {"module_or_topic": module, "min_score": REVIEWER_MIN_SCORE})
            reviewer = pick_reviewer(owner, experts.get("experts") or [], owners)
    decisions = rw.get("decisions") or []
    first = next((d for d in decisions if d.get("source_id") in {f["id"] for r in related for f in r["fixed_by"]}), None)
    trace = await call("trace_decision", {"node_id": first["id"]}) if first else None
    decision = pick_decision(related, decisions, trace)
    pending = [{"id": p["id"], "statement": p["statement"], "source_id": p.get("source_id"), "url": p.get("source_url")}
               for p in rw.get("pending_proposals") or [] if module and module in (p.get("modules") or [])]
    m = owners.get("module") or {}
    facts = {
        "issue": rw.get("issue"),
        "related_issues": related,
        "likely_duplicates": [r for r in related if r["duplicate"]],
        "module": {"id": m.get("id", module), "path": m.get("path")} if module else None,
        "decision_behind_fix": decision,
        "pending_proposals": pending,
        "suggested_owner": owner,
        "paper_owner_warnings": warnings,
        "suggested_reviewer": reviewer,
        "codeowners_url": owners.get("codeowners_url"),
    }
    return {"facts": facts, "calls": calls}


# ---------------------------------------------------------------- writing (LLM)

SYSTEM = """You are Lore's Steward. You draft the first triage comment on a new GitHub issue in {repo},
for a maintainer to review before it is posted. Write GitHub-flavoured Markdown.

Use only the facts given (JSON from Lore's graph). Never add a person, issue, PR, decision or link that
is not in them; links must be copied exactly from a "url" field. If a fact is null or empty, leave it
out (e.g. no reviewer -> don't suggest one). A pending proposal is not merged: never present it as current.

Follow the Playbook steps. The later steps were learned from maintainers' edits of earlier drafts: they
are the house style, and when a step conflicts with an earlier one, the later step wins."""

DRAFT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["comment"],
                "properties": {"comment": {"type": "string"}}}


def draft_messages(repo: str, facts: dict[str, Any], steps: list[str]) -> list[dict[str, Any]]:
    playbook = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    return [
        {"role": "system", "content": SYSTEM.format(repo=repo)},
        {"role": "user", "content": f"Playbook steps:\n{playbook}\n\nFacts:\n{json.dumps(facts, indent=1, default=str)}"
                                    "\n\nReply as JSON: {\"comment\": \"<the Markdown comment>\"}."},
    ]


def _parse(content: str, key: str) -> str | None:
    s, e = content.find("{"), content.rfind("}")
    if s < 0 or e < s:
        return None
    try:
        v = json.loads(content[s:e + 1]).get(key)
    except (json.JSONDecodeError, AttributeError):
        return None
    return v if isinstance(v, str) else None


async def draft_task(client: Client, org: str, task_id: str, issue_id: str, agent: str,
                     use_cache: bool = True) -> dict[str, Any]:
    """Steps 2-7 for a Task this agent has claimed. Releases the Task on any failure."""
    started = time.monotonic()
    try:
        g = await gather(client, org, issue_id)
        pb = (await _tool(client, "get_playbook", {"org": org, "name": PLAYBOOK_NAME}))["results"]
        repo = issue_id.removeprefix("issue:").split("#")[0]
        msgs = draft_messages(repo, g["facts"], pb["steps"])
        reply = await anyio.to_thread.run_sync(lambda: agent_chat(msgs, json_schema=DRAFT_SCHEMA, use_cache=use_cache))
        text = _parse(reply["content"], "comment")
        if not text or not text.strip():
            raise StewardError(f"{reply.get('model')} returned no comment")
        draft, rejected = clean_draft(text, allowed_links(g["facts"]))
        facts = {**g["facts"], "tool_calls": g["calls"], "rejected_links": rejected, "playbook_steps": pb["steps"]}
        await _tool(client, "save_draft", {"org": org, "task_id": task_id, "agent": agent, "draft": draft,
                                           "facts": facts, "playbook_version": pb["version"],
                                           "model": reply.get("model") or ""})
        return {"task_id": task_id, "issue_id": issue_id, "status": "drafted", "draft": draft, "facts": facts,
                "playbook_version": pb["version"], "model": reply.get("model"),
                "seconds": round(time.monotonic() - started, 1)}
    except Exception as e:  # noqa: BLE001 - the Task goes back on the board with the reason
        err = f"{type(e).__name__}: {e}"
        try:
            await _tool(client, "release_task", {"org": org, "task_id": task_id, "agent": agent, "error": err})
        except StewardError:
            pass
        return {"task_id": task_id, "issue_id": issue_id, "status": "open", "error": err}


async def run_once(client: Client, org: str, agent: str | None = None, task_ids: list[str] | None = None,
                   limit: int = 20, use_cache: bool = True, log=lambda m: None) -> list[dict[str, Any]]:
    """Claim and draft every open Task (or just task_ids). A Task another worker claimed first is
    skipped: claim_task returns claimed = false for it."""
    agent = agent or agent_name()
    board = (await _tool(client, "open_tasks", {"org": org, "limit": limit}))["results"]["tasks"]
    out = []
    for t in board:
        if task_ids is not None and t["task_id"] not in task_ids:
            continue
        if t["attempts"] >= STEWARD_MAX_ATTEMPTS:
            continue
        claim = (await _tool(client, "claim_task", {"org": org, "task_id": t["task_id"], "agent": agent}))["results"]
        if not claim["claimed"]:
            log(f"  {t['task_id']}: claimed by another worker, skipped")
            continue
        log(f"  {t['task_id']}: claimed by {agent}, drafting")
        r = await draft_task(client, org, t["task_id"], claim["issue_id"], agent, use_cache=use_cache)
        log(f"  {t['task_id']}: {r['status']}" + (f" ({r['error']})" if r.get("error") else f" in {r.get('seconds')}s"))
        out.append(r)
    return out


# ---------------------------------------------------------------- learning from edits

LEARN = """A maintainer edited the triage comment Lore's Steward drafted before approving it. Write the
general rule the Steward should follow on FUTURE issues so its drafts come out the way the maintainer
wants: one imperative sentence, at most 30 words, not specific to this issue's details (no issue
numbers or titles) unless the edit is about a standing practice (e.g. "always tag @x for FFI bugs").
If the edit only fixes a typo or wording with no general lesson, reply with an empty rule.
Reply as JSON: {"rule": "..."}."""

RULE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["rule"],
               "properties": {"rule": {"type": "string"}}}


def learn_rule(before: str, after: str) -> str:
    """One Playbook rule from a human's edit (blocking: one LLM call)."""
    msgs = [{"role": "system", "content": LEARN},
            {"role": "user", "content": f"Steward's draft:\n---\n{before}\n---\n\nWhat the maintainer approved:\n---\n{after}\n---"}]
    reply = agent_chat(msgs, json_schema=RULE_SCHEMA)
    return (_parse(reply["content"], "rule") or "").strip()[:300]
