"""The deterministic grounding pass (lore/agents/ground.py): no LLM, no graph."""

from lore.agents import ground
from lore.agents.navigator import _url_to_id

PR = "https://github.com/FalkorDB/FalkorDB/pull/"

TRACE = ("trace_decision", {"decisions": [{
    "id": "decision:aa", "status": "active", "statement": "Remove all_nodes_matrix from the Rust engine",
    "sources": [{"id": "pr:FalkorDB/FalkorDB#2678", "url": PR + "2678"}],
    "issues": [{"id": "issue:FalkorDB/FalkorDB#2677", "rels": ["CLOSES"]},
               {"id": "issue:FalkorDB/FalkorDB#9", "rels": ["REFERENCES"]}]}]})

EXPERTS = ("find_experts", {
    "subject": {"kind": "module", "id": "module:FalkorDB:graph/src/parser", "path": "graph/src/parser"},
    "experts": [{"person_id": "person:AviAvni", "person": "AviAvni", "evidence": [PR + "3335", PR + "3104"]},
                {"person_id": "person:DvirDukhan", "person": "DvirDukhan", "evidence": [PR + "2262"]}]})

OWNERS = ("module_owners", {"module": {"id": "module:FalkorDB:graph/src/planner", "path": "graph/src/planner"},
                            "active_experts": [{"id": "person:AviAvni", "evidence": [PR + "2390"]}]})

KNOWN = {"decision:aa", "pr:FalkorDB/FalkorDB#2678", "issue:FalkorDB/FalkorDB#2677", "issue:FalkorDB/FalkorDB#9",
         "module:FalkorDB:graph/src/parser", "module:FalkorDB:graph/src/planner", "module:FalkorDB:graph",
         "person:AviAvni", "person:DvirDukhan", "pr:FalkorDB/FalkorDB#3335", "pr:FalkorDB/FalkorDB#2262",
         "pr:FalkorDB/FalkorDB#2390", "codeowners"}
LABELS = {"person:AviAvni": "Avi Avni"}


def s(text, *cites):
    return {"text": text, "cites": list(cites)}


def attach(sentences, intent, results):
    return ground.attach_mentions(sentences, intent, results, KNOWN, LABELS, _url_to_id)


def test_why_lead_is_the_statement_cited_to_its_path():
    lead = ground.why_lead([TRACE], KNOWN)
    assert lead["text"] == "Remove all_nodes_matrix from the Rust engine."
    # decision, the PR it was decided in, the issue that PR closes; not the merely referenced issue
    assert lead["cites"] == ["decision:aa", "pr:FalkorDB/FalkorDB#2678", "issue:FalkorDB/FalkorDB#2677"]


def test_why_lead_skips_decisions_that_are_not_active_or_not_returned():
    proposed = ("trace_decision", {"decisions": [{**TRACE[1]["decisions"][0], "status": "proposed"}]})
    assert ground.why_lead([proposed], KNOWN) is None
    assert ground.why_lead([TRACE], KNOWN - {"decision:aa"}) is None


def test_add_lead_goes_first_and_replaces_a_verbatim_repeat():
    lead = s("Remove all_nodes_matrix from the Rust engine.", "decision:aa")
    out = ground.add_lead([s("remove all_nodes_matrix from the rust engine", "decision:aa"), s("Because X.", "decision:aa")], lead)
    assert [x["text"] for x in out] == [lead["text"], "Because X."]


def test_person_gets_their_node_and_top_evidence_pr_in_who_answers():
    out = attach([s("Ask Avi Avni or DvirDukhan.")], "who-knows", [EXPERTS])
    assert out[0]["cites"] == ["person:AviAvni", "pr:FalkorDB/FalkorDB#3335", "person:DvirDukhan", "pr:FalkorDB/FalkorDB#2262"]


def test_no_evidence_pr_outside_who_and_owns_answers():
    out = attach([s("It was proposed by AviAvni.")], "why", [EXPERTS])
    assert out[0]["cites"] == ["person:AviAvni"]


def test_pr_issue_and_module_mentions():
    out = attach([s("PR #2678 closed issue #2677 in graph/src/parser; see #9.")], "why", [TRACE])
    assert set(out[0]["cites"]) == {"pr:FalkorDB/FalkorDB#2678", "issue:FalkorDB/FalkorDB#2677",
                                    "issue:FalkorDB/FalkorDB#9", "module:FalkorDB:graph/src/parser"}


def test_issue_number_does_not_cite_a_pr_with_that_number():
    out = attach([s("Issue #2678 is unrelated.")], "why", [TRACE])
    assert out[0]["cites"] == []


def test_unknown_nodes_are_never_added():
    out = attach([s("PR #1234 by SomeoneElse changed graph/src/udf.")], "who-knows", [EXPERTS])
    assert out[0]["cites"] == []


