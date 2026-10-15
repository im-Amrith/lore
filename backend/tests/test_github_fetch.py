import pytest

import lore.ingest.github_fetch as gf
from lore.ingest.github_fetch import (
    Checkpoint,
    GitHub,
    GIT_LOG_FORMAT,
    is_doc_path,
    login_from_noreply,
    parse_git_log,
    pr_number_from_subject,
    scrub,
)


def test_scrub_redacts_emails_recursively():
    data = {"body": "ping me at jane.doe+x@example.co.uk", "list": ["Co-authored-by: A <a@b.io>"], "n": 3}
    out = scrub(data)
    assert "@example" not in out["body"] and "[email]" in out["body"]
    assert out["list"] == ["Co-authored-by: A <[email]>"]
    assert out["n"] == 3


def test_scrub_keeps_team_handles():
    assert scrub("owned by @FalkorDB/falkordb-core") == "owned by @FalkorDB/falkordb-core"


def test_login_from_noreply():
    assert login_from_noreply("12345+AviAvni@users.noreply.github.com") == "AviAvni"
    assert login_from_noreply("swilly22@users.noreply.github.com") == "swilly22"
    assert login_from_noreply("49699333+dependabot[bot]@users.noreply.github.com") == "dependabot[bot]"
    assert login_from_noreply("avi@example.com") is None


def test_pr_number_from_subject():
    assert pr_number_from_subject("Drop all_nodes_matrix (#2678)") == 2678
    assert pr_number_from_subject("Merge pull request #12 from x/y") == 12
    assert pr_number_from_subject("see #12 for context") is None


def test_is_doc_path():
    assert is_doc_path("README.md")
    assert is_doc_path("src/graph/README.md")
    assert is_doc_path("docs/adr/0001-rust.md")
    assert is_doc_path("design/storage.mdx")
    assert not is_doc_path("src/docs.rs")
    assert not is_doc_path("CHANGELOG.md")


def test_parse_git_log():
    rec = GIT_LOG_FORMAT
    raw = (
        "\x1eabc123\x1fp1 p2\x1fAvi Avni\x1favi@example.com\x1f100\x1f200\x1fFix scan (#42)\n\nbody\x1d\n"
        "10\t2\tgraph/src/a.rs\n-\t-\tlogo.png\n"
        "\x1edef456\x1fabc123\x1fBob\x1fbob@x.io\x1f300\x1f400\x1fNo PR\x1d\n"
    )
    assert rec.startswith("%x1e")
    commits = parse_git_log(raw)
    assert len(commits) == 2
    c = commits[0]
    assert c["sha"] == "abc123" and c["parents"] == ["p1", "p2"]
    assert c["pr_number"] == 42 and c["subject"] == "Fix scan (#42)"
    assert c["files"] == [
        {"path": "graph/src/a.rs", "additions": 10, "deletions": 2},
        {"path": "logo.png", "additions": 0, "deletions": 0},
    ]
    assert commits[1]["files"] == [] and commits[1]["pr_number"] is None


class FakeGitHub(GitHub):
    """Serves PR pages of 2 from `prs`; raises once when asked for page `fail_page`."""

    def __init__(self, prs, fail_page=None):
        self.log, self.calls, self.prs, self.fail_page, self.pages_served = (lambda m: None), 0, prs, fail_page, []

    def graphql(self, query, variables=None):
        start = int(variables["after"] or 0)
        if start // 2 == self.fail_page:
            self.fail_page = None
            raise RuntimeError("network down")
        self.pages_served.append(start // 2)
        page = self.prs[start:start + 2]
        has_next = start + 2 < len(self.prs)
        return {"repository": {"pullRequests": {
            "nodes": page, "pageInfo": {"hasNextPage": has_next, "endCursor": str(start + 2)}}}}


def test_paginate_resumes_from_checkpoint(tmp_path):
    prs = [{"number": n} for n in range(5)]
    cp = Checkpoint(tmp_path / "prs.partial.json", "2025-01-01")
    gh = FakeGitHub(prs, fail_page=1)
    with pytest.raises(RuntimeError):
        gh.paginate("q", {}, ["repository", "pullRequests"], checkpoint=cp)

    cp = Checkpoint(tmp_path / "prs.partial.json", "2025-01-01")  # fresh process
    assert [n["number"] for n in cp.state["nodes"]] == [0, 1]
    nodes = gh.paginate("q", {}, ["repository", "pullRequests"], checkpoint=cp)
    assert [n["number"] for n in nodes] == [0, 1, 2, 3, 4]
    assert gh.pages_served == [0, 1, 2]  # page 0 not re-fetched
    assert Checkpoint(tmp_path / "prs.partial.json", "2025-01-01").state["listed"] is True


def test_checkpoint_ignored_when_since_changes(tmp_path):
    Checkpoint(tmp_path / "x.partial.json", "2025-01-01").save(nodes=[{"number": 1}])
    assert Checkpoint(tmp_path / "x.partial.json", "2024-01-01").state == {}


def test_complete_all_skips_done_nodes(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(gf, "_complete_nested", lambda gh, t, node, nested: seen.append(node["number"]))
    nodes = [{"number": 1, "_done": True}, {"number": 2}]
    out = gf._complete_all(FakeGitHub([]), "PullRequest", nodes, {}, None, "PRs")
    assert seen == [2] and all("_done" not in n for n in out)
