import pytest

import lore.ingest.github_fetch as gf
from lore.ingest.github_fetch import (
    GitHub,
    ItemStream,
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
    """Serves PR pages of 2 from `prs` and records which pages were asked for."""

    def __init__(self, prs):
        self.log, self.calls, self.prs, self.pages_served = (lambda m: None), 0, prs, []

    def graphql(self, query, variables=None):
        start = int(variables["after"] or 0)
        self.pages_served.append(start // 2)
        page = [dict(n) for n in self.prs[start:start + 2]]
        has_next = start + 2 < len(self.prs)
        return {"repository": {"pullRequests": {
            "nodes": page, "pageInfo": {"hasNextPage": has_next, "endCursor": str(start + 2)}}}}


def _stream(gh, out, fail_on=None):
    def complete(node):
        if node["id"] == fail_on:
            raise RuntimeError("killed")
        node["done"] = True
    gh.stream("q", {}, ["repository", "pullRequests"], out, complete=complete)


def test_stream_resumes_mid_page(tmp_path):
    prs = [{"id": f"PR_{n}", "body": f"mail me at u{n}@example.com"} for n in range(5)]
    out_path = tmp_path / "prs.json"
    gh = FakeGitHub(prs)
    with pytest.raises(RuntimeError):
        _stream(gh, ItemStream(out_path, "2025-01-01"), fail_on="PR_3")  # dies inside page 1

    out = ItemStream(out_path, "2025-01-01")  # fresh process
    assert out.done_ids == {"PR_0", "PR_1", "PR_2"} and out.state["after"] == "2"
    _stream(gh, out)
    assert gh.pages_served == [0, 1, 1, 2]  # page 0 not re-fetched; page 1 re-read, PR_2 skipped
    assert out.finish() == 5
    items = gf.read_json(out_path)
    assert [i["id"] for i in items] == [f"PR_{n}" for n in range(5)]
    assert all(i["done"] and "[email]" in i["body"] for i in items)
    assert not (tmp_path / "prs.partial.jsonl").exists() and not (tmp_path / "prs.partial.state.json").exists()


def test_stream_drops_torn_last_line(tmp_path):
    out = ItemStream(tmp_path / "prs.json", "k")
    out.append({"id": "PR_0"})
    out.save_cursor(None)
    with (tmp_path / "prs.partial.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"id": "PR_1", "bo')  # killed mid-write
    out = ItemStream(tmp_path / "prs.json", "k")
    assert out.done_ids == {"PR_0"}
    out.append({"id": "PR_1"})
    assert out.finish() == 2


def test_stream_restarts_when_since_changes(tmp_path):
    out = ItemStream(tmp_path / "prs.json", "2025-01-01")
    out.append({"id": "PR_0"})
    out.save_cursor("2")
    out = ItemStream(tmp_path / "prs.json", "2024-01-01")
    assert out.done_ids == set() and out.state == {}


def test_raw_blob_ids():
    z = "0" * 40
    raw = (
        f":100644 100644 {'a' * 40} {'b' * 40} M\tsrc/x.c\n"
        f":000000 100644 {z} {'c' * 40} A\tsrc/new.c\n"
        f":160000 160000 {'d' * 40} {'e' * 40} M\tdeps/sub\n"
        "\n"
    )
    assert gf.raw_blob_ids(raw) == {"a" * 40, "b" * 40, "c" * 40}


def _commit(sha, name, email, pr=None):
    return {"sha": sha, "author_name": name, "author_email": email, "pr_number": pr}


def test_assign_logins_sandbox_cast():
    commits = [
        _commit("a", "Amrithesh S Menon", "me@home.example"),
        _commit("b", "im-Amrith", "1+im-Amrith@users.noreply.github.com"),
        _commit("c", "Amrithesh S Menon", "me@old-laptop.example"),  # unlinked email
        _commit("d", "Priya Raman", "priya@tern.invalid", pr=12),     # inside a PR im-Amrith opened
        _commit("e", "Marta Silva", "marta@tern.invalid"),
    ]
    counts = gf.assign_logins(commits, {"a": "im-Amrith", "b": "im-Amrith", "c": None, "d": None, "e": None})
    logins = {c["sha"]: (c["author_login"], c["login_source"]) for c in commits}
    assert logins == {
        "a": ("im-Amrith", "api"),
        "b": ("im-Amrith", "api"),
        "c": ("im-Amrith", "name_match"),
        "d": (None, "name_only"),
        "e": (None, "name_only"),
    }
    assert counts == {"api": 2, "noreply": 0, "name_match": 1, "name_only": 2}
    assert all("author_email" not in c for c in commits)


def test_assign_logins_ambiguous_name_stays_unlinked():
    commits = [_commit("a", "Sam", "x@a.example"), _commit("b", "Sam", "y@b.example"), _commit("c", "Sam", "z@c.example")]
    gf.assign_logins(commits, {"a": "sam-one", "b": "sam-two", "c": None})
    assert commits[2]["author_login"] is None
