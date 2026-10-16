"""The ten lore-mcp tools as plain functions (server.py registers them with MCP).

Every tool takes `org` (FalkorDB, im-Amrith, ...) which selects the graph lore_<org>, runs only
named queries from queries/, and returns the same envelope:

    {tool, org, graph,
     results,   # the tool's answer data
     nodes,     # ids of every node the results touch
     edges,     # {id, source, type, target} for every edge walked; id = "<src>-<TYPE>-><dst>"
     sources,   # node id -> GitHub URL, for every cited node that has one
     cypher}    # [{query, cypher, params, rows}] for every query that ran, in order

Edge ids are built from the endpoint ids, not FalkorDB's internal edge ids, which change
when a graph is reloaded. Decisions below DECISION_MIN_CONFIDENCE never appear (each query
filters them). Decisions are always split by status: `decisions` (active, current),
`pending_proposals` (open/draft PRs, never presented as current) and `history` (superseded).
"""

from __future__ import annotations

import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from lore.config import (
    BETWEENNESS_SAMPLING_SIZE,
    BETWEENNESS_SEED,
    BUS_FACTOR_MIN_SCORE,
    BUS_FACTOR_MIN_SHARE,
    BUS_FACTOR_WINDOW,
    CO_CHANGE_MAX_MODULES,
    DECISION_MIN_CONFIDENCE,
    DUPLICATE_MAX_DISTANCE,
    IMPACT_MIN_COUNT,
    RISK_BRIDGE_PEOPLE,
    RISK_MAX_MODULES,
    SIMILAR_MAX_DISTANCE,
    graph_name,
)
from lore.graph.client import get_db, get_graph, query, ro_query
from lore.graph.queries import load_query
from lore.graph.search import STOPWORDS, find_start, similar_issues
from lore.safety import check_approval, check_sandbox_repo, parse_issue_id

ENTITY_LABELS = ("Decision", "Doc", "PullRequest", "Issue", "Module", "Topic")
PARITY_NOTE = "parity decision: matches existing behaviour (the C engine or openCypher) rather than a new choice"


# ---------------------------------------------------------------- ids and urls

def url_for(node_id: str, org: str) -> str | None:
    """GitHub URL for a node id, when the id alone says where it lives (see CLAUDE.md ids)."""
    if not node_id:
        return None
    gh = "https://github.com"
    if m := re.match(r"^pr:(.+/.+)#(\d+)$", node_id):
        return f"{gh}/{m.group(1)}/pull/{m.group(2)}"
    if m := re.match(r"^issue:(.+/.+)#(\d+)$", node_id):
        return f"{gh}/{m.group(1)}/issues/{m.group(2)}"
    if m := re.match(r"^person:([A-Za-z0-9-]+(?:\[bot\])?)$", node_id):  # person:name:<slug> has no profile
        return f"{gh}/{m.group(1)}"
    if m := re.match(r"^module:([^:]+):(.+)$", node_id):
        repo, path = m.groups()
        return f"{gh}/{org}/{repo}" if path == "/" else f"{gh}/{org}/{repo}/tree/HEAD/{path}"
    if m := re.match(r"^doc:([^:]+/[^:]+):(.+)$", node_id):
        return f"{gh}/{m.group(1)}/blob/HEAD/{m.group(2)}"
    if m := re.match(r"^team:([^/]+)/(.+)$", node_id):
        return f"{gh}/orgs/{m.group(1)}/teams/{m.group(2)}"
    return None


def id_from_url(url: str) -> str | None:
    """Inverse of url_for for PR and issue URLs (queries return evidence as URLs)."""
    if m := re.match(r"^https://github\.com/([^/]+/[^/]+)/pull/(\d+)", url or ""):
        return f"pr:{m.group(1)}#{m.group(2)}"
    if m := re.match(r"^https://github\.com/([^/]+/[^/]+)/issues/(\d+)", url or ""):
        return f"issue:{m.group(1)}#{m.group(2)}"
    return None


