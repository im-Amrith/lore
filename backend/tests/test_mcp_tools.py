"""lore-mcp tools against the loaded graphs: one test per tool on the sandbox graph
(lore_im-amrith), plus smoke tests on FalkorDB. Skipped when FalkorDB or the graph is missing.
Expected values come from docs/SANDBOX_STORY.md and docs/golden_set.yaml."""

import uuid

import pytest

from lore.config import get_settings, graph_name
from lore.graph.queries import load_query
from lore.mcp_server import tools as t
from lore.safety import WriteRefused, make_approval_token

SANDBOX = "im-Amrith"
REPO = "im-Amrith/lore-sandbox"
PR = f"pr:{REPO}#"


def _graphs() -> list[str]:
    try:
        from lore.graph.client import get_db
        return get_db().list_graphs()
    except Exception:
        return []


GRAPHS = _graphs()
needs_sandbox = pytest.mark.skipif(graph_name(SANDBOX) not in GRAPHS, reason="sandbox graph not loaded")
needs_falkordb = pytest.mark.skipif(graph_name("FalkorDB") not in GRAPHS, reason="FalkorDB graph not loaded")


def check_envelope(env: dict, tool: str) -> dict:
    """Every tool: results, touched node + edge ids, source URLs, and the Cypher that ran."""
    assert env["tool"] == tool and env["graph"].startswith("lore_")
    assert set(env) >= {"results", "nodes", "edges", "sources", "cypher"}
    assert env["cypher"], "no query recorded"
    for c in env["cypher"]:
        assert c["cypher"] == load_query(c["query"])  # only named queries from queries/
    nodes = set(env["nodes"])
    for e in env["edges"]:
        assert e["id"] == f"{e['source']}-{e['type']}->{e['target']}"
        assert e["source"] in nodes and e["target"] in nodes
    assert all(u.startswith("https://github.com/") for u in env["sources"].values())
    return env["results"]


# ---------------------------------------------------------------- pure helpers

def test_url_for_ids():
    assert t.url_for("pr:FalkorDB/FalkorDB#2678", "FalkorDB") == "https://github.com/FalkorDB/FalkorDB/pull/2678"
    assert t.url_for("issue:a/b#3", "a") == "https://github.com/a/b/issues/3"
    assert t.url_for("person:AviAvni", "FalkorDB") == "https://github.com/AviAvni"
    assert t.url_for("person:name:marta-silva", SANDBOX) is None  # no GitHub login, no profile link
    assert t.url_for("module:FalkorDB:graph/src/index", "FalkorDB") == \
        "https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/index"
    assert t.url_for("module:lore-sandbox:/", SANDBOX) == "https://github.com/im-Amrith/lore-sandbox"
    assert t.url_for("team:FalkorDB/falkordb-core", "FalkorDB") == "https://github.com/orgs/FalkorDB/teams/falkordb-core"
    assert t.url_for("decision:abc", "FalkorDB") is None
    assert t.id_from_url("https://github.com/FalkorDB/FalkorDB/pull/2678") == "pr:FalkorDB/FalkorDB#2678"


def test_parse_since():
    assert t.parse_since(None) == 0
    assert t.parse_since("2026-01-01") == 1767225600
    assert t.parse_since(1767225600) == t.parse_since("1767225600") == 1767225600


def test_unknown_org_is_refused():
    with pytest.raises(ValueError):
        t.knowledge_risk("no-such-org-xyz")


# ---------------------------------------------------------------- one test per tool (sandbox)

@needs_sandbox
def test_find_entities():
    r = check_envelope(t.find_entities(SANDBOX, "Why do we cache links in Redis?"), "find_entities")
    assert r["decisions"][0]["source_id"] == PR + "11"
    assert all(d["status"] == "active" for d in r["decisions"])
    # Draft PR #16's decision may be found, but only ever as a pending proposal.
    assert all(d["status"] == "proposed" for d in r["pending_proposals"])
    assert PR + "16" not in {d["source_id"] for d in r["decisions"]}
    assert "module:lore-sandbox:cache" in {m["id"] for m in r["modules"]}
    assert "link-cache" in {x["name"] for x in r["topics"]}


