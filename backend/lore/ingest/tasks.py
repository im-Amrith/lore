"""Librarian: open triage Tasks on the work board (docs/PLAN.md "Agents coordinate through the graph").

    open_triage_tasks(org, repo, issue_ids=None) -> [{task_id, status, issue_id}]

With no issue_ids, every open issue of the repo that has no triage Task yet gets one. The M13
webhook calls this for each new sandbox issue; Steward then claims and drafts the Task.
Only the sandbox repo is triaged (the Task leads to a comment there).
"""

from __future__ import annotations

import time
from typing import Any

from lore.graph.client import get_graph, query, ro_query
from lore.safety import check_sandbox_repo


def open_triage_tasks(org: str, repo: str, issue_ids: list[str] | None = None) -> list[dict[str, Any]]:
    check_sandbox_repo(repo)
    graph = get_graph(org)
    if issue_ids is None:
        issue_ids = [r["issue_id"] for r in ro_query(graph, "open_issues", {"repo": repo})]
    if not issue_ids:
        return []
    return query(graph, "task_open", {"issue_ids": issue_ids, "now": int(time.time())})
