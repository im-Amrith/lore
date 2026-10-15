from lore.ingest.modules import module_path, parse_codeowners, rule_module
from lore.ingest.normalize import (
    RefIndex,
    canonical_login,
    commit_pr_links,
    find_references,
    is_bot_name,
    person_id,
    person_name_id,
    pr_id,
)

SANDBOX = "im-Amrith/lore-sandbox"
FALKOR = "FalkorDB/FalkorDB"


# --- ids -------------------------------------------------------------------

def test_ids():
    assert pr_id(FALKOR, 2678) == "pr:FalkorDB/FalkorDB#2678"
    assert person_id("AviAvni") == "person:AviAvni"
    assert person_name_id("Priya Raman") == "person:name:priya-raman"
    assert person_name_id("Marta Silva") == "person:name:marta-silva"
    assert person_name_id("José Núñez") == "person:name:jose-nunez"


def test_bots():
    assert canonical_login("dependabot[bot]") == "dependabot"
    assert person_id("dependabot[bot]") == person_id("dependabot")
    assert is_bot_name("github-actions[bot]") and is_bot_name("Copilot") and is_bot_name("dependabot")
    assert not is_bot_name("AviAvni")


# --- modules ---------------------------------------------------------------

def test_module_default_two_levels():
    assert module_path("analytics/clicks.py", SANDBOX) == "analytics"
    assert module_path("src/serializers/encoder/v14.c", "x/y") == "src/serializers"
    assert module_path("README.md", SANDBOX) == "/"


def test_module_falkordb_engine_three_levels():
    assert module_path("graph/src/index/mod.rs", FALKOR) == "graph/src/index"
    assert module_path("graph/src/parser/ast/expr.rs", FALKOR) == "graph/src/parser"
    assert module_path("graph/src/lib.rs", FALKOR) == "graph/src"
    assert module_path("graph/benches/x.rs", FALKOR) == "graph/benches"


def test_codeowners_dirs_override():
    rules = parse_codeowners("# owners\n/docs/  @im-Amrith\n/build/** @FalkorDB/falkordb-core\n/CODEOWNERS @a\n*.md @b\n")
    dirs = [r.directory for r in rules if r.directory]
    assert dirs == ["docs", "build"]
    assert module_path("docs/adr/0001-link-cache.md", SANDBOX, dirs) == "docs"
    assert module_path("build/docker/Dockerfile", FALKOR, dirs) == "build"
    assert rule_module(rules[2], FALKOR, dirs) == "/"       # a root file
    assert rule_module(rules[3], FALKOR, dirs) is None      # globs own no single module
    assert rules[1].owners == ["@FalkorDB/falkordb-core"]


def test_codeowners_skips_emails():
    assert parse_codeowners("/api/ @me [email]")[0].owners == ["@me"]


# --- references --------------------------------------------------------------

def _idx():
    idx = RefIndex()
    idx.numbers = {(SANDBOX, 6): "issue:im-Amrith/lore-sandbox#6", (SANDBOX, 11): "pr:im-Amrith/lore-sandbox#11",
                   (FALKOR, 2279): "pr:FalkorDB/FalkorDB#2279"}
    idx.add_sha("657c5288243c1680085e7a082f5a7053b4df51e5")
    idx.doc_paths = {(SANDBOX, "docs/adr/0001-link-cache.md"): "doc:im-Amrith/lore-sandbox:docs/adr/0001-link-cache.md",
                     (SANDBOX, "README.md"): "doc:im-Amrith/lore-sandbox:README.md"}
    return idx


def test_references():
    text = ("Refs #6\n\nThis reverses the decision in #11. See docs/adr/0001-link-cache.md, "
            "commit 657c528, FalkorDB/FalkorDB#2279 and https://github.com/im-Amrith/lore-sandbox/issues/6. "
            "Unknown #99, colour &#35; and hex deadbeef, README.md")
    assert find_references(text, SANDBOX, _idx()) == {
        "issue:im-Amrith/lore-sandbox#6",
        "pr:im-Amrith/lore-sandbox#11",
        "pr:FalkorDB/FalkorDB#2279",
        "commit:657c5288243c1680085e7a082f5a7053b4df51e5",
        "doc:im-Amrith/lore-sandbox:docs/adr/0001-link-cache.md",
    }


def test_references_local_number_is_repo_scoped():
    # "#11" in a FalkorDB text must not resolve to the sandbox's #11.
    assert find_references("see #11", FALKOR, _idx()) == set()
    assert find_references(None, SANDBOX, _idx()) == set()


# --- commit -> PR --------------------------------------------------------------

def _c(sha, parents, pr=None):
    return {"sha": sha, "parents": parents, "pr_number": pr}


def test_commit_pr_links_merge_commit_branch_side():
    # main: m0 -> M (merge of PR 12, branch b1 -> b2) -> s (squash "(#13)")
    commits = [
        _c("s", ["M"], 13),
        _c("M", ["m0", "b2"], 12),
        _c("b2", ["b1"]),
        _c("b1", ["m0"]),
        _c("m0", []),
    ]
    links = commit_pr_links(commits, {})
    assert links == {"s": 13, "M": 12, "b2": 12, "b1": 12}


def test_commit_pr_links_merge_commit_oid():
    assert commit_pr_links([_c("r", [])], {"r": 7}) == {"r": 7}


def test_commit_pr_links_rebase_merge_by_subject_and_date():
    # Rebase merge: main has new shas; the PR lists the original ones.
    commits = [
        {"sha": "new2", "parents": ["new1"], "pr_number": None, "subject": "analytics: add reset()", "authored_at": 200},
        {"sha": "new1", "parents": ["base"], "pr_number": None, "subject": "analytics: count clicks", "authored_at": 100},
        {"sha": "base", "parents": [], "pr_number": None, "subject": "init", "authored_at": 50},
    ]
    pr_commits = {14: [("old1", "analytics: count clicks", 100), ("old2", "analytics: add reset()", 200)]}
    assert commit_pr_links(commits, {"new2": 14}, pr_commits) == {"new1": 14, "new2": 14}


def test_commit_pr_links_number_needs_matching_base_branch():
    # main-rs came from another repo: its "Merge pull request #658" is not this repo's PR #658.
    commits = [
        {"sha": "rs1", "parents": [], "pr_number": 658, "branches": ["main-rs"], "subject": "x", "authored_at": 1},
        {"sha": "rs2", "parents": [], "pr_number": 2262, "branches": ["main-rs"], "subject": "y", "authored_at": 2},
        {"sha": "m1", "parents": [], "pr_number": 2678, "branches": ["main"], "subject": "z", "authored_at": 3},
    ]
    base = {658: "master", 2262: "main-rs", 2678: "main"}
    assert commit_pr_links(commits, {}, None, base) == {"rs2": 2262, "m1": 2678}


def test_exact_link_beats_number():
    commits = [{"sha": "a", "parents": [], "pr_number": 5, "branches": ["main"], "subject": "s", "authored_at": 1}]
    assert commit_pr_links(commits, {"a": 9}, None, {5: "main", 9: "main"}) == {"a": 9}
