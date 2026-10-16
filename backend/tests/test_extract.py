import pytest

from lore.config import _parse_topics_md
from lore.ingest.extract import (
    Candidate,
    decision_id,
    quote_match,
    rank_modules,
    schema_for,
    strip_bot_blocks,
    validate,
)
from lore.llm.cache import CallCapExceeded, cache_get, cache_key, cache_put, count_call

CODERABBIT = """We fold deltas on every write because reads paid O(delta) forever.

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

* **New Features**
  * Added adaptive delta-folding controls.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->"""


def test_strip_coderabbit_block():
    out = strip_bot_blocks(CODERABBIT)
    assert out == "We fold deltas on every write because reads paid O(delta) forever."


def test_strip_unclosed_copilot_block_runs_to_end():
    text = "Human intro.\n<!-- START COPILOT CODING AGENT TIPS -->\nTips from the bot"
    assert strip_bot_blocks(text) == "Human intro."


def test_strip_cubic_and_template_comments_and_generated_line():
    text = ("Why: X.\n<!-- Closes #N or References #N -->\n"
            "<!-- This is an auto-generated description by cubic. -->\nbot\n"
            "<!-- End of auto-generated description by cubic. -->\n"
            "🤖 Generated with [Claude Code](https://claude.com/claude-code)\nAfter.")
    assert strip_bot_blocks(text) == "Why: X.\n\nAfter."


def test_strip_unmarked_coderabbit_heading():
    text = "Intro.\n\n## Summary by CodeRabbit\n* stuff\n\n## Testing\nran it"
    assert strip_bot_blocks(text) == "Intro.\n\n## Testing\nran it"


def test_rank_modules_by_files_and_cap():
    mods = ["module:R:/", "module:R:graph/src/parser", "module:R:graph/src", "module:R:docs"]
    files = ["graph/src/parser/a.rs", "graph/src/parser/b.rs", "graph/src/lib.rs", "README.md"]
    ranked = rank_modules(mods, files, cap=3)
    assert ranked == ["module:R:graph/src/parser", "module:R:/", "module:R:graph/src"]


def test_quote_match_ignores_markdown_and_breaks():
    text = "Outside `GRAPH.BULK`, deltas were never\nfolded into the **base** matrix."
    assert quote_match("deltas were never folded into the base matrix", text) == 1.0
    assert quote_match("because Rust is faster than C", text) < 0.5


def _cand(**kw):
    base = dict(id="pr:o/r#1", kind="pr", url="u", title="t", body="b", author="alice", author_id="person:alice",
                approvers=["bob"], modules=["module:r:api", "module:r:cache"], at=100, label="PR #1")
    base.update(kw)
    return Candidate(**base)


def test_validate_clamps_to_allowed_values_and_caps_unverified():
    c = _cand()
    text = "We use a shared Redis cache with a 24h TTL."
    raw = {"topics": ["link-cache", "made-up"], "decisions": [
        {"statement": "Use Redis", "rationale": "", "alternatives": [], "quote": "a shared Redis cache with a 24h TTL",
         "affected_modules": ["module:r:cache", "module:r:other"], "proposed_by": ["alice", "mallory"],
         "approved_by": ["bob", "eve"], "confidence": 0.9, "topics": ["link-cache"]},
        {"statement": "Rust is faster", "rationale": "speed", "alternatives": [], "quote": "Rust is much faster than C",
         "affected_modules": [], "proposed_by": [], "approved_by": [], "confidence": 0.8, "topics": []},
    ]}
    topics, ds = validate(raw, c, text, ["link-cache", "storage"], "m")
    assert topics == ["link-cache"]
    assert ds[0]["affected_modules"] == ["module:r:cache"]
    assert ds[0]["proposed_by"] == ["alice"] and ds[0]["approved_by"] == ["bob"]
    assert ds[0]["quote_verified"] and ds[0]["confidence"] == 0.9
    assert not ds[1]["quote_verified"] and ds[1]["confidence"] == 0.5 and ds[1]["llm_confidence"] == 0.8


def test_schema_empty_choice_lists_allow_nothing():
    s = schema_for(_cand(approvers=[], modules=[]), ["a"])
    item = s["properties"]["decisions"]["items"]["properties"]
    assert item["approved_by"]["maxItems"] == 0 and "enum" not in item["approved_by"]["items"]
    assert item["proposed_by"]["items"]["enum"] == ["alice"]


def test_decision_id_stable_across_whitespace():
    assert decision_id("pr:o/r#1", "Use  Redis.") == decision_id("pr:o/r#1", "use redis")


def test_parse_topics_md():
    md = ("| 1 | `query-execution` | Running a plan | `graph/src/runtime/` | `perf(runtime)` |\n"
          "**For the sandbox org**, use its own short list (see X): `link-cache`, `storage`.")
    topics, sandbox = _parse_topics_md(md)
    assert topics[0].id == "query-execution" and topics[0].paths == "`graph/src/runtime/`"
    assert sandbox == ["link-cache", "storage"]


def test_cache_roundtrip_and_call_cap(tmp_path):
    k = cache_key("m", "p", "i")
    assert cache_get("chat", k, root=tmp_path) is None
    cache_put("chat", k, {"a": 1}, root=tmp_path)
    assert cache_get("chat", k, root=tmp_path) == {"a": 1}
    assert count_call("chat", root=tmp_path, cap=2) == 1
    assert count_call("chat", root=tmp_path, cap=2) == 2
    with pytest.raises(CallCapExceeded):
        count_call("chat", root=tmp_path, cap=2)
    assert count_call("embed", root=tmp_path, cap=2) == 1  # kinds counted separately


def test_pick_issues_closes_first_then_body_order():
    from lore.ingest.extract import pick_issues
    issues = [{"id": f"i{n}", "number": n, "closes": n == 9} for n in (5, 2280, 9, 7)]
    body = "Fix #2280\n\nAlso resolved: #7, #5"
    assert [i["number"] for i in pick_issues(issues, body, cap=3)] == [9, 2280, 7]
