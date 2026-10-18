"""Incremental sync (M15, docs/PLAN.md "Keeping knowledge current"): a merged PR updates the graph.

    sync_merged(repo, [16])            webhook (pull_request closed + merged) or the poll found PR #16 merged
    merged_not_loaded(repo)            the poll's check: PRs merged on GitHub whose merge the graph lacks
    prime(repo)                        once per server: fetch the repo's raw cache (data/raw), which a sync updates

What a sync does, in order (each step's time is in the report):
  1. re-fetch: just the merged PR (one GraphQL query), the commits added since the last fetch (git
     fetch + their logins) and the repo's docs (one query), into the raw cache
  2. load: normalise the repo's raw cache and MERGE it (idempotent; nothing else in the graph changes)
  3. promote: the PR's decisions extracted while it was a proposal go from 'proposed' to 'active'
     (same node, same id, so memory that cited them still does)
  4. extract: only the changed PRs and docs that have no decision yet (ADR 0003 in the demo); a source
     that already has decisions is never re-extracted, which would replace them and their history
  5. embed what changed (local model): the changed docs' chunks and the decisions with no embedding
  6. supersede: for each newly active decision, the active decisions on the same module AND topic
     go to the LLM, which says which ones it replaces; those get SUPERSEDES, status 'superseded'
     and valid_to (queries/15_*)
  7. re-derive EXPERT_IN and CO_CHANGED only for the modules the new commits touched
The graph's data version (query 93) counts merged PRs and SUPERSEDES edges, so it changes and the
Navigator's answer cache can't serve the pre-merge answer.

simulate=True (tests only, never in production): the PR is treated as merged now, and its commits
and docs are read from its head branch, so the whole sync runs without merging anything on GitHub.
Use it on a copy of the raw cache (LORE_RAW_DIR) and a test FalkorDB.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from lore.config import SYNC_EXTRA_POOL, DECISION_MIN_CONFIDENCE, FETCH_SINCE_DAYS, CO_CHANGE_MAX_MODULES, CO_CHANGE_MIN_COUNT, \
    RAW_DIR, get_settings
from lore.graph.client import get_graph, query, ro_query
from lore.ingest.embed import embed_graph
from lore.ingest.extract import extract, load_candidates, load_extractions
from lore.ingest.github_fetch import (
    GitHub,
    _git,
    assign_logins,
    fetch_docs,
    fetch_pr,
    fetch_repo,
    lookup_commit_logins,
    prefetch_blobs,
    read_commits,
    read_json,
    write_json,
)
from lore.ingest.load import load_rows
from lore.ingest.normalize import commit_id, doc_id, normalize_repos, pr_id
from lore.llm.agent import agent_chat
from lore.llm.chat import POOLED
from lore.safety import check_sandbox_repo

GITHUB_API = "https://api.github.com"
DERIVE_JOBS = ["expert_reset", "expert_authored", "expert_reviewed", "expert_score", "co_changed_reset", "co_changed"]


def _repo_dir(repo: str) -> Path:
    owner, name = repo.split("/")
    return RAW_DIR / owner / name


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- what to sync

def prime(repo: str, log: Callable[[str], None] = print) -> bool:
    """Fetch the repo's whole raw cache once (a fresh server has none). False if it was there."""
    check_sandbox_repo(repo)
    if (_repo_dir(repo) / "commits.json").exists():  # the last file fetch_repo writes
        return False
    owner, name = repo.split("/")
    since = datetime.now(timezone.utc) - timedelta(days=FETCH_SINCE_DAYS)
    fetch_repo(GitHub(get_settings().github_token, log=log), owner, name, since)
    return True


