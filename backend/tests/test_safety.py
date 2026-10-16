import pytest

from lore.config import get_settings
from lore.safety import (
    WriteRefused,
    check_approval,
    check_sandbox_repo,
    make_approval_token,
    parse_issue_id,
)

SANDBOX = "im-Amrith/lore-sandbox"


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sandbox_repo", SANDBOX)
    monkeypatch.setattr(s, "triage_approval_secret", "test-secret")
    return s


def test_parse_issue_id():
    assert parse_issue_id("issue:im-Amrith/lore-sandbox#12") == (SANDBOX, 12)
    for bad in ("pr:im-Amrith/lore-sandbox#12", "issue:lore-sandbox#1", "issue:a/b#x", ""):
        with pytest.raises(ValueError):
            parse_issue_id(bad)


def test_allowlist_accepts_only_the_sandbox(settings):
    assert check_sandbox_repo(SANDBOX) == SANDBOX
    assert check_sandbox_repo("IM-AMRITH/Lore-Sandbox")  # GitHub names are case-insensitive
    for other in ("FalkorDB/FalkorDB", "im-Amrith/lore", "im-Amrith/lore-sandbox-2", "evil/im-Amrith/lore-sandbox"):
        with pytest.raises(WriteRefused):
            check_sandbox_repo(other)


def test_allowlist_refuses_everything_when_unset(settings, monkeypatch):
    monkeypatch.setattr(settings, "sandbox_repo", "")
    with pytest.raises(WriteRefused):
        check_sandbox_repo(SANDBOX)


def test_approval_token_binds_issue_and_exact_draft(settings):
    issue = "issue:im-Amrith/lore-sandbox#12"
    token = make_approval_token(issue, "Likely related to #3.")
    check_approval(issue, "Likely related to #3.", token)
    with pytest.raises(WriteRefused):
        check_approval(issue, "Likely related to #3. Edited after approval.", token)
    with pytest.raises(WriteRefused):
        check_approval("issue:im-Amrith/lore-sandbox#13", "Likely related to #3.", token)
    with pytest.raises(WriteRefused):
        check_approval(issue, "Likely related to #3.", "")


def test_no_secret_means_no_approvals(settings, monkeypatch):
    monkeypatch.setattr(settings, "triage_approval_secret", "")
    with pytest.raises(WriteRefused):
        make_approval_token("issue:im-Amrith/lore-sandbox#12", "x")
    with pytest.raises(WriteRefused):
        check_approval("issue:im-Amrith/lore-sandbox#12", "x", "anything")
