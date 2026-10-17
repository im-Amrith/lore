"""lore-mcp: the Lore tools over MCP (Python MCP SDK 2.x, MCPServer): the ten from docs/PLAN.md,
plus data_version and Steward's work board (open_tasks, claim_task, save_draft, release_task,
get_playbook).

Run over stdio:  uv run --directory backend python -m lore.mcp_server
Each tool is a thin wrapper over lore.mcp_server.tools; see that module for the envelope
every tool returns (results, nodes, edges, sources, cypher). The docstrings below are what
the agent's LLM sees when it picks a tool, so they say what to pass and what comes back.
"""

import functools
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from lore.mcp_server import tools as _tools

INSTRUCTIONS = """Lore answers who owns, who knows and why-was-this-decided questions from a GitHub org's
history stored in FalkorDB. Every tool takes `org` (e.g. FalkorDB, im-Amrith) to select its graph.
Start with find_entities to turn names into node ids, then call the tool for the intent. Build answers
only from returned nodes and cite their ids; `sources` maps ids to links. Decisions in
`pending_proposals` are not merged and must never be presented as current; `history` is superseded."""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = MCPServer("lore-mcp", instructions=INSTRUCTIONS)


class _Expected:
    """tools.X, but expected failures (a refused write, an unknown org or module id, a bad
    argument) become ToolError, whose message reaches the agent. Anything else stays a crash,
    which the SDK reports without its text."""

    def __getattr__(self, name: str):
        fn = getattr(_tools, name)

        @functools.wraps(fn)
        def call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (PermissionError, ValueError) as exc:
                raise ToolError(str(exc)) from exc
        return call


t = _Expected()


@mcp.tool(annotations=READ)
def find_entities(org: str, text: str, labels: list[str] | None = None, limit: int = 5) -> dict[str, Any]:
    """Find starting nodes for a question: decisions (vector + full-text), doc chunks, PRs, issues,
    plus modules and topics named in it. labels limits the search to some of
    Decision, Doc, PullRequest, Issue, Module, Topic. Decisions come split into decisions (current),
    pending_proposals (not merged) and history."""
    return t.find_entities(org, text, labels, limit)


@mcp.tool(annotations=READ)
def trace_decision(org: str, node_id: str, question: str | None = None) -> dict[str, Any]:
    """Why-trace: a decision's sources (PR / issue / doc), the issues they closed (top 6, ranked:
    closed and linking back first, then by closeness to question), who proposed and approved it,
    affected modules, superseded versions (history) and open or draft PRs that propose changing it
    (pending_proposals). node_id is a decision id or the id of the PR, issue or doc."""
    return t.trace_decision(org, node_id, question)


@mcp.tool(annotations=READ)
def find_experts(org: str, module_or_topic: str, since: str | None = None, min_score: float = 0.5) -> dict[str, Any]:
    """Who knows a module (id, path like graph/src/index, or last segment like parser) or a topic
    (e.g. link-cache): ranked people with time-decayed scores and evidence PRs and commits.
    since (YYYY-MM-DD) keeps people active since then."""
    return t.find_experts(org, module_or_topic, since, min_score)


@mcp.tool(annotations=READ)
def module_owners(org: str, module: str) -> dict[str, Any]:
    """Who owns a module: CODEOWNERS owners (people or teams) compared with the active experts (each
    with up to 3 evidence PRs), the CODEOWNERS link (source id "codeowners"),
    paper owners (listed but inactive 12 months) and a mismatch flag. Says so when no owner is listed."""
    return t.module_owners(org, module)


@mcp.tool(annotations=READ)
def knowledge_risk(org: str, repo: str | None = None) -> dict[str, Any]:
    """Knowledge risk: modules with their bus factor (people who could maintain them) and
    single-expert flags, the top bridge people by betweenness, and the real working groups from
    label propagation. repo limits modules to one repo."""
    return t.knowledge_risk(org, repo)


@mcp.tool(annotations=READ)
def related_work(org: str, issue_id: str | None = None, text: str | None = None, limit: int = 5) -> dict[str, Any]:
    """For an issue (issue_id) or a new issue's text: similar past issues and the PRs that fixed
    them, the modules involved, decisions on those modules, and duplicate candidates."""
    return t.related_work(org, issue_id, text, limit)


@mcp.tool(annotations=READ)
def impact_radius(org: str, module: str) -> dict[str, Any]:
    """What else usually changes with a module: co-changed modules with counts and share of the
    module's commits, the active decisions on them, and their top experts."""
    return t.impact_radius(org, module)


@mcp.tool(annotations=READ)
def recall(org: str, user_id: str, topic: str | None = None, limit: int = 10) -> dict[str, Any]:
    """A user's past questions and the nodes their answers cited, and what changed since: newer
    decisions or references to those nodes. topic filters by question text or topic name."""
    return t.recall(org, user_id, topic, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                                      openWorldHint=False))
def remember(org: str, user_id: str, question: str, answer: str, cited_ids: list[str],
             cypher: str = "", intent: str = "general", session_id: str | None = None) -> dict[str, Any]:
    """Store a question and its answer in the user's memory, with CITED edges to the node ids the
    answer used. Returns the session id to reuse for follow-up questions."""
    return t.remember(org, user_id, question, answer, cited_ids, cypher, intent, session_id)


@mcp.tool(annotations=READ)
def data_version(org: str) -> dict[str, Any]:
    """A short fingerprint of the org graph's knowledge (counts and latest timestamps; memory
    excluded). It changes after a load, sync or derive, so a cached answer is valid while it holds."""
    return t.data_version(org)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                                      openWorldHint=True))
def post_triage(org: str, issue_id: str, draft: str, approval_token: str) -> dict[str, Any]:
    """Post a human-approved triage comment on an issue in the sandbox repo. Needs the approval
    token the UI issues for this exact issue and draft; any other repo is refused. With DRY_RUN=true
    (the default) the comment is only printed."""
    return t.post_triage(org, issue_id, draft, approval_token)


# Steward's work board. Not offered to the Navigator (agents/navigator.py AGENT_TOOLS).
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


@mcp.tool(annotations=READ)
def open_tasks(org: str, limit: int = 20) -> dict[str, Any]:
    """Open triage Tasks on the work board (each FOR an issue), oldest first."""
    return t.open_tasks(org, limit)


@mcp.tool(annotations=WRITE)
def claim_task(org: str, task_id: str, agent: str) -> dict[str, Any]:
    """Atomically claim an open Task for agent. claimed is false when another worker has it."""
    return t.claim_task(org, task_id, agent)


@mcp.tool(annotations=WRITE)
def save_draft(org: str, task_id: str, agent: str, draft: str, facts: dict[str, Any],
               playbook_version: int = 0, model: str = "") -> dict[str, Any]:
    """Store a draft triage comment and the facts it was written from on a Task agent has claimed."""
    return t.save_draft(org, task_id, agent, draft, facts, playbook_version, model)


@mcp.tool(annotations=WRITE)
def release_task(org: str, task_id: str, agent: str, error: str = "") -> dict[str, Any]:
    """Put a claimed Task back on the board (open), recording why the draft failed."""
    return t.release_task(org, task_id, agent, error)


@mcp.tool(annotations=READ)
def get_playbook(org: str, name: str = "triage") -> dict[str, Any]:
    """The triage Playbook (procedural memory): its steps, version and the Feedback that adjusted it."""
    return t.get_playbook(org, name)


def main() -> None:
    mcp.run("stdio")