def merged_not_loaded(repo: str, recent: int = 10) -> list[int]:
    """The poll's fallback for a missed webhook: recently closed PRs that GitHub says are merged
    but the graph still has unmerged (one REST call)."""
    token = get_settings().github_token
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "lore-librarian",
               **({"Authorization": f"Bearer {token}"} if token else {})}
    r = httpx.get(f"{GITHUB_API}/repos/{repo}/pulls", headers=headers, timeout=30,
                  params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": recent})
    r.raise_for_status()
    merged = [p["number"] for p in r.json() if p.get("merged_at")]
    if not merged:
        return []
    graph = get_graph(repo.split("/")[0])
    states = ro_query(graph, "pr_states", {"ids": [pr_id(repo, n) for n in merged]})
    loaded = {s["id"] for s in states if s["merged_at"]}
    return [n for n in merged if pr_id(repo, n) not in loaded]


# ---------------------------------------------------------------- 1. re-fetch

def refetch(repo: str, numbers: list[int], simulate: bool, log: Callable[[str], None]) -> dict[str, Any]:
    """Update the raw cache for these PRs: the PRs, new commits, docs. Returns what changed."""
    owner, name = repo.split("/")
    d = _repo_dir(repo)
    gh = GitHub(get_settings().github_token, log=lambda m: None)
    now = time.time()

    prs = read_json(d / "prs.json")
    heads = []
    for n in numbers:
        node = fetch_pr(gh, owner, name, n)
        if simulate:  # test only: the PR as it would look merged a moment ago
            node.update(state="MERGED", isDraft=False, mergedAt=_iso(now), closedAt=_iso(now))
            heads.append(node["headRefName"])
        prs = [p for p in prs if p["number"] != n] + [node]
    write_json(d / "prs.json", prs)

    git_dir = d / "git"
    _git(git_dir, "fetch", "--prune", "origin")
    default = read_json(d / "repo.json")["defaultBranchRef"]["name"]
    old = read_json(d / "commits.json")
    since = datetime.fromisoformat(old["since"])
    branches = list(dict.fromkeys(old["branches"] + heads))
    prefetch_blobs(git_dir, branches, since, lambda m: None)
    commits = read_commits(git_dir, branches, since)
    known = {c["sha"]: c for c in old["commits"]}
    new = [c["sha"] for c in commits if c["sha"] not in known]
    # Logins GitHub already gave for known commits are kept; only new commits are looked up.
    api_login = {s: c["author_login"] for s, c in known.items() if c.get("login_source") == "api"}
    api_login.update(lookup_commit_logins(gh, owner, name, new) if new else {})
    counts = assign_logins(commits, api_login)
    write_json(d / "commits.json", {**old, "branches": branches, "login_sources": counts, "commits": commits})

    old_docs = {x["path"]: x["text"] for x in read_json(d / "docs.json")}
    docs = fetch_docs(gh, owner, name, git_dir, heads[0] if simulate and heads else default)
    write_json(d / "docs.json", docs)
    changed_docs = [doc_id(repo, x["path"]) for x in docs if old_docs.get(x["path"]) != x["text"]]
    log(f"  re-fetched PR {', '.join(f'#{n}' for n in numbers)}: {len(new)} new commit(s), "
        f"{len(changed_docs)} changed doc(s) {[c.split(':', 2)[-1] for c in changed_docs]}")
    return {"pr_ids": [pr_id(repo, n) for n in numbers], "commit_ids": [commit_id(s) for s in new],
            "doc_ids": changed_docs}


# ---------------------------------------------------------------- 6. supersession (LLM judge)

JUDGE = """You maintain the decision record of the {repo} repository. A pull request was just merged and a
decision became current. Below are older decisions, still marked current, that touch the same module
and topic. For each one, say whether the NEW decision replaces it: it reverses, overturns or
supersedes that choice, so the older one is no longer how the project works. A decision that is
merely related, or that both can be true at once, is NOT replaced. Only use ids from the list.
Reply as JSON: {{"replaces": [{{"id": "<decision id>", "reason": "<one short sentence>"}}]}}"""

JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["replaces"], "properties": {
    "replaces": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "reason"],
        "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}}}}}


def _brief(d: dict[str, Any]) -> dict[str, Any]:
    return {k: d.get(k) for k in ("id", "statement", "rationale", "alternatives", "source_id") if d.get(k)}


def judge(repo: str, new: dict[str, Any], olds: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Which of olds the new decision replaces (one LLM call). Ids not in olds are dropped."""
    msgs = [{"role": "system", "content": JUDGE.format(repo=repo)},
            {"role": "user", "content": json.dumps({"new": _brief(new), "older": [_brief(o) for o in olds]},
                                                   indent=1, default=str)}]
    reply = agent_chat(msgs, json_schema=JUDGE_SCHEMA, extra_pool=SYNC_EXTRA_POOL)
    content = reply["content"]
    try:
        out = json.loads(content[content.find("{"):content.rfind("}") + 1]).get("replaces", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    ok = {o["id"] for o in olds}
    return [{"id": r["id"], "reason": str(r.get("reason", ""))[:300]} for r in out
            if isinstance(r, dict) and r.get("id") in ok]


# ---------------------------------------------------------------- the sync

def sync_merged(repo: str, numbers: list[int], simulate: bool = False,
                log: Callable[[str], None] = print) -> dict[str, Any]:
    check_sandbox_repo(repo)
    owner = repo.split("/")[0]
    graph = get_graph(owner)
    t0, times = time.monotonic(), {}

    def lap(step: str) -> None:
        times[step] = round(time.monotonic() - t0 - sum(times.values()), 1)

    ch = refetch(repo, numbers, simulate, log)
    lap("refetch")
    load_rows(graph, normalize_repos([tuple(repo.split("/"))]), log=lambda m: None, indexes=False)
    lap("load")
    now = int(time.time())
    # When the change took effect: the merge. Every decision it supersedes is valid until then (an ADR
    # added in the PR has its own, earlier, commit date; that isn't when the old decision stopped).
    merged_at = [s["merged_at"] for s in ro_query(graph, "pr_states", {"ids": ch["pr_ids"]}) if s["merged_at"]]
    effective = max(merged_at) if merged_at else now
    promoted = query(graph, "promote_decisions", {"pr_ids": ch["pr_ids"], "now": now})
    log(f"  promoted {len(promoted)} decision(s) from proposed to active")
    lap("promote")

    fresh = {r["id"] for r in ro_query(graph, "sources_without_decisions", {"ids": ch["pr_ids"] + ch["doc_ids"]})}
    cands = [c for c in load_candidates(graph, repo, all_prs=True) if c.id in fresh]
    extracted: list[dict[str, Any]] = []
    if cands:
        token = POOLED.set(SYNC_EXTRA_POOL)  # extraction through the pool: a merge can't stall on one endpoint
        try:
            results = extract(cands, repo, owner, log=log)
        finally:
            POOLED.reset(token)
        load_extractions(graph, results, owner, log=lambda m: None)
        extracted = ro_query(graph, "decisions_of_sources", {"ids": [c.id for c in cands]})
    log(f"  extracted {len(extracted)} decision(s) from {[c.label for c in cands]}")
    lap("extract")
    embed_graph(graph, repo, log=lambda m: None, missing_only=True, doc_ids=ch["doc_ids"])
    lap("embed")

    new_ids = [p["id"] for p in promoted] + [e["id"] for e in extracted]
    rows: list[dict[str, Any]] = []
    for nid in new_ids:
        new = ro_query(graph, "decision_detail", {"id": nid})[0]
        olds = ro_query(graph, "supersede_candidates", {"new_id": nid, "new_ids": new_ids,
                                                        "min_confidence": DECISION_MIN_CONFIDENCE})
        if not olds:
            continue
        for r in judge(repo, new, olds):
            rows.append({"new_id": nid, "old_id": r["id"], "reason": r["reason"], "at": now,
                         "valid_to": effective})
            log(f"  {nid} supersedes {r['id']}: {r['reason']}")
    if rows:
        query(graph, "supersede", {"rows": rows})
    lap("supersede")

    modules = [r["id"] for r in ro_query(graph, "modules_of_commits", {"ids": ch["commit_ids"]})]
    if modules:
        params = {"now": now, "modules": modules, "max_modules": CO_CHANGE_MAX_MODULES,
                  "min_count": CO_CHANGE_MIN_COUNT}
        for job in DERIVE_JOBS:
            query(graph, job, params)
    log(f"  re-derived EXPERT_IN / CO_CHANGED for {[m.rsplit(':', 1)[-1] for m in modules]}")
    lap("derive")
    return {"repo": repo, "prs": numbers, "simulated": simulate, **ch, "promoted": [p["id"] for p in promoted],
            "extracted": [e["id"] for e in extracted], "superseded": rows, "modules": modules,
            "seconds": round(time.monotonic() - t0, 1), "steps": times}


def sync_check(repo: str, log: Callable[[str], None] = print) -> dict[str, Any] | None:
    """The poll: sync any merged PR the graph has not seen merged. None when there is nothing to do."""
    numbers = merged_not_loaded(repo)
    return sync_merged(repo, numbers, log=log) if numbers else None