def parse_since(since: str | int | None) -> int:
    """'2026-01-01', an epoch-seconds int (or numeric string), or None (= all time) -> epoch seconds."""
    if since in (None, "", 0):
        return 0
    if isinstance(since, int) or str(since).isdigit():
        return int(since)
    return int(datetime.fromisoformat(str(since)).replace(tzinfo=timezone.utc).timestamp())


def _short(node_id: str) -> str:
    """pr:FalkorDB/FalkorDB#2678 -> PR #2678, for notes."""
    if m := re.match(r"^(pr|issue):.+#(\d+)$", node_id or ""):
        return f"{'PR' if m.group(1) == 'pr' else 'issue'} #{m.group(2)}"
    return node_id


# ---------------------------------------------------------------- the envelope

def _show(params: dict[str, Any]) -> dict[str, Any]:
    """Params as shown in the envelope: embedding vectors are replaced by their size."""
    out = {}
    for k, v in params.items():
        if isinstance(v, list) and len(v) > 16 and all(isinstance(x, float) for x in v[:16]):
            out[k] = f"<vector, {len(v)} dims>"
        else:
            out[k] = v
    return out


class Run:
    """One tool call: the selected graph, plus everything the call ran and touched."""

    def __init__(self, tool: str, org: str):
        org = (org or "").strip()
        name = graph_name(org)
        if name not in get_db().list_graphs():
            raise ValueError(f"no graph for org {org!r} ({name}); load it first")
        self.tool, self.org, self.name = tool, org, name
        self.graph = get_graph(org)
        self.cypher: list[dict[str, Any]] = []
        self.nodes: dict[str, None] = {}  # insertion-ordered set
        self.edges: dict[str, dict[str, str]] = {}
        self.sources: dict[str, str] = {}

    def _record(self, name: str, params: dict, rows: list) -> list[dict[str, Any]]:
        self.cypher.append({"query": name, "cypher": load_query(name), "params": _show(params), "rows": len(rows)})
        return rows

    def ro(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return self._record(name, params, ro_query(self.graph, name, params))

    def rw(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return self._record(name, params, query(self.graph, name, params))

    def ro_query(self, graph, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Same signature as graph.client.ro_query, for the search helpers."""
        return self.ro(name, params)

    def node(self, node_id: str | None, url: str | None = None) -> None:
        if not node_id:
            return
        self.nodes[node_id] = None
        if url:  # a URL stored on the node beats one built from its id
            self.sources[node_id] = url
        elif node_id not in self.sources and (u := url_for(node_id, self.org)):
            self.sources[node_id] = u

    def edge(self, src: str | None, rel: str, dst: str | None) -> None:
        if not src or not dst:
            return
        self.node(src)
        self.node(dst)
        eid = f"{src}-{rel}->{dst}"
        self.edges[eid] = {"id": eid, "source": src, "type": rel, "target": dst}

    def result(self, results: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool": self.tool, "org": self.org, "graph": self.name, "results": results,
            "nodes": list(self.nodes), "edges": list(self.edges.values()),
            "sources": self.sources, "cypher": self.cypher,
        }


# ---------------------------------------------------------------- shared helpers

def _decision(row: dict[str, Any]) -> dict[str, Any]:
    """The fields every decision carries in a result, whatever query it came from."""
    d = {k: row.get(k) for k in ("id", "statement", "status", "kind", "confidence", "source_id", "source_url")
         if k in row}
    d["parity"] = row.get("kind") == "parity"
    if d["parity"]:
        d["note"] = PARITY_NOTE
    return d


def _split(decisions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """active -> decisions (current), proposed -> pending_proposals, anything else -> history."""
    out: dict[str, list] = {"decisions": [], "pending_proposals": [], "history": []}
    for d in decisions:
        status = d.get("status")
        if status == "active":
            out["decisions"].append(d)
        elif status == "proposed":
            out["pending_proposals"].append({**d, "note": f"{_short(d.get('source_id'))} is not merged; "
                                                       "this is a proposal, not a current decision"})
        else:
            out["history"].append(d)
    return out


def _resolve_module(run: Run, module: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Module id / path / last segment -> (best match, other matches)."""
    rows = run.ro("resolve_module", {"q": (module or "").strip().strip("/").lower() or "/", "limit": 5})
    return (rows[0], rows[1:]) if rows else (None, [])


def _terms(text: str, min_len: int = 3) -> list[str]:
    """Lowercased words (and a de-pluralised form) for module and topic name matching."""
    words = [w for w in re.split(r"[^a-z0-9_]+", (text or "").lower()) if len(w) >= min_len and w not in STOPWORDS]
    out: list[str] = []
    for w in words:
        for t in (w, w[:-2] if w.endswith("es") else None, w[:-1] if w.endswith("s") else None):
            if t and len(t) >= min_len and t not in out:
                out.append(t)
    return out


# ---------------------------------------------------------------- 1. find_entities

def find_entities(org: str, text: str, labels: list[str] | None = None, limit: int = 5) -> dict[str, Any]:
    """Query 2: starting nodes for a question (vector + full-text), plus modules and topics by name."""
    run = Run("find_entities", org)
    want = set(labels or ENTITY_LABELS)
    unknown = want - set(ENTITY_LABELS)
    if unknown:
        raise ValueError(f"unknown labels {sorted(unknown)}; use {list(ENTITY_LABELS)}")
    kinds = tuple(k for k, lab in (("decisions", "Decision"), ("docs", "Doc"), ("prs", "PullRequest"),
                                   ("issues", "Issue")) if lab in want)
    hits = find_start(run.graph, text, limit, ro=run.ro_query, kinds=kinds) if kinds else {}
    results: dict[str, Any] = {}

    if "decisions" in hits:
        decisions = []
        for r in hits["decisions"]:
            d = {**_decision(r), "rank": r["rank"], "distance": r["distance"], "sources": r["sources"]}
            decisions.append(d)
            run.node(d["id"], r.get("source_url"))
            for s in r["sources"]:
                run.edge(d["id"], "DECIDED_IN", s)
        results.update(_split(decisions))
    if "docs" in hits:
        results["docs"] = hits["docs"]
        for r in hits["docs"]:
            run.edge(r["id"], "PART_OF", r["doc_id"])
            run.node(r["doc_id"], r["url"])
    for key in ("prs", "issues"):
        if key in hits:
            results[key] = hits[key]
            for r in hits[key]:
                run.node(r["id"], r["url"])

    terms = _terms(text)
    if "Module" in want:
        results["modules"] = run.ro("entry_modules", {"terms": terms, "limit": limit}) if terms else []
        for r in results["modules"]:
            run.node(r["id"])
    if "Topic" in want:
        topic_terms = _terms(text, min_len=2)  # topic parts can be short: ci, api
        results["topics"] = run.ro("entry_topics", {"terms": topic_terms, "limit": limit}) if topic_terms else []
        for r in results["topics"]:
            run.node(f"topic:{r['name']}")
    return run.result(results)


# ---------------------------------------------------------------- 2. trace_decision

def _trace_entry(run: Run, r: dict[str, Any]) -> dict[str, Any]:
    d = {**_decision(r), "rationale": r["rationale"], "alternatives": r["alternatives"], "quote": r["quote"],
         "valid_from": r["valid_from"], "valid_to": r["valid_to"],
         "sources": r["sources"], "issues": r["issues"], "people": r["people"], "modules": r["modules"]}
    run.node(d["id"], r["source_url"])
    for s in r["sources"]:
        run.node(s["id"], s["url"])
        run.edge(d["id"], "DECIDED_IN", s["id"])
    issues: dict[str, dict] = {}  # a PR often both CLOSES and REFERENCES the same issue
    for i in r["issues"]:
        run.node(i["id"], i["url"])
        run.edge(i["via"], i["rel"], i["id"])
        entry = issues.setdefault(i["id"], {**{k: v for k, v in i.items() if k != "rel"}, "rels": []})
        entry["rels"].append(i["rel"])
    d["issues"] = list(issues.values())
    for p in r["people"]:
        run.edge(p["id"], p["role"], d["id"])
    for m in r["modules"]:
        run.edge(d["id"], "AFFECTS", m)
    return d


def trace_decision(org: str, node_id: str) -> dict[str, Any]:
    """Query 3: a decision's lineage. node_id is a Decision id or the PR / issue / doc it was decided in."""
    run = Run("trace_decision", org)
    params = {"node_id": node_id, "min_confidence": DECISION_MIN_CONFIDENCE}
    rows = run.ro("trace_decision", params)
    # A superseded decision is history; trace what replaced it too, so the current one is shown.
    seen = {r["id"] for r in rows}
    for newer_id in [n["id"] for r in rows for n in r["newer"] if n["id"] not in seen]:
        if newer_id not in seen:
            seen.add(newer_id)
            rows += run.ro("trace_decision", {**params, "node_id": newer_id})

    out: dict[str, list] = {"decisions": [], "pending_proposals": [], "history": []}
    pending: dict[str, dict] = {}
    for r in rows:
        d = _trace_entry(run, r)
        for older in r["history"]:
            run.edge(d["id"], "SUPERSEDES", older["id"])
            out["history"].append({**_decision(older), "superseded_by": d["id"], "valid_to": older["valid_to"]})
        for rv in r["rivals"]:
            run.node(rv["id"], rv["source_url"])
            for m in rv["shared_modules"]:
                run.edge(rv["id"], "AFFECTS", m)
            for t in rv["shared_topics"]:
                run.edge(d["id"], "ABOUT", f"topic:{t}")
                run.edge(rv["id"], "ABOUT", f"topic:{t}")
        if r["newer"] or r["status"] not in ("active", "proposed"):
            out["history"].append({**d, "superseded_by": [n["id"] for n in r["newer"]]})
        elif r["status"] == "proposed":
            # Never current. The rivals here are the active decisions it would replace.
            d["note"] = f"{_short(r['source_id'])} is not merged; this is a proposal, not a current decision"
            d["would_change"] = [rv["id"] for rv in r["rivals"]]
            pending[d["id"]] = d
        else:
            out["decisions"].append(d)
            for rv in r["rivals"]:
                p = pending.setdefault(rv["id"], {**_decision(rv), "would_change": [],
                                                  "shared_modules": rv["shared_modules"],
                                                  "shared_topics": rv["shared_topics"]})
                p["would_change"].append(d["id"])
                what = "draft " if rv["source_draft"] else "open " if rv["source_state"] == "open" else ""
                p["note"] = (f"{what}{_short(rv['source_id'])} proposes changing this "
                             f"(same module {', '.join(rv['shared_modules'])}, topic {', '.join(rv['shared_topics'])}); "
                             "it is not merged, so the current decision stands")
    out["pending_proposals"] = list(pending.values())
    out["history"] = list({h["id"]: h for h in out["history"]}.values())
    results: dict[str, Any] = {"found": bool(rows), **out}
    if not rows:
        results["message"] = (f"not found: no decision with confidence >= {DECISION_MIN_CONFIDENCE} "
                              f"is or was decided in {node_id}")
    return run.result(results)


# ---------------------------------------------------------------- 3. find_experts

def find_experts(org: str, module_or_topic: str, since: str | int | None = None) -> dict[str, Any]:
    """Query 5: ranked people for a module (EXPERT_IN) or, failing that, a topic (ABOUT PRs)."""
    run = Run("find_experts", org)
    since_at = parse_since(since)
    module, others = _resolve_module(run, module_or_topic)
    if module:
        rows = run.ro("who_knows", {"module": module["id"], "since": since_at})
        run.node(module["id"])
        commit_base = f"https://github.com/{org}/{module['repo']}/commit/"
        experts = []
        for r in rows:
            run.edge(r["person_id"], "EXPERT_IN", module["id"])
            for url in (r["evidence"] or []) + (r["evidence_reviews"] or []):
                run.node(id_from_url(url), url)
            for c in r["evidence_commits"] or []:
                run.edge(c, "TOUCHES", module["id"])
                run.sources[c] = commit_base + c.removeprefix("commit:")
            experts.append(r)
        return run.result({"subject": {"kind": "module", **module}, "experts": experts,
                           "other_matches": others, "since": since_at,
                           **({} if experts else {"message": f"not found: no one with score > 0.5 on {module['path']}"})})

    wanted = (module_or_topic or "").strip().lower()
    if found := run.ro("entry_topics", {"terms": [wanted, *re.split(r"[-\s]+", wanted)], "limit": 1}):
        topic = found[0]["name"]
        rows = run.ro("who_knows_topic", {"topic": topic, "since": since_at, "now": int(time.time())})
        for r in rows:
            run.node(r["person_id"])  # linked to the topic through the evidence PRs below
            for url in r["evidence"]:
                run.edge(id_from_url(url), "ABOUT", f"topic:{topic}")
                run.sources[id_from_url(url)] = url
        return run.result({"subject": {"kind": "topic", "name": topic}, "experts": rows, "since": since_at,
                           **({} if rows else {"message": f"not found: no one with score > 0.5 on topic {topic}"})})
    return run.result({"subject": None, "experts": [],
                       "message": f"not found: no module or topic named {module_or_topic!r}"})


# ---------------------------------------------------------------- 4. module_owners

def module_owners(org: str, module: str) -> dict[str, Any]:
    """Query 6: CODEOWNERS owners vs the people who actually work on a module."""
    run = Run("module_owners", org)
    m, others = _resolve_module(run, module)
    if not m:
        return run.result({"module": None, "message": f"not found: no module named {module!r}"})
    r = run.ro("module_owners", {"module": m["id"], "now": int(time.time())})[0]
    codeowners = f"https://github.com/{org}/{m['repo']}/blob/HEAD/CODEOWNERS"
    run.node(m["id"])
    for o in r["owners"]:
        run.edge(o["id"], "OWNS", m["id"])
    for e in r["active_experts"]:
        run.edge(e["id"], "EXPERT_IN", m["id"])
    names = {o["name"] for o in r["owners"]}
    top = r["active_experts"][0]["person"] if r["active_experts"] else None
    # Unknown when every owner is a team with no public members: we can't say who's on it.
    knowable = any(o["kind"] == "Person" for o in r["owners"])
    top_is_owner = (top in names) if (top and knowable) else None
    paper = [o["name"] for o in r["owners"] if o["paper"]]
    results = {
        "module": m, "listed_owner": r["listed_owner"], "owners": r["owners"],
        "active_experts": r["active_experts"], "paper_owners": paper,
        "top_expert_is_owner": top_is_owner,
        "mismatch": (not r["listed_owner"]) or bool(paper) or top_is_owner is False,
        "codeowners_url": codeowners, "other_matches": others,
    }
    if not r["listed_owner"]:
        results["message"] = f"no owner is listed for {m['path']} in CODEOWNERS"
    else:
        run.sources["codeowners"] = codeowners
    return run.result(results)


# ---------------------------------------------------------------- 5. knowledge_risk

def knowledge_risk(org: str, repo: str | None = None) -> dict[str, Any]:
    """Query 7 (bus factor) + query 8 (betweenness top 5, label-propagation working groups)."""
    run = Run("knowledge_risk", org)
    repo_name = (repo or "").split("/")[-1]
    rows = run.ro("bus_factor", {"now": int(time.time()), "min_score": BUS_FACTOR_MIN_SCORE,
                                 "min_share": BUS_FACTOR_MIN_SHARE, "window": BUS_FACTOR_WINDOW,
                                 "repo": repo_name})
    active = [r for r in rows if r["bus_factor"] > 0]
    modules = []
    for r in active[:RISK_MAX_MODULES]:
        run.node(r["module_id"])
        for pid in r["expert_ids"]:
            run.edge(pid, "EXPERT_IN", r["module_id"])
        modules.append({**r, "single_expert": r["bus_factor"] == 1})
    bridges = run.ro("betweenness", {"limit": RISK_BRIDGE_PEOPLE, "sampling_size": BETWEENNESS_SAMPLING_SIZE,
                                     "seed": BETWEENNESS_SEED})
    for b in bridges:
        run.node(b["id"])
    groups = run.ro("label_propagation", {})
    for g in groups:
        for pid in g["member_ids"]:
            run.node(pid)
    return run.result({
        "repo": repo_name or None,
        "modules": modules,
        "single_expert_modules": [m["module"] for m in modules if m["single_expert"]],
        "dormant_modules": len(rows) - len(active),
        "bridge_people": bridges,
        "working_groups": groups,
        "thresholds": {"min_score": BUS_FACTOR_MIN_SCORE, "min_share": BUS_FACTOR_MIN_SHARE,
                       "window_days": BUS_FACTOR_WINDOW // 86400},
    })


# ---------------------------------------------------------------- 6. related_work

def related_work(org: str, issue_id: str | None = None, text: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Query 9: similar issues (and where they were fixed), decisions on those modules, duplicates."""
    run = Run("related_work", org)
    if issue_id:
        found = run.ro("issue_text", {"issue_id": issue_id})
        if not found:
            return run.result({"message": f"not found: no issue {issue_id} in the graph"})
        issue = found[0]
        title, body = issue["title"], issue["body"] or ""
        run.node(issue_id, issue["url"])
    elif text:
        title, body = text, ""
    else:
        raise ValueError("give an issue_id or text")

    similar = similar_issues(run.graph, title, body, issue_id=issue_id, limit=limit,
                             max_distance=SIMILAR_MAX_DISTANCE, ro=run.ro_query)
    modules: list[str] = []
    for s in similar:
        run.node(s["id"], s["url"])
        for url in s["fixes"]:
            run.edge(id_from_url(url), "CLOSES", s["id"])
            run.sources[id_from_url(url)] = url
        for m in s["modules"]:
            if m not in modules:
                modules.append(m)
        s["duplicate_candidate"] = s["distance"] <= DUPLICATE_MAX_DISTANCE
    # Ranking: first decisions made in the PR that fixed a similar issue (nearest issue first;
    # the demo issue -> #3 -> PR 13's case-sensitive lookup), then by the nearest issue whose
    # fix touched one of the decision's modules.
    rank = {m: i for i, m in enumerate(modules)}
    fix_rank: dict[str, int] = {}
    for i, s in enumerate(similar):
        for url in s["fixes"]:
            fix_rank.setdefault(id_from_url(url), i)
    decisions = []
    if modules:
        for r in run.ro("module_decisions", {"modules": modules, "min_confidence": DECISION_MIN_CONFIDENCE,
                                             "limit": 20}):
            run.node(r["id"], r["source_url"])
            for m in r["modules"]:
                run.edge(r["id"], "AFFECTS", m)
            decisions.append({**_decision(r), "modules": r["modules"]})
        decisions.sort(key=lambda d: (fix_rank.get(d["source_id"], len(similar)), min(rank[m] for m in d["modules"])))
        decisions = decisions[:8]
    return run.result({
        "issue": {"id": issue_id, "title": title},
        "similar_issues": similar,
        "duplicate_candidates": [s["id"] for s in similar if s["duplicate_candidate"]],
        "modules": modules,
        **_split(decisions),
        "thresholds": {"similar_max_distance": SIMILAR_MAX_DISTANCE, "duplicate_max_distance": DUPLICATE_MAX_DISTANCE},
    })


# ---------------------------------------------------------------- 7. impact_radius

def impact_radius(org: str, module: str) -> dict[str, Any]:
    """Query 10: modules that usually change with this one, decisions on them, who knows them."""
    run = Run("impact_radius", org)
    m, others = _resolve_module(run, module)
    if not m:
        return run.result({"module": None, "message": f"not found: no module named {module!r}"})
    rows = run.ro("impact_radius", {"module": m["id"], "max_modules": CO_CHANGE_MAX_MODULES,
                                    "min_count": IMPACT_MIN_COUNT, "limit": 10,
                                    "min_confidence": DECISION_MIN_CONFIDENCE})
    run.node(m["id"])
    for r in rows:
        run.edge(m["id"], "CO_CHANGED", r["module_id"])
        for d in r["decisions"]:
            run.node(d["id"], d["source_url"])
            run.edge(d["id"], "AFFECTS", r["module_id"])
            d["parity"] = d.get("kind") == "parity"
            if d["parity"]:
                d["note"] = PARITY_NOTE
        for e in r["experts"]:
            run.edge(e["id"], "EXPERT_IN", r["module_id"])
    return run.result({"module": m, "co_changed": rows, "other_matches": others,
                       **({} if rows else {"message": f"not found: no module co-changed >= {IMPACT_MIN_COUNT} "
                                                      f"times with {m['path']}"})})


# ---------------------------------------------------------------- 8. recall

def recall(org: str, user_id: str, topic: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Query 11: this user's past questions, and what changed since in the nodes they were shown."""
    run = Run("recall", org)
    params = {"user_id": user_id, "topic": (topic or "").strip().lower(), "limit": limit}
    questions = run.ro("recall_questions", params)
    for q in questions:
        for k in q["cited"]:
            run.edge(q["answer_id"], "CITED", k)
    changes = run.ro("what_changed", params)
    for c in changes:
        run.node(c["newer_id"], c["newer_url"])
        run.edge(c["newer_id"], c["change"], c["cited_id"])
    return run.result({"user_id": user_id, "questions": questions, "changes": changes})


# ---------------------------------------------------------------- 9. remember (writes)

def remember(org: str, user_id: str, question: str, answer: str, cited_ids: list[str],
             cypher: str = "", intent: str = "general", session_id: str | None = None) -> dict[str, Any]:
    """Write memory: (User)-[:HAD]->(Session)-[:ASKED]->(Question)-[:ANSWERED_WITH]->(Answer)-[:CITED]->(k)."""
    if not user_id:
        raise ValueError("user_id is required")
    run = Run("remember", org)
    now = int(time.time())
    session_id = session_id or f"session:{user_id}:{datetime.fromtimestamp(now, timezone.utc):%Y-%m-%d}"
    qid, aid = f"question:{uuid.uuid4().hex[:16]}", f"answer:{uuid.uuid4().hex[:16]}"
    rows = run.rw("remember", {"user_id": user_id, "session_id": session_id, "question_id": qid, "answer_id": aid,
                               "question": question, "answer": answer, "cypher": cypher, "intent": intent,
                               "cited": list(dict.fromkeys(cited_ids or [])), "now": now})
    cited = rows[0]["cited"] if rows else 0
    run.edge(user_id, "HAD", session_id)
    run.edge(session_id, "ASKED", qid)
    run.edge(qid, "ANSWERED_WITH", aid)
    for k in cited_ids or []:
        run.edge(aid, "CITED", k)
    return run.result({"user_id": user_id, "session_id": session_id, "question_id": qid, "answer_id": aid,
                       "cited": cited, "cited_requested": len(set(cited_ids or []))})


# ---------------------------------------------------------------- 10. post_triage (dry run)

def post_triage(org: str, issue_id: str, draft: str, approval_token: str) -> dict[str, Any]:
    """Post an approved triage comment, only to SANDBOX_REPO. Dry run for now (M8): it checks the
    allowlist, the approval token and that the issue exists, then prints the comment instead of posting."""
    repo, number = parse_issue_id(issue_id)
    check_sandbox_repo(repo)  # raises WriteRefused before anything else happens
    check_approval(issue_id, draft, approval_token)
    run = Run("post_triage", org)
    found = run.ro("issue_text", {"issue_id": issue_id})
    if not found:
        raise ValueError(f"no issue {issue_id} in graph {run.name}")
    run.node(issue_id, found[0]["url"])
    # stdout is the MCP stdio channel, so the dry-run comment goes to stderr.
    print(f"[post_triage dry run] {repo}#{number}\n{draft}\n[end]", file=sys.stderr)
    return run.result({"dry_run": True, "posted": False, "repo": repo, "issue_number": number,
                       "issue_url": found[0]["url"], "comment": draft,
                       "would_post_to": f"https://api.github.com/repos/{repo}/issues/{number}/comments"})
