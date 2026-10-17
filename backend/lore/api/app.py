"""Lore's HTTP API (FastAPI). OpenAPI docs at /docs.

    uv run --directory backend uvicorn lore.api.app:app --port 8000

Routes, one per UI screen (docs/PLAN.md "UI screens"):
  POST /ask                         Navigator answer: citations, subgraph, path, Cypher
  POST /ask/stream                  the same, streaming the tools and LLM calls as they happen (NDJSON)
  GET  /module/{id}                 owners vs experts, decisions by status, co-changed modules
  GET  /risk                        bus factor per module, bridge people, working groups
  GET  /triage                      triage inbox: Tasks, their issue, Steward's draft and its facts
  POST /triage/{task}/approve       approve a draft (edited or not): post_triage (sandbox only), Task -> approved;
                                    an edit is stored as Feedback and adds a rule to the Playbook
  POST /triage/{task}/redraft       put a drafted Task back on the board and let Steward draft it again
  POST /triage/sync                 check SANDBOX_REPO for new issues now and draft them
  GET  /playbook                    Steward's triage Playbook and the Feedback that adjusted it
  POST /webhook/github              sandbox issue events (signature checked): load the issue, open a Task;
                                    pull_request closed + merged: sync that PR (M15: new decisions, supersession)
  GET  /memory/{user}               past questions and what changed since
  GET  /users, POST /users          username picker (no passwords)
  GET  /health                      graphs, data versions, LLM endpoint states

Steward (M13): with STEWARD_POLL_SECONDS > 0 the API polls SANDBOX_REPO for new issues (default every
60 s, so no tunnel is needed locally); the deployed backend gets the same events from the webhook.
Either way the Librarian loads the issue and opens a Task, then Steward claims and drafts it.
M15: a merged PR (webhook, or the same poll checking for merges the graph lacks) is synced: the PR,
its commits and docs are re-fetched, its decisions become current and replace the ones they supersede.

/ask, Steward and the approve route go through lore-mcp (an in-process MCP session opened at startup:
the same server and protocol as stdio, without a second process loading the embedding model).
The read-only screens call the same named-query tool functions directly. Every response that
reads the graph carries the Cypher that ran, for the UI's "show query" toggle.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from mcp.client import Client
from pydantic import BaseModel, Field

from lore.agents import steward
from lore.agents.navigator import ask as navigator_ask
from lore.api.ratelimit import RateLimiter
from lore.config import DECISION_MIN_CONFIDENCE, PLAYBOOK_DEFAULT_STEPS, PLAYBOOK_NAME, get_settings, graph_name
from lore.graph.client import get_db, get_graph, query, ro_query
from lore.graph.queries import load_query
from lore.ingest import live, sync
from lore.llm.agent import load_state
from lore.llm.chat import LLMError
from lore.mcp_server import tools
from lore.mcp_server.server import mcp
from lore.safety import WriteRefused, make_approval_token, verify_webhook

# A child of uvicorn's logger, so Steward's progress shows in the server log at its level.
log = logging.getLogger("uvicorn.error").getChild("steward")

USER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")


def orgs() -> list[str]:
    """The orgs the API serves: the demo org and the sandbox repo's owner."""
    s = get_settings()
    out = [s.demo_org]
    if s.sandbox_repo:
        out.append(s.sandbox_repo.split("/")[0])
    return list(dict.fromkeys(out))


def _org(org: str | None) -> str:
    """A known org, matched case-insensitively; 404 otherwise."""
    if org is None:
        return orgs()[0]
    for o in orgs():
        if o.lower() == org.lower():
            return o
    raise HTTPException(404, f"unknown org {org!r}; this API serves {orgs()}")


def _user(user: str) -> str:
    if not USER_ID.match(user or ""):
        raise HTTPException(422, "user: 1-40 characters, letters, digits, '.', '_' or '-', starting with a letter or digit")
    return user


def _run(fn, *args: Any) -> dict[str, Any]:
    """A tool function; its expected failures (unknown org/module, bad argument) become 404/400."""
    try:
        return fn(*args)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(404 if "no graph" in str(e) or "not found" in str(e) else 400, str(e)) from e


