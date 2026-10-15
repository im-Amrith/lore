from lore.ingest.github_fetch import (
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
