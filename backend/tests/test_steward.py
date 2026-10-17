"""Steward (M13): the pure parts. The graph side (claims, drafts) is checked by running it."""

import hashlib
import hmac

import pytest

from lore.agents.steward import (
    allowed_links,
    clean_draft,
    person,
    pick_owner,
    pick_related,
    pick_reviewer,
    primary_module,
)
from lore.config import get_settings
from lore.ingest.live import issue_row, upsert_issues
from lore.safety import WriteRefused, verify_webhook

SANDBOX = "im-Amrith/lore-sandbox"
GH = "https://github.com/im-Amrith/lore-sandbox"


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sandbox_repo", SANDBOX)
    monkeypatch.setattr(s, "github_webhook_secret", "hook-secret")
    return s


# ---------------------------------------------------------------- intake

def test_issue_row_from_rest_issue():
    row = issue_row({"number": 17, "title": "Links 404", "body": None, "state": "open",
                     "html_url": f"{GH}/issues/17", "created_at": "2026-10-17T10:00:00Z",
                     "user": {"login": "im-Amrith", "type": "User", "email": "x@example.com"},
                     "labels": [{"name": "bug"}]}, SANDBOX)
    assert row["id"] == "issue:im-Amrith/lore-sandbox#17"
    assert row["author_id"] == "person:im-Amrith" and row["labels"] == ["bug"] and row["body"] == ""
    assert row["opened_at"] == 1792231200 and row["closed_at"] is None
    assert "x@example.com" not in str(row)  # never store emails


def test_issue_row_skips_pull_requests_and_flags_bots():
    assert issue_row({"number": 1, "pull_request": {"url": "..."}}, SANDBOX) is None
    row = issue_row({"number": 2, "title": "t", "user": {"login": "dependabot[bot]", "type": "Bot"}}, SANDBOX)
    assert row["author_is_bot"] is True


def test_intake_refuses_other_repos(settings):
    with pytest.raises(WriteRefused):
        upsert_issues("FalkorDB", "FalkorDB/FalkorDB", [{"number": 1, "title": "t"}])


# ---------------------------------------------------------------- webhook signature

def _sign(body: bytes, secret: str = "hook-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_signature(settings):
    body = b'{"action": "opened"}'
    verify_webhook(body, _sign(body))
    for bad in (None, "", _sign(body, "other"), _sign(b'{"action": "edited"}')):
        with pytest.raises(WriteRefused):
            verify_webhook(body, bad)


def test_webhook_refused_without_secret(settings, monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    with pytest.raises(WriteRefused):
        verify_webhook(b"{}", _sign(b"{}", ""))


# ---------------------------------------------------------------- picking the facts

def test_person_mentions():
    assert person("person:im-Amrith")["mention"] == "@im-Amrith"
    p = person("person:name:priya-raman", "Priya Raman")
    assert p["mention"] == "Priya Raman" and p["login"] is None


def test_primary_module_skips_tests_and_docs():
    mods = ["module:lore-sandbox:tests", "module:lore-sandbox:api", "module:lore-sandbox:docs"]
    assert primary_module(mods) == "module:lore-sandbox:api"
    assert primary_module(["module:lore-sandbox:tests"]) == "module:lore-sandbox:tests"
    assert primary_module([]) is None


def _similar(n, d, fixes=()):
    return {"id": f"issue:{SANDBOX}#{n}", "number": n, "title": f"#{n}", "url": f"{GH}/issues/{n}",
            "state": "closed", "distance": d, "fixes": list(fixes), "duplicate_candidate": d <= 0.15}


def test_pick_related_keeps_nearest_and_close_ones():
    # CSV export check: #9 (0.19) and #4 (0.25) in, #3 (0.42) out.
    got = pick_related([_similar(9, 0.194), _similar(4, 0.248, [f"{GH}/pull/14"]), _similar(3, 0.417)])
    assert [r["number"] for r in got] == [9, 4]
    assert got[1]["fixed_by"] == [{"id": f"pr:{SANDBOX}#14", "url": f"{GH}/pull/14"}]
    # Demo issue: only the nearest, #3 at 0.35.
    assert [r["number"] for r in pick_related([_similar(3, 0.35), _similar(7, 0.397)])] == [3]


ANALYTICS = {
    "module": {"id": "module:lore-sandbox:analytics", "path": "analytics"}, "listed_owner": True,
    "owners": [{"id": "person:im-Angel2305", "name": "im-Angel2305", "kind": "Person", "paper": True}],
    "active_experts": [{"id": "person:name:priya-raman", "person": "Priya Raman", "score": 3.99,
                        "evidence": [f"{GH}/pull/14"]}],
}


def test_owner_is_who_does_the_work_with_paper_owner_warning():
    owner, warnings = pick_owner(ANALYTICS)
    assert owner["id"] == "person:name:priya-raman" and owner["mention"] == "Priya Raman"
    assert not owner["codeowner"]
    assert len(warnings) == 1 and warnings[0]["id"] == "person:im-Angel2305"
    assert "@im-Angel2305" in warnings[0]["text"] and "Priya Raman" in warnings[0]["text"]


def test_reviewer_falls_back_to_codeowners():
    owner, _ = pick_owner(ANALYTICS)
    r = pick_reviewer(owner, [{"person_id": "person:name:priya-raman", "person": "Priya Raman"}], ANALYTICS)
    assert r["id"] == "person:im-Angel2305" and "CODEOWNERS" in r["why"]


def test_reviewer_prefers_someone_who_reviewed():
    api = {"module": {"id": "module:lore-sandbox:api", "path": "api"}, "listed_owner": True,
           "owners": [{"id": "person:im-Amrith", "name": "im-Amrith", "kind": "Person", "paper": False}],
           "active_experts": [{"id": "person:im-Amrith", "person": "im-Amrith", "score": 3.99}]}
    owner, warnings = pick_owner(api)
    assert owner["id"] == "person:im-Amrith" and owner["codeowner"] and not warnings
    experts = [{"person_id": "person:im-Amrith", "person": "im-Amrith"},
               {"person_id": "person:im-Angel2305", "person": "im-Angel2305", "evidence_reviews": [f"{GH}/pull/11"]}]
    r = pick_reviewer(owner, experts, api)
    assert r["mention"] == "@im-Angel2305" and r["why"] == "reviewed PR #11 on api"


# ---------------------------------------------------------------- the draft's links

def test_clean_draft_drops_links_no_tool_returned():
    facts = {"related_issues": [{"url": f"{GH}/issues/3", "fixed_by": [{"url": f"{GH}/pull/13"}]}]}
    allowed = allowed_links(facts)
    assert allowed == {f"{GH}/issues/3", f"{GH}/pull/13"}
    text = (f"See [#3]({GH}/issues/3), fixed by {GH}/pull/13.\n"
            f"Also [#99]({GH}/issues/99) and https://evil.example/x")
    out, rejected = clean_draft(text, allowed)
    assert f"[#3]({GH}/issues/3)" in out and f"{GH}/pull/13" in out
    assert "#99" in out and f"{GH}/issues/99" not in out and "evil" not in out
    assert rejected == [f"{GH}/issues/99", "https://evil.example/x"]