@needs_sandbox
def test_find_entities_labels():
    r = check_envelope(t.find_entities(SANDBOX, "cache", labels=["Module"]), "find_entities")
    assert set(r) == {"modules"}
    with pytest.raises(ValueError):
        t.find_entities(SANDBOX, "cache", labels=["Commit"])


@needs_sandbox
def test_trace_decision_with_pending_proposal():
    env = t.trace_decision(SANDBOX, PR + "11")
    r = check_envelope(env, "trace_decision")
    [d] = r["decisions"]
    assert d["status"] == "active" and d["kind"] == "architecture" and not d["parity"]
    assert "issue:im-Amrith/lore-sandbox#1" in {i["id"] for i in d["issues"]}  # PR 11 closes #1
    roles = {(p["login"], p["role"]) for p in d["people"]}
    assert ("im-Amrith", "PROPOSED") in roles and ("im-Angel2305", "APPROVED") in roles
    # Draft PR #16 proposes changing it: listed separately, never as current.
    [p] = r["pending_proposals"]
    assert p["source_id"] == PR + "16" and p["status"] == "proposed"
    assert p["note"].startswith("draft PR #16 proposes changing this") and d["id"] in p["would_change"]
    assert r["history"] == []
    assert env["sources"][PR + "11"] == "https://github.com/im-Amrith/lore-sandbox/pull/11"


@needs_sandbox
def test_trace_decision_on_the_proposal_itself():
    r = check_envelope(t.trace_decision(SANDBOX, PR + "16"), "trace_decision")
    assert r["decisions"] == []  # a proposed decision is never current
    [p] = r["pending_proposals"]
    assert "not merged" in p["note"]
    assert len(p["would_change"]) == 2  # PR 11's decision and ADR 0001's


@needs_sandbox
def test_trace_decision_not_found():
    r = check_envelope(t.trace_decision(SANDBOX, "issue:im-Amrith/lore-sandbox#7"), "trace_decision")
    assert r["found"] is False and r["message"].startswith("not found")


@needs_sandbox
def test_find_experts_module_and_topic():
    r = check_envelope(t.find_experts(SANDBOX, "storage"), "find_experts")
    assert r["subject"]["id"] == "module:lore-sandbox:storage"
    assert r["experts"][0]["person"] == "Marta Silva"  # every storage commit is Marta's (s03)
    assert r["experts"][0]["evidence_commits"]
    r = check_envelope(t.find_experts(SANDBOX, "link-cache"), "find_experts")
    assert r["subject"] == {"kind": "topic", "name": "link-cache"}
    assert r["experts"][0]["person"] == "im-Amrith"
    r = check_envelope(t.find_experts(SANDBOX, "storage", since="2999-01-01"), "find_experts")
    assert r["experts"] == [] and r["message"].startswith("not found")


@needs_sandbox
def test_module_owners_paper_owner():
    env = t.module_owners(SANDBOX, "analytics")
    r = check_envelope(env, "module_owners")
    # s02: CODEOWNERS lists the reviewer, but all analytics commits are Priya's.
    assert r["paper_owners"] == ["im-Angel2305"]
    assert r["active_experts"][0]["person"] == "Priya Raman"
    assert r["mismatch"] is True and r["top_expert_is_owner"] is False
    assert {"source": "person:im-Angel2305", "type": "OWNS"}.items() <= env["edges"][0].items()