def test_one_segment_module_only_in_module_answers():
    assert attach([s("The graph stores nodes.")], "why", [])[0]["cites"] == []
    assert attach([s("graph has two experts.")], "risk", [])[0]["cites"] == ["module:FalkorDB:graph"]


def test_owner_sentences_cite_codeowners():
    out = attach([s("No owner is listed for graph/src/planner."), s("AviAvni works there.")], "owns", [OWNERS])
    assert "codeowners" in out[0]["cites"]
    assert out[1]["cites"] == ["person:AviAvni", "pr:FalkorDB/FalkorDB#2390"]
    assert "codeowners" in attach([s("CODEOWNERS lists the core team.")], "why", [])[0]["cites"]


def test_existing_cites_are_kept_and_not_duplicated():
    out = attach([s("AviAvni wrote it.", "person:AviAvni", "decision:aa")], "why", [])
    assert out[0]["cites"] == ["person:AviAvni", "decision:aa"]


def test_module_first_prepends_the_path_and_cites_it():
    mod = ground.subject_module([EXPERTS])
    out = ground.module_first([s("Ask AviAvni.", "person:AviAvni"), s("More.")], mod, KNOWN)
    assert out[0]["text"] == "On graph/src/parser: Ask AviAvni."
    assert out[0]["cites"] == ["person:AviAvni", "module:FalkorDB:graph/src/parser"]


def test_module_first_leaves_a_sentence_that_names_the_path():
    mod = ground.subject_module([OWNERS, EXPERTS])  # module_owners wins
    assert mod["path"] == "graph/src/planner"
    out = ground.module_first([s("graph/src/planner has no listed owner.")], mod, KNOWN)
    assert out[0]["text"] == "graph/src/planner has no listed owner."


def test_module_first_does_not_match_a_longer_path():
    mod = {"id": "module:FalkorDB:graph/src", "path": "graph/src"}
    out = ground.module_first([s("graph/src/parser is Avi's.")], mod, KNOWN | {"module:FalkorDB:graph/src"})
    assert out[0]["text"].startswith("On graph/src: ")


def test_why_lead_prefers_the_pr_decision_and_cites_the_same_choice_recorded_elsewhere():
    adr = {"id": "decision:adr", "status": "active", "statement": "Move the link cache to Redis",
           "modules": ["module:lore-sandbox:cache"], "sources": [{"id": "doc:x:docs/adr/0001.md"}], "issues": []}
    pr = {"id": "decision:pr", "status": "active", "statement": "Use a shared Redis link cache",
          "modules": ["module:lore-sandbox:cache"], "sources": [{"id": "pr:x#11"}],
          "issues": [{"id": "issue:x#1", "rels": ["CLOSES", "REFERENCES"]}]}
    other = {"id": "decision:other", "status": "active", "statement": "Unrelated", "modules": ["module:lore-sandbox:api"],
             "sources": [{"id": "pr:x#3"}], "issues": []}
    known = {"decision:adr", "decision:pr", "decision:other", "doc:x:docs/adr/0001.md", "pr:x#11", "issue:x#1", "pr:x#3"}
    lead = ground.why_lead([("trace_decision", {"decisions": [adr]}), ("trace_decision", {"decisions": [pr, other]})], known)
    assert lead["text"] == "Use a shared Redis link cache."
    assert lead["cites"] == ["decision:pr", "pr:x#11", "issue:x#1", "decision:adr", "doc:x:docs/adr/0001.md"]


PEOPLE_TRACE = ("trace_decision", {"decisions": [{**TRACE[1]["decisions"][0], "people": [
    {"id": "person:AviAvni", "login": "AviAvni", "role": "PROPOSED"},
    {"id": "person:DvirDukhan", "login": "DvirDukhan", "role": "APPROVED"}]}]})


def test_why_people_appended_only_when_nobody_is_named():
    out = ground.why_people([s("It was slow.", "decision:aa")], [PEOPLE_TRACE], KNOWN)
    assert out[-1] == s("Proposed by AviAvni; approved by DvirDukhan.", "decision:aa", "person:AviAvni", "person:DvirDukhan")
    kept = [s("Avi Avni proposed it.", "decision:aa")]
    assert ground.why_people(kept, [PEOPLE_TRACE], KNOWN) == kept


def test_owns_listed_names_codeowners_owners_when_missing():
    owners = ("module_owners", {"module": {"id": "module:lore-sandbox:analytics", "path": "analytics"},
                                "owners": [{"id": "person:im-Angel2305", "kind": "Person", "name": "im-Angel2305"}]})
    known = KNOWN | {"person:im-Angel2305"}
    out = ground.owns_listed([s("Priya Raman does the work."), s("More.")], [owners], known)
    assert out[1] == s("CODEOWNERS lists im-Angel2305 for analytics.", "codeowners", "person:im-Angel2305")
    named = [s("CODEOWNERS lists im-Angel2305, but Priya does the work.")]
    assert ground.owns_listed(named, [owners], known) == named