def _cypher(*envelopes: dict[str, Any], extra: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [{"tool": e["tool"], **c} for e in envelopes for c in e["cypher"]] + (extra or [])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with Client(mcp) as client:
        app.state.mcp = client
        app.state.steward = {"agent": steward.agent_name(), "last_tick": None, "last_error": None}
        app.state.sync = {"last": None, "last_error": None, "running": False}
        app.state.background = set()
        poll = None
        if settings.sandbox_repo and settings.steward_poll_seconds > 0:
            poll = asyncio.create_task(_steward_poll())
        yield
        if poll:
            poll.cancel()


settings = get_settings()
app = FastAPI(
    title="Lore API",
    version="0.1.0",
    description="Who owns this, who knows this and why was this decided: answers traced through a "
                "GitHub org's history in FalkorDB. Every graph answer includes the Cypher that ran.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
limiter = RateLimiter(settings.ask_per_minute, settings.ask_per_day)
# Wrong approve passcodes per client IP: 5 a minute, 20 a day, then 429 (no guessing it).
passcode_failures = RateLimiter(5, 20)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"], summary="Graphs, data versions and LLM endpoint states")
def health() -> dict[str, Any]:
    graphs = set(get_db().list_graphs())
    out = {}
    for o in orgs():
        if graph_name(o) in graphs:
            out[o] = {"graph": graph_name(o), "data_version": tools.data_version(o)["results"]["version"]}
        else:
            out[o] = {"graph": graph_name(o), "missing": True}
    now = time.time()
    llm = {k: v for k, v in load_state().items() if v.get("until", 0) > now}
    return {"orgs": out, "sandbox_repo": settings.sandbox_repo, "llm_endpoints_unavailable": llm,
            "sync": getattr(app.state, "sync", None)}


# ---------------------------------------------------------------- Ask

class AskIn(BaseModel):
    org: str = Field(examples=["FalkorDB"])
    user: str = Field(examples=["amrith"])
    question: str = Field(min_length=3, max_length=500, examples=["Who knows the Cypher parser?"])
    session_id: str | None = None


ASK_FIELDS = ("question", "org", "user", "intent", "found", "not_found", "answer", "sentences", "citations",
              "subgraph", "path", "cypher", "tool_calls", "llm_calls", "dropped", "session_id", "seconds",
              "answer_cache", "sources", "labels", "decision_status")


@app.post("/ask", tags=["ask"], summary="Ask the Navigator (rate-limited per user)",
          responses={429: {"description": "Too many questions from this user"},
                     503: {"description": "Every free-tier LLM endpoint is rate-limited or out of quota"}})
async def ask(body: AskIn) -> dict[str, Any]:
    org, user = _org(body.org), _user(body.user)
    if limited := _limited(user):
        return limited
    try:
        r = await navigator_ask(body.question, org, user, app.state.mcp, session_id=body.session_id)
    except LLMError as e:
        raise HTTPException(503, f"no LLM available right now: {e}") from e
    return {k: r.get(k) for k in ASK_FIELDS}


def _limited(user: str) -> JSONResponse | None:
    if wait := limiter.check(user):
        return JSONResponse({"detail": f"rate limit: at most {settings.ask_per_minute} questions a minute and "
                                       f"{settings.ask_per_day} a day per user; retry in {wait:.0f}s"},
                            status_code=429, headers={"Retry-After": str(int(wait) + 1)})
    return None


@app.post("/ask/stream", tags=["ask"], summary="Ask, streaming progress as NDJSON (one JSON object per line)",
          responses={200: {"content": {"application/x-ndjson": {}},
                           "description": 'Lines: {"type": "tool"|"llm"|"llm_done"|"cache", ...} while the '
                                          'Navigator works, then {"type": "answer", "data": <same as POST /ask>} '
                                          'or {"type": "error", "status", "detail"}'}})
async def ask_stream(body: AskIn):
    org, user = _org(body.org), _user(body.user)
    if limited := _limited(user):
        return limited
    send, recv = anyio.create_memory_object_stream(max_buffer_size=math.inf)

    async def produce() -> None:
        with send:
            try:
                r = await navigator_ask(body.question, org, user, app.state.mcp, session_id=body.session_id,
                                        on_event=send.send_nowait)
                send.send_nowait({"type": "answer", "data": {k: r.get(k) for k in ASK_FIELDS}})
            except LLMError as e:
                send.send_nowait({"type": "error", "status": 503, "detail": f"no LLM available right now: {e}"})
            except Exception as e:  # noqa: BLE001 - reported to the client, not swallowed
                send.send_nowait({"type": "error", "status": 500, "detail": f"{type(e).__name__}: {e}"})

    async def lines():
        task = asyncio.create_task(produce())
        try:
            with recv:
                async for event in recv:
                    yield json.dumps(event, default=str) + "\n"
        finally:
            if not task.done():  # the client went away mid-answer
                task.cancel()

    return StreamingResponse(lines(), media_type="application/x-ndjson")


# ---------------------------------------------------------------- Module page

@app.get("/module/{module_id:path}", tags=["screens"],
         summary="Module page: owners vs experts, decisions by status, co-changed modules")
def module(module_id: str, org: str | None = Query(None, description="default: the sandbox org for "
                                                                       "sandbox modules, else the demo org")) -> dict[str, Any]:
    """module_id: an id (module:FalkorDB:graph/src/index), a path (graph/src/index) or a last segment (index)."""
    if org is None:
        sandbox_repo = settings.sandbox_repo.split("/")[-1]
        org = orgs()[-1] if sandbox_repo and module_id.startswith(f"module:{sandbox_repo}:") else orgs()[0]
    org = _org(org)
    owners = _run(tools.module_owners, org, module_id)
    m = owners["results"]["module"]
    if not m:
        raise HTTPException(404, owners["results"].get("message", f"no module {module_id!r}"))
    experts = _run(tools.find_experts, org, m["id"])
    impact = _run(tools.impact_radius, org, m["id"])
    params = {"modules": [m["id"]], "min_confidence": DECISION_MIN_CONFIDENCE, "limit": 30}
    rows = ro_query(get_graph(org), "module_decisions", params)
    decisions = tools._split([tools._decision(r) for r in rows])
    co_changed = [{**{k: v for k, v in c.items() if k != "decisions"}, "decisions": c["decisions"][:3]}
                  for c in impact["results"]["co_changed"]]
    return {
        "org": org, "module": m,
        "owners": {k: owners["results"][k] for k in ("listed_owner", "owners", "paper_owners", "active_experts",
                                                     "top_expert_is_owner", "mismatch", "codeowners_url")
                   } | ({"message": owners["results"]["message"]} if "message" in owners["results"] else {}),
        "experts": experts["results"]["experts"],
        "decisions": decisions,
        "co_changed": co_changed,
        "sources": {**owners["sources"], **experts["sources"], **impact["sources"]},
        "cypher": _cypher(owners, experts, impact, extra=[{"tool": "module_page", "query": "module_decisions",
                                                             "cypher": load_query("module_decisions"),
                                                             "params": params, "rows": len(rows)}]),
    }


# ---------------------------------------------------------------- Knowledge-risk map

@app.get("/risk", tags=["screens"], summary="Knowledge risk: bus factor per module, bridge people, working groups")
def risk(org: str | None = None, repo: str | None = Query(None, description="limit modules to one repo")) -> dict[str, Any]:
    org = _org(org)
    env = _run(tools.knowledge_risk, org, repo)
    return {"org": org, **env["results"], "cypher": _cypher(env)}


# ---------------------------------------------------------------- Steward (poll, webhook)

_tick_lock = asyncio.Lock()


async def steward_tick(issues: list[dict[str, Any]] | None = None, force: bool = False,
                       task_ids: list[str] | None = None) -> dict[str, Any]:
    """Librarian intake (new issues -> Issue nodes + open Tasks), then Steward drafts open Tasks.
    One tick at a time per process; across processes the atomic claim keeps drafts single."""
    repo = settings.sandbox_repo
    async with _tick_lock:
        taken = await anyio.to_thread.run_sync(lambda: live.intake(repo, issues, force))
        for i in taken["loaded"]:
            log.info("steward: loaded %s", i)
        drafted = await steward.run_once(app.state.mcp, repo.split("/")[0], app.state.steward["agent"],
                                         task_ids=task_ids, log=log.info)
    state = {"at": int(time.time()), "loaded": taken["loaded"], "opened": [x["task_id"] for x in taken["tasks"]],
             "drafted": [{k: d.get(k) for k in ("task_id", "status", "error", "model")} for d in drafted]}
    app.state.steward.update(last_tick=state, last_error=None)
    return state


_sync_lock = asyncio.Lock()


async def sync_tick(numbers: list[int] | None = None, simulate: bool = False) -> dict[str, Any] | None:
    """M15: sync merged PRs (these, or whatever the poll finds merged on GitHub but not in the graph).
    One sync at a time; a second trigger for the same merge then finds nothing left to do."""
    repo = settings.sandbox_repo
    async with _sync_lock:
        app.state.sync["running"] = True
        try:
            if numbers:
                states = await anyio.to_thread.run_sync(lambda: ro_query(
                    get_graph(repo.split("/")[0]), "pr_states", {"ids": [f"pr:{repo}#{n}" for n in numbers]}))
                numbers = [n for n, s in zip(numbers, states) if not s["merged_at"]]  # already synced: skip
                if not numbers:
                    return None
                r = await anyio.to_thread.run_sync(lambda: sync.sync_merged(repo, numbers, simulate, log=log.info))
            else:
                r = await anyio.to_thread.run_sync(lambda: sync.sync_check(repo, log=log.info))
        finally:
            app.state.sync["running"] = False
    if r:
        app.state.sync.update(last={k: r[k] for k in ("prs", "promoted", "extracted", "superseded", "modules",
                                                       "seconds", "steps", "simulated")} | {"at": int(time.time())},
                              last_error=None)
        log.info("sync: PR %s in %ss %s", r["prs"], r["seconds"], r["steps"])
    return r


async def _steward_poll() -> None:
    while True:
        try:
            await steward_tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - GitHub or the LLM pool down: log it, try next minute
            app.state.steward["last_error"] = f"{type(e).__name__}: {e}"
            log.warning("steward poll failed: %s: %s", type(e).__name__, e)
        try:
            await sync_tick()  # the webhook's fallback: a merge it missed is synced within a minute
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            app.state.sync["last_error"] = f"{type(e).__name__}: {e}"
            log.warning("sync poll failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(settings.steward_poll_seconds)


def _in_background(coro) -> None:
    task = asyncio.create_task(coro)
    app.state.background.add(task)  # keep a reference until it finishes
    task.add_done_callback(app.state.background.discard)


@app.post("/webhook/github", tags=["triage"], status_code=202,
          summary="GitHub webhook for SANDBOX_REPO issue events (X-Hub-Signature-256 checked)")
async def github_webhook(request: Request) -> dict[str, Any]:
    """Point the sandbox repo's webhook here (content type application/json, the secret in
    GITHUB_WEBHOOK_SECRET, "Issues" events). An opened, reopened or edited issue is loaded and gets
    a triage Task; Steward drafts it in the background. Anything else is acknowledged and ignored."""
    body = await request.body()
    try:
        verify_webhook(body, request.headers.get("X-Hub-Signature-256"))
    except WriteRefused as e:
        raise HTTPException(401, str(e)) from e
    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body or b"{}")
    if event == "ping":
        return {"ok": True, "event": "ping"}
    repo = (payload.get("repository") or {}).get("full_name", "")
    if event == "pull_request":
        pr = payload.get("pull_request") or {}
        if payload.get("action") != "closed" or not pr.get("merged"):
            return {"ok": True, "ignored": f"pull_request {payload.get('action', '')}".strip()}
        if repo.lower() != settings.sandbox_repo.lower():
            raise HTTPException(403, f"{repo} is not the sandbox repo")
        _in_background(sync_tick([int(pr["number"])], simulate=settings.sync_simulate_merge))
        return {"ok": True, "event": "pull_request", "action": "merged", "pr": pr["number"]}
    if event != "issues" or payload.get("action") not in ("opened", "reopened", "edited"):
        return {"ok": True, "ignored": f"{event} {payload.get('action', '')}".strip()}
    if repo.lower() != settings.sandbox_repo.lower():
        raise HTTPException(403, f"{repo} is not the sandbox repo")
    issue = payload["issue"]
    _in_background(steward_tick([issue], force=True))
    return {"ok": True, "event": "issues", "action": payload["action"], "issue": issue.get("number")}


# ---------------------------------------------------------------- Triage inbox

def _sandbox_org() -> str:
    if not settings.sandbox_repo:
        raise HTTPException(503, "SANDBOX_REPO is not set")
    return _org(settings.sandbox_repo.split("/")[0])


def _task_id(task: str) -> str:
    """'9', 'issue:<repo>#9' or a full task id -> the full task id."""
    if task.isdigit():
        return f"task:triage:issue:{settings.sandbox_repo}#{task}"
    return task if task.startswith("task:") else f"task:triage:{task}"


@app.get("/triage", tags=["triage"],
         summary="Triage inbox: Tasks with their issue, Steward's draft and its facts")
def triage(status: str = Query("", description="open, claimed, drafted, approved; empty = all"),
           preview: bool = Query(False, description="also run related_work for Tasks Steward hasn't drafted yet"),
           limit: int = Query(30, ge=1, le=100)) -> dict[str, Any]:
    org = _sandbox_org()
    params = {"status": status, "limit": limit}
    items = ro_query(get_graph(org), "triage_inbox", params)
    cypher = [{"tool": "triage", "query": "triage_inbox", "cypher": load_query("triage_inbox"), "params": params,
               "rows": len(items)}]
    for item in items:
        item["facts"] = json.loads(item["facts"]) if item.get("facts") else None
        if preview and not item["facts"] and item["status"] != "approved":
            env = _run(tools.related_work, org, item["issue_id"], None, 3)
            r = env["results"]
            item["related"] = {"similar_issues": r["similar_issues"], "duplicate_candidates": r["duplicate_candidates"],
                               "modules": r["modules"], "decisions": r["decisions"][:3],
                               "pending_proposals": r["pending_proposals"][:2]}
            cypher += _cypher(env)
    return {"org": org, "repo": settings.sandbox_repo, "items": items, "cypher": cypher,
            "dry_run": settings.dry_run, "poll_seconds": settings.steward_poll_seconds,
            "steward": app.state.steward}


class ApproveIn(BaseModel):
    user: str = Field(examples=["amrith"])
    passcode: str = Field("", max_length=200, description="APPROVE_PASSCODE: only people who know it can approve")
    draft: str | None = Field(None, max_length=4000,
                              description="the final comment text (edited or not); default: the Task's draft")
    rule: str | None = Field(None, max_length=300,
                             description="what Steward should do next time; when the draft was edited and this is "
                                         "empty, the rule is learned from the edit")


@app.post("/triage/{task:path}/approve", tags=["triage"],
          summary="Approve a draft: post it to the sandbox issue (unless DRY_RUN) and mark the Task approved")
async def approve(task: str, body: ApproveIn, request: Request) -> dict[str, Any]:
    """task: the issue number (9), the issue id or the full task id (URL-encode '#' as %23).
    The passcode (APPROVE_PASSCODE) is checked first; only then is the approval token minted, by the
    human's click, for this issue and this exact text. post_triage refuses anything else and any repo
    but SANDBOX_REPO."""
    _check_passcode(body.passcode, request)
    org, user, task_id = _sandbox_org(), _user(body.user), _task_id(task)
    rows = [r for r in ro_query(get_graph(org), "triage_inbox", {"status": "", "limit": 1000}) if r["task_id"] == task_id]
    if not rows:
        raise HTTPException(404, f"no triage task {task_id}")
    item = rows[0]
    if item["status"] == "approved":
        raise HTTPException(409, f"{task_id} is already approved")
    draft = (body.draft or item["draft"] or "").strip()
    if not draft:
        raise HTTPException(422, "nothing to approve: Steward hasn't drafted this task yet, so send the comment as draft")
    token = make_approval_token(item["issue_id"], draft)
    r = await app.state.mcp.call_tool("post_triage", {"org": org, "issue_id": item["issue_id"], "draft": draft,
                                                      "approval_token": token})
    if r.is_error:
        raise HTTPException(403, " ".join(getattr(c, "text", "") for c in r.content) or "post_triage refused")
    posted = r.structured_content["results"]
    params = {"task_id": task_id, "draft": draft, "user": user, "now": int(time.time()),
              "posted": bool(posted.get("posted")), "dry_run": bool(posted.get("dry_run")),
              "comment_url": posted.get("comment_url")}
    done = await anyio.to_thread.run_sync(lambda: query(get_graph(org), "task_approve", params))
    if not done:
        raise HTTPException(409, f"{task_id} was approved meanwhile")
    cypher = [{"tool": "approve", "query": "task_approve", "cypher": load_query("task_approve"),
               "params": {**params, "draft": f"<{len(draft)} chars>"}, "rows": 1}]
    feedback = None
    before = (item["draft"] or "").strip()
    if before and _differs(before, draft):
        feedback, fb_cypher = await _store_feedback(org, task_id, user, before, draft, (body.rule or "").strip())
        cypher.append(fb_cypher)
    return {"task": done[0], "post": posted, "feedback": feedback, "cypher": cypher}


def _check_passcode(passcode: str, request: Request) -> None:
    """403 for a wrong passcode, 429 after too many from one IP, 503 when none is configured."""
    if not settings.approve_passcode:
        raise HTTPException(503, "APPROVE_PASSCODE is not set on the server, so approvals are refused")
    ip = request.client.host if request.client else "unknown"  # the real client: uvicorn trusts Caddy's X-Forwarded-For
    if wait := passcode_failures.blocked(ip):
        raise HTTPException(429, f"too many wrong passcodes; retry in {wait:.0f}s", headers={"Retry-After": str(int(wait) + 1)})
    if not hmac.compare_digest(passcode.encode("utf-8"), settings.approve_passcode.encode("utf-8")):
        passcode_failures.check(ip)
        raise HTTPException(403, "wrong approve passcode")


def _differs(a: str, b: str) -> bool:
    """An edit worth learning from: more than whitespace changed."""
    return re.sub(r"\s+", " ", a).strip() != re.sub(r"\s+", " ", b).strip()


async def _store_feedback(org: str, task_id: str, user: str, before: str, after: str,
                          rule: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(Feedback)-[:ADJUSTS]->(Playbook): the edit, and the rule it teaches Steward (the human's own
    words when given, else one LLM call; no LLM available = the edit is stored without a rule)."""
    learned = False
    if not rule:
        try:
            rule = await anyio.to_thread.run_sync(lambda: steward.learn_rule(before, after))
            learned = True
        except LLMError as e:
            log.warning("feedback: no rule learned (%s)", e)
    params = {"name": PLAYBOOK_NAME, "default_steps": PLAYBOOK_DEFAULT_STEPS,
              "feedback_id": f"feedback:{uuid.uuid4().hex[:16]}", "text": rule or "edited the draft",
              "rule": rule, "before": before, "after": after, "task_id": task_id, "user": user,
              "now": int(time.time())}
    row = (await anyio.to_thread.run_sync(lambda: query(get_graph(org), "feedback_add", params)))[0]
    shown = {**params, "before": f"<{len(before)} chars>", "after": f"<{len(after)} chars>",
             "default_steps": f"<{len(PLAYBOOK_DEFAULT_STEPS)} steps>"}
    return ({"id": row["feedback_id"], "rule": rule, "learned": learned, "playbook_version": row["version"],
             "steps": row["steps"]},
            {"tool": "approve", "query": "feedback_add", "cypher": load_query("feedback_add"), "params": shown,
             "rows": 1})


@app.post("/triage/{task:path}/redraft", tags=["triage"],
          summary="Let Steward draft a Task again (e.g. after the Playbook learned a rule)")
async def redraft(task: str) -> dict[str, Any]:
    org, task_id = _sandbox_org(), _task_id(task)
    if not await anyio.to_thread.run_sync(lambda: query(get_graph(org), "task_reopen", {"task_id": task_id})):
        raise HTTPException(409, f"{task_id} is approved or doesn't exist; only drafted Tasks can be redrafted")
    async with _tick_lock:
        out = await steward.run_once(app.state.mcp, org, app.state.steward["agent"], task_ids=[task_id],
                                     log=log.info)
    if not out:
        raise HTTPException(409, f"{task_id} was claimed by another worker")
    r = out[0]
    if r["status"] != "drafted":
        raise HTTPException(503, f"Steward couldn't draft {task_id}: {r.get('error')}")
    return {k: r.get(k) for k in ("task_id", "issue_id", "status", "draft", "facts", "playbook_version", "model")}


@app.post("/triage/sync", tags=["triage"], summary="Check SANDBOX_REPO for new issues now and draft open Tasks")
async def triage_sync() -> dict[str, Any]:
    _sandbox_org()
    try:
        return await steward_tick()
    except Exception as e:  # noqa: BLE001 - GitHub unreachable, LLM pool out: say so
        raise HTTPException(503, f"sync failed: {type(e).__name__}: {e}") from e


@app.get("/playbook", tags=["triage"], summary="Steward's triage Playbook: steps, version, Feedback")
def playbook() -> dict[str, Any]:
    env = _run(tools.get_playbook, _sandbox_org())
    return {**env["results"], "cypher": _cypher(env)}


# ---------------------------------------------------------------- My memory

@app.get("/memory/{user}", tags=["memory"], summary="A user's past questions and what changed since, per org")
def memory(user: str, org: str | None = Query(None, description="one org; default: every org"),
           topic: str | None = None, limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    user = _user(user)
    out, cypher = {}, []
    for o in [_org(org)] if org else orgs():
        env = _run(tools.recall, o, user, topic, limit)
        out[o] = {"questions": env["results"]["questions"], "changes": env["results"]["changes"],
                  "sources": env["sources"]}
        cypher += _cypher(env)
    return {"user": user, "orgs": out, "cypher": cypher}


# ---------------------------------------------------------------- Users

class UserIn(BaseModel):
    id: str = Field(examples=["amrith"], description="the username; becomes User.id")
    github_login: str | None = Field(None, examples=["im-Amrith"],
                                     description="optional; links (User)-[:IS]->(Person) where that person exists")


@app.get("/users", tags=["users"], summary="Username picker: every user, with questions asked per org")
def users() -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for o in orgs():
        for r in ro_query(get_graph(o), "users_list", {}):
            u = merged.setdefault(r["id"], {"id": r["id"], "github_login": r["github_login"], "questions": 0,
                                            "last_asked": None, "person_ids": {}})
            u["questions"] += r["questions"]
            u["github_login"] = u["github_login"] or r["github_login"]
            if r["last_asked"] and (u["last_asked"] or 0) < r["last_asked"]:
                u["last_asked"] = r["last_asked"]
            if r["person_id"]:
                u["person_ids"][o] = r["person_id"]
    return {"users": sorted(merged.values(), key=lambda u: (-(u["last_asked"] or 0), u["id"]))}


@app.post("/users", tags=["users"], summary="Create (or update) a user in every org graph", status_code=201)
def create_user(body: UserIn) -> dict[str, Any]:
    uid = _user(body.id)
    params = {"id": uid, "github_login": body.github_login or None, "now": int(time.time())}
    linked = {}
    for o in orgs():
        r = query(get_graph(o), "user_upsert", params)[0]
        if r["person_id"]:
            linked[o] = r["person_id"]
    return {"id": uid, "github_login": body.github_login, "is_person": linked}