@needs_sandbox
def test_knowledge_risk():
    r = check_envelope(t.knowledge_risk(SANDBOX), "knowledge_risk")
    storage = next(m for m in r["modules"] if m["module"] == "storage")
    assert storage["single_expert"] and storage["experts"] == ["Marta Silva"]  # s03
    assert "storage" in r["single_expert_modules"]
    # Two collaborators only: nobody sits between others, and no group bigger than one forms.
    assert r["bridge_people"] == [] and isinstance(r["working_groups"], list)
    assert check_envelope(t.knowledge_risk(SANDBOX, repo="nope"), "knowledge_risk")["modules"] == []


@needs_sandbox
def test_related_work_demo_issue():
    text = ("Links with capital letters 404 in the mobile app. Opening /Xk9fT2a from the iOS app shows "
            "'not found'; the same link works on desktop.")
    r = check_envelope(t.related_work(SANDBOX, text=text), "related_work")
    assert r["similar_issues"][0]["number"] == 3  # closed by PR 13, same api/ module
    assert "module:lore-sandbox:api" in r["modules"]
    assert r["decisions"][0]["source_id"] == PR + "13"
    assert r["duplicate_candidates"] == []  # related, not the same bug
    assert all(d["status"] == "proposed" for d in r["pending_proposals"])


@needs_sandbox
def test_related_work_by_issue_id_and_duplicate():
    r = check_envelope(t.related_work(SANDBOX, issue_id="issue:im-Amrith/lore-sandbox#6"), "related_work")
    assert "issue:im-Amrith/lore-sandbox#6" not in {s["id"] for s in r["similar_issues"]}
    assert r["similar_issues"][0]["number"] == 1
    r = t.related_work(SANDBOX, text="Redirect returns 500 for codes with uppercase letters")["results"]
    assert r["duplicate_candidates"] == ["issue:im-Amrith/lore-sandbox#3"]


@needs_sandbox
def test_impact_radius():
    r = check_envelope(t.impact_radius(SANDBOX, "api"), "impact_radius")
    assert r["module"]["id"] == "module:lore-sandbox:api"
    assert isinstance(r["co_changed"], list)
    assert t.impact_radius(SANDBOX, "no-such-module")["results"]["message"].startswith("not found")


@needs_sandbox
def test_remember_then_recall():
    """remember writes memory nodes; recall reads them back for that user only."""
    from lore.graph.client import get_graph
    user = f"test:mcp:{uuid.uuid4().hex[:8]}"
    try:
        env = t.remember(SANDBOX, user, "Why do we cache links in Redis?", "Because ... [PR 11]",
                         [PR + "11", "issue:im-Amrith/lore-sandbox#1", "decision:missing"], intent="why")
        w = check_envelope(env, "remember")
        assert w["cited"] == 2 and w["cited_requested"] == 3  # the unknown id is skipped
        r = check_envelope(t.recall(SANDBOX, user), "recall")
        [q] = r["questions"]
        assert q["question"] == "Why do we cache links in Redis?" and q["session_id"] == w["session_id"]
        assert set(q["cited"]) == {PR + "11", "issue:im-Amrith/lore-sandbox#1"}
        assert r["changes"] == []  # nothing newer yet (M15 adds SUPERSEDES)
        assert check_envelope(t.recall(SANDBOX, user, topic="redis"), "recall")["questions"]
        assert check_envelope(t.recall(SANDBOX, user, topic="analytics"), "recall")["questions"] == []
        assert t.recall(SANDBOX, user + "-other")["results"]["questions"] == []  # per-user memory
    finally:
        get_graph(SANDBOX).query(
            "MATCH (u:User {id: $u}) OPTIONAL MATCH (u)-[:HAD]->(s:Session) "
            "OPTIONAL MATCH (s)-[:ASKED]->(q:Question) OPTIONAL MATCH (q)-[:ANSWERED_WITH]->(a:Answer) "
            "DETACH DELETE u, s, q, a", {"u": user})


