"""Librarian intake for new sandbox issues (M13). The API's 60 s poll and the GitHub webhook both
end here; Steward then claims the Tasks this opens.

    intake(repo)                      poll: GET /repos/{repo}/issues?state=open (REST), load what's new
    intake(repo, [issue], force=True) webhook: load (or reload) the issue from the event payload

An issue is loaded as an Issue node plus its author (queries/13_issue_upsert.cypher) and embedded
the same way the full load embeds issues (title + start of body), so related_work can match it.
Then every open issue without a Task gets one (ingest/tasks.py, the same step as scripts/tasks.py).
Only SANDBOX_REPO is taken in: its Tasks lead to comments there.
"""

from __future__ import annotations

from typing import Any

import httpx

from lore.config import get_settings
from lore.graph.client import get_graph, query, ro_query
from lore.ingest.embed import issue_text
from lore.ingest.normalize import epoch, is_bot_name, issue_id, person_id
from lore.ingest.tasks import open_triage_tasks
from lore.llm.embed import embed
from lore.safety import check_sandbox_repo

GITHUB_API = "https://api.github.com"


def issue_row(issue: dict[str, Any], repo: str) -> dict[str, Any] | None:
    """A GitHub REST issue (also the webhook's `issue`) -> a 13_issue_upsert row. None for pull
    requests, which the issues endpoint lists too. Only the author's login is kept, never an email."""
    if issue.get("pull_request"):
        return None
    user = issue.get("user") or {}
    login = user.get("login") or "ghost"  # deleted accounts show up as ghost on github.com
    opened = epoch(issue.get("created_at"))
    return {
        "id": issue_id(repo, issue["number"]), "number": issue["number"], "repo": repo,
        "title": issue.get("title") or "", "body": issue.get("body") or "",
        "state": (issue.get("state") or "open").lower(),
        "state_reason": (issue.get("state_reason") or "").lower() or None,
        "labels": [lb["name"] if isinstance(lb, dict) else str(lb) for lb in issue.get("labels") or []],
        "url": issue.get("html_url") or f"https://github.com/{repo}/issues/{issue['number']}",
        "opened_at": opened, "closed_at": epoch(issue.get("closed_at")),
        "author_id": person_id(login), "author_login": login,
        "author_is_bot": user.get("type") == "Bot" or is_bot_name(login),
    }


def fetch_open_issues(repo: str, per_page: int = 50) -> list[dict[str, Any]]:
    """The newest open issues of a public repo (one REST call; the token only raises the rate limit)."""
    token = get_settings().github_token
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "lore-librarian"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(f"{GITHUB_API}/repos/{repo}/issues", headers=headers, timeout=30,
                  params={"state": "open", "sort": "created", "direction": "desc", "per_page": per_page})
    r.raise_for_status()
    return r.json()


def upsert_issues(org: str, repo: str, issues: list[dict[str, Any]], force: bool = False) -> list[str]:
    """Load issues that are new to the graph (or have no embedding); force reloads all of them
    (an edited issue). Returns the ids loaded."""
    check_sandbox_repo(repo)
    rows = [r for i in issues if (r := issue_row(i, repo))]
    if not rows:
        return []
    graph = get_graph(org)
    if not force:
        known = {k["id"] for k in ro_query(graph, "issues_known", {"ids": [r["id"] for r in rows]}) if k["embedded"]}
        rows = [r for r in rows if r["id"] not in known]
    if not rows:
        return []
    query(graph, "issue_upsert", {"rows": rows})
    vecs = embed([issue_text(r["title"], r["body"]) for r in rows])
    query(graph, "embed_set_issues", {"rows": [{"id": r["id"], "vec": v} for r, v in zip(rows, vecs)]})
    return [r["id"] for r in rows]


def intake(repo: str, issues: list[dict[str, Any]] | None = None, force: bool = False) -> dict[str, Any]:
    """Load new issues of repo (fetched when not given) and open a triage Task for every open
    issue that has none. Returns {"loaded": [issue ids], "tasks": [new or existing Task rows]}."""
    check_sandbox_repo(repo)
    org = repo.split("/")[0]
    loaded = upsert_issues(org, repo, fetch_open_issues(repo) if issues is None else issues, force)
    tasks = open_triage_tasks(org, repo)
    return {"loaded": loaded, "tasks": tasks}