@pytest.fixture
def approvals(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sandbox_repo", REPO)
    monkeypatch.setattr(s, "triage_approval_secret", "test-secret")


@needs_sandbox
def test_post_triage_dry_run(approvals, capsys):
    issue, draft = "issue:im-Amrith/lore-sandbox#6", "Likely related to #1 (closed by PR 11)."
    env = t.post_triage(SANDBOX, issue, draft, make_approval_token(issue, draft))
    r = check_envelope(env, "post_triage")
    assert r["dry_run"] is True and r["posted"] is False and r["comment"] == draft
    assert draft in capsys.readouterr().err  # printed to stderr, never stdout (the MCP channel)


@needs_sandbox
def test_post_triage_refuses_other_repos_and_bad_tokens(approvals):
    draft = "Looks like a duplicate."
    real = "issue:FalkorDB/FalkorDB#2677"
    with pytest.raises(WriteRefused):  # even with a token that is valid for that issue + draft
        t.post_triage("FalkorDB", real, draft, make_approval_token(real, draft))
    issue = "issue:im-Amrith/lore-sandbox#6"
    with pytest.raises(WriteRefused):
        t.post_triage(SANDBOX, issue, draft, "not-a-token")
    with pytest.raises(WriteRefused):  # approved draft, edited afterwards
        t.post_triage(SANDBOX, issue, draft + " Edited.", make_approval_token(issue, draft))


# ---------------------------------------------------------------- smoke tests on FalkorDB

@needs_falkordb
def test_smoke_trace_decision_2678():
    r = check_envelope(t.trace_decision("FalkorDB", "pr:FalkorDB/FalkorDB#2678"), "trace_decision")
    [d] = r["decisions"]
    assert "all_nodes_matrix" in d["statement"]
    assert ("AviAvni", "PROPOSED") in {(p["login"], p["role"]) for p in d["people"]}
    assert "issue:FalkorDB/FalkorDB#2677" in {i["id"] for i in d["issues"]}
    assert "module:FalkorDB:graph/src/graph" in d["modules"]  # golden q01 path


@needs_falkordb
def test_smoke_find_experts_index():
    r = check_envelope(t.find_experts("FalkorDB", "graph/src/index"), "find_experts")
    assert [e["person"] for e in r["experts"][:2]] == ["DvirDukhan", "AviAvni"]  # golden q05
    assert t.find_experts("FalkorDB", "index")["results"]["subject"]["id"] == "module:FalkorDB:graph/src/index"


@needs_falkordb
def test_smoke_impact_radius_parser():
    r = check_envelope(t.impact_radius("FalkorDB", "parser"), "impact_radius")
    top2 = {x["module"] for x in r["co_changed"][:2]}
    assert top2 == {"graph/src/planner", "graph/src/runtime"}  # golden q10, either order


@needs_falkordb
def test_trace_ranks_linked_issues_closes_and_links_back_first():
    # PR #2279 CLOSES 116 issues; its tracking issue #2280 is the only one linking back (golden q03).
    r = check_envelope(t.trace_decision("FalkorDB", "pr:FalkorDB/FalkorDB#2279",
                                        question="Why are there two branches, main and master?"), "trace_decision")
    [d] = r["decisions"]
    assert d["issue_count"] == 116 and len(d["issues"]) == 6
    assert d["issues"][0]["id"] == "issue:FalkorDB/FalkorDB#2280" and d["issues"][0]["links_back"]
    assert [i["distance"] for i in d["issues"][1:]] == sorted(i["distance"] for i in d["issues"][1:])


@needs_falkordb
def test_module_owners_always_cites_codeowners_and_gives_evidence():
    env = t.module_owners("FalkorDB", "planner")
    r = check_envelope(env, "module_owners")
    assert r["listed_owner"] is False  # golden q08: no owner listed, and CODEOWNERS is still the source
    assert env["sources"]["codeowners"] == "https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS"
    top = r["active_experts"][0]
    assert top["person"] == "AviAvni" and 1 <= len(top["evidence"]) <= 3
    assert all(env["sources"][f"pr:FalkorDB/FalkorDB#{u.rsplit('/', 1)[1]}"] == u for u in top["evidence"])
