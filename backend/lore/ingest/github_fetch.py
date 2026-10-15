"""Fetch a repo's history from GitHub into data/raw/<owner>/<repo>/.

Sources:
- GraphQL API: repo metadata, pull requests (files, reviews, comments, closing
  issues), issues (labels, comments), CODEOWNERS, docs, releases.
- A blobless git clone (data/raw/<owner>/<repo>/git): commits with changed
  paths and line counts, from the default branch plus any extra branches in
  config.EXTRA_BRANCHES (FalkorDB/FalkorDB also needs main-rs).

Privacy: email addresses are never written. Commit author emails are used in
memory only, to map each commit to a GitHub login, and every string written to
disk goes through scrub() which redacts anything that looks like an email.

Each output file is cached; a repo step is skipped when its file exists, unless
refresh=True.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from lore.config import EXTRA_BRANCHES, RAW_DIR

GRAPHQL_URL = "https://api.github.com/graphql"

# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# 12345+login@users.noreply.github.com or login@users.noreply.github.com
NOREPLY_RE = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+(?:\[bot\])?)@users\.noreply\.github\.com$", re.I)
# "Fix thing (#1234)" (squash merge) or "Merge pull request #1234 from ..."
PR_IN_SUBJECT_RE = re.compile(r"\(#(\d+)\)\s*$")
MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)\b")

DOC_DIRS = {"docs", "doc", "design", "rfcs", "rfc", "adr", "adrs", "decisions"}
DOC_EXTS = (".md", ".mdx", ".markdown")
MAX_DOCS = 400
MAX_DOC_BYTES = 300_000


def scrub(value: Any) -> Any:
    """Recursively redact email addresses from every string in a JSON-like value."""
    if isinstance(value, str):
        return EMAIL_RE.sub("[email]", value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def login_from_noreply(email: str) -> str | None:
    m = NOREPLY_RE.match(email.strip())
    return m.group(1) if m else None


def pr_number_from_subject(subject: str) -> int | None:
    m = PR_IN_SUBJECT_RE.search(subject) or MERGE_PR_RE.match(subject)
    return int(m.group(1)) if m else None


def is_doc_path(path: str) -> bool:
    lower = path.lower()
    if not lower.endswith(DOC_EXTS):
        return False
    parts = lower.split("/")
    if parts[-1].startswith("readme"):
        return True
    return any(p in DOC_DIRS for p in parts[:-1])


def iso_to_epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# git log record separators: \x1e starts a commit, \x1f splits header fields,
# \x1d ends the message; the --numstat lines follow.
GIT_LOG_FORMAT = "%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%ct%x1f%B%x1d"


def parse_git_log(output: str) -> list[dict[str, Any]]:
    """Parse `git log --numstat --format=GIT_LOG_FORMAT`. Keeps author_email (in memory only)."""
    commits = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        header, _, stats = record.partition("\x1d")
        sha, parents, name, email, at, ct, message = header.split("\x1f", 6)
        files = []
        for line in stats.strip().splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            add, dele, path = parts
            files.append({
                "path": path,
                # "-" means binary file: no line counts
                "additions": int(add) if add.isdigit() else 0,
                "deletions": int(dele) if dele.isdigit() else 0,
            })
        message = message.strip()
        subject = message.split("\n", 1)[0]
        commits.append({
            "sha": sha,
            "parents": parents.split(),
            "author_name": name,
            "author_email": email,  # dropped before writing
            "authored_at": int(at),
            "committed_at": int(ct),
            "subject": subject,
            "message": message,
            "pr_number": pr_number_from_subject(subject),
            "files": files,
        })
    return commits


# ---------------------------------------------------------------------------
# Disk
# ---------------------------------------------------------------------------

def repo_dir(owner: str, name: str) -> Path:
    return RAW_DIR / owner / name


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(scrub(obj), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# GraphQL client with rate-limit handling
# ---------------------------------------------------------------------------

class TransientError(Exception):
    pass


class GitHub:
    def __init__(self, token: str, log: Callable[[str], None] = print):
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set (see .env.example)")
        self.http = httpx.Client(
            timeout=90,
            headers={"Authorization": f"bearer {token}", "User-Agent": "lore-fetch"},
        )
        self.log = log
        self.calls = 0

    def _sleep_until(self, reset_epoch: float, why: str) -> None:
        wait = max(0.0, reset_epoch - time.time()) + 5
        self.log(f"  rate limit ({why}): sleeping {wait:.0f}s")
        time.sleep(wait)

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a query. Retries 5xx (raising TransientError after 3 tries) and waits out rate limits.

        Network errors (DNS, dropped connections) get a longer backoff, ~5 min in
        total, so a brief outage doesn't throw away a long PR fetch.
        """
        transient = 0
        network = 0
        while True:
            try:
                r = self.http.post(GRAPHQL_URL, json={"query": query, "variables": variables or {}})
            except httpx.TransportError as e:
                network += 1
                if network >= 8:
                    raise TransientError(str(e)) from e
                wait = min(60, 5 * 2 ** (network - 1))
                self.log(f"  network error ({e}); retry {network}/7 in {wait}s")
                time.sleep(wait)
                continue
            self.calls += 1

            if r.status_code in (403, 429):
                # Secondary limits send retry-after; primary limits send x-ratelimit-reset.
                if "retry-after" in r.headers:
                    self._sleep_until(time.time() + int(r.headers["retry-after"]), "retry-after")
                elif r.headers.get("x-ratelimit-remaining") == "0":
                    self._sleep_until(int(r.headers["x-ratelimit-reset"]), "primary")
                else:
                    self._sleep_until(time.time() + 60, f"HTTP {r.status_code}")
                continue
            if r.status_code >= 500:
                transient += 1
                if transient >= 3:
                    raise TransientError(f"HTTP {r.status_code}")
                time.sleep(5 * transient)
                continue
            r.raise_for_status()

            body = r.json()
            errors = body.get("errors") or []
            if any(e.get("type") == "RATE_LIMITED" for e in errors):
                self._sleep_until(int(r.headers.get("x-ratelimit-reset", time.time() + 60)), "graphql")
                continue
            if errors and not body.get("data"):
                raise RuntimeError(f"GraphQL errors: {errors}")
            data = body["data"]

            rl = data.get("rateLimit")
            if rl and rl["remaining"] < 100:
                self._sleep_until(iso_to_epoch(rl["resetAt"]), f"{rl['remaining']} points left")
            return data

    def paginate(
        self,
        query: str,
        variables: dict[str, Any],
        path: list[str],
        stop: Callable[[dict], bool] | None = None,
        page_size: int = 50,
        label: str = "",
    ) -> list[dict[str, Any]]:
        """Follow a connection at `path` (e.g. ["repository", "pullRequests"]).

        `stop(node)` ends paging at the first node it returns True for (that node is
        excluded). Page size halves when GitHub keeps timing out on a heavy page.
        """
        nodes: list[dict] = []
        after = None
        while True:
            try:
                data = self.graphql(query, {**variables, "first": page_size, "after": after})
            except TransientError:
                if page_size <= 5:
                    raise
                page_size //= 2
                self.log(f"  {label}: server errors, page size -> {page_size}")
                continue
            conn = data
            for key in path:
                conn = conn[key]
            for node in conn["nodes"]:
                if stop and stop(node):
                    return nodes
                nodes.append(node)
            if label:
                self.log(f"  {label}: {len(nodes)}")
            if not conn["pageInfo"]["hasNextPage"]:
                return nodes
            after = conn["pageInfo"]["endCursor"]


# ---------------------------------------------------------------------------
# GraphQL documents
# ---------------------------------------------------------------------------

RATE = "rateLimit { remaining resetAt cost }"
ACTOR = "{ login __typename }"
PAGE = "pageInfo { hasNextPage endCursor }"

COMMENT_FIELDS = f"id author {ACTOR} body createdAt url"
REVIEW_FIELDS = (
    f"id author {ACTOR} state submittedAt body url "
    f"comments(first: 30) {{ totalCount nodes {{ {COMMENT_FIELDS} path }} }}"
)
FILE_FIELDS = "path additions deletions changeType"
CLOSING_FIELDS = "number repository { nameWithOwner }"

# Nested connections on a PR/issue and their node fields. Pages beyond the first
# are fetched with a follow-up node(id) query (see _complete_nested).
PR_NESTED = {
    "files": (100, FILE_FIELDS),
    "reviews": (50, REVIEW_FIELDS),
    "comments": (50, COMMENT_FIELDS),
    "closingIssuesReferences": (20, CLOSING_FIELDS),
}
ISSUE_NESTED = {"comments": (100, COMMENT_FIELDS)}


def _nested_block(nested: dict[str, tuple[int, str]]) -> str:
    return " ".join(f"{f}(first: {n}) {{ {PAGE} nodes {{ {fields} }} }}" for f, (n, fields) in nested.items())


REPO_QUERY = f"""
query($owner: String!, $name: String!) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    name nameWithOwner description url isFork isArchived createdAt pushedAt
    primaryLanguage {{ name }}
    defaultBranchRef {{ name }}
  }}
}}"""

ORG_REPOS_QUERY = f"""
query($org: String!, $first: Int!, $after: String) {{
  {RATE}
  organization(login: $org) {{
    repositories(first: $first, after: $after, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
      {PAGE}
      nodes {{ name isFork isArchived pushedAt }}
    }}
  }}
}}"""

PRS_QUERY = f"""
query($owner: String!, $name: String!, $first: Int!, $after: String) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    pullRequests(first: $first, after: $after, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      {PAGE}
      nodes {{
        id number title body state isDraft url createdAt updatedAt closedAt mergedAt
        author {ACTOR} mergedBy {ACTOR}
        baseRefName headRefName mergeCommit {{ oid }}
        additions deletions changedFiles
        labels(first: 20) {{ nodes {{ name }} }}
        {_nested_block(PR_NESTED)}
      }}
    }}
  }}
}}"""

ISSUES_QUERY = f"""
query($owner: String!, $name: String!, $since: DateTime!, $first: Int!, $after: String) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    issues(first: $first, after: $after, filterBy: {{since: $since}},
           orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      {PAGE}
      nodes {{
        id number title body state stateReason url createdAt updatedAt closedAt
        author {ACTOR}
        labels(first: 30) {{ nodes {{ name }} }}
        {_nested_block(ISSUE_NESTED)}
      }}
    }}
  }}
}}"""

RELEASES_QUERY = f"""
query($owner: String!, $name: String!, $first: Int!, $after: String) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    releases(first: $first, after: $after, orderBy: {{field: CREATED_AT, direction: DESC}}) {{
      {PAGE}
      nodes {{ tagName name description url createdAt publishedAt isPrerelease isDraft
               author {ACTOR} tagCommit {{ oid }} }}
    }}
  }}
}}"""

CODEOWNERS_PATHS = ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]
CODEOWNERS_QUERY = f"""
query($owner: String!, $name: String!) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    {" ".join(f'f{i}: object(expression: "HEAD:{p}") {{ ... on Blob {{ text }} }}' for i, p in enumerate(CODEOWNERS_PATHS))}
  }}
}}"""


def _followup_query(typename: str, field: str, n: int, fields: str) -> str:
    return f"""
query($id: ID!, $after: String) {{
  {RATE}
  node(id: $id) {{ ... on {typename} {{ {field}(first: {n}, after: $after) {{ {PAGE} nodes {{ {fields} }} }} }} }}
}}"""


# ---------------------------------------------------------------------------
# Fetch steps
# ---------------------------------------------------------------------------

def _complete_nested(gh: GitHub, typename: str, node: dict, nested: dict[str, tuple[int, str]]) -> None:
    """Fetch remaining pages of nested connections; flatten each to a plain list."""
    for field, (n, fields) in nested.items():
        conn = node[field]
        items = list(conn["nodes"])
        after = conn["pageInfo"]["endCursor"] if conn["pageInfo"]["hasNextPage"] else None
        while after:
            data = gh.graphql(_followup_query(typename, field, n, fields), {"id": node["id"], "after": after})
            c = data["node"][field]
            items.extend(c["nodes"])
            after = c["pageInfo"]["endCursor"] if c["pageInfo"]["hasNextPage"] else None
        node[field] = items
    if "labels" in node:
        node["labels"] = [l["name"] for l in node["labels"]["nodes"]]


def list_org_repos(gh: GitHub, org: str, since: datetime) -> list[str]:
    nodes = gh.paginate(ORG_REPOS_QUERY, {"org": org}, ["organization", "repositories"], page_size=100)
    return [
        n["name"] for n in nodes
        if not n["isFork"] and not n["isArchived"] and n["pushedAt"] and iso_to_epoch(n["pushedAt"]) >= since.timestamp()
    ]


def fetch_prs(gh: GitHub, owner: str, name: str, since: datetime) -> list[dict]:
    cutoff = since.timestamp()
    prs = gh.paginate(
        PRS_QUERY, {"owner": owner, "name": name}, ["repository", "pullRequests"],
        stop=lambda n: iso_to_epoch(n["updatedAt"]) < cutoff, page_size=20, label="PRs",
    )
    for pr in prs:
        _complete_nested(gh, "PullRequest", pr, PR_NESTED)
    return prs


def fetch_issues(gh: GitHub, owner: str, name: str, since: datetime) -> list[dict]:
    issues = gh.paginate(
        ISSUES_QUERY, {"owner": owner, "name": name, "since": since.isoformat()},
        ["repository", "issues"], page_size=50, label="issues",
    )
    for issue in issues:
        _complete_nested(gh, "Issue", issue, ISSUE_NESTED)
    return issues


def fetch_releases(gh: GitHub, owner: str, name: str) -> list[dict]:
    return gh.paginate(RELEASES_QUERY, {"owner": owner, "name": name}, ["repository", "releases"], page_size=100)


def fetch_codeowners(gh: GitHub, owner: str, name: str) -> dict | None:
    repo = gh.graphql(CODEOWNERS_QUERY, {"owner": owner, "name": name})["repository"]
    for i, path in enumerate(CODEOWNERS_PATHS):
        blob = repo.get(f"f{i}")
        if blob and blob.get("text") is not None:
            return {"path": path, "text": blob["text"]}
    return None


def fetch_docs(gh: GitHub, owner: str, name: str, git_dir: Path, branch: str) -> list[dict]:
    """List markdown docs from the clone's tree, then pull text + last change via GraphQL."""
    out = _git(git_dir, "ls-tree", "-r", "--name-only", f"origin/{branch}")
    paths = [p for p in out.splitlines() if is_doc_path(p)][:MAX_DOCS]
    docs = []
    for start in range(0, len(paths), 20):
        batch = paths[start:start + 20]
        var_decls = ", ".join(f"$e{i}: String!, $p{i}: String!" for i in range(len(batch)))
        objs = " ".join(f"o{i}: object(expression: $e{i}) {{ ... on Blob {{ text byteSize isBinary }} }}" for i in range(len(batch)))
        hist = " ".join(
            f"h{i}: history(first: 1, path: $p{i}) {{ nodes {{ oid committedDate author {{ name user {{ login }} }} }} }}"
            for i in range(len(batch))
        )
        q = f"""
query($owner: String!, $name: String!, $ref: String!, {var_decls}) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    {objs}
    ref(qualifiedName: $ref) {{ target {{ ... on Commit {{ {hist} }} }} }}
  }}
}}"""
        variables: dict[str, Any] = {"owner": owner, "name": name, "ref": f"refs/heads/{branch}"}
        for i, p in enumerate(batch):
            variables[f"e{i}"] = f"{branch}:{p}"
            variables[f"p{i}"] = p
        repo = gh.graphql(q, variables)["repository"]
        target = repo["ref"]["target"]
        for i, p in enumerate(batch):
            blob = repo.get(f"o{i}")
            if not blob or blob["isBinary"] or blob["byteSize"] > MAX_DOC_BYTES:
                continue
            last = (target[f"h{i}"]["nodes"] or [None])[0]
            docs.append({
                "path": p,
                "branch": branch,
                "text": blob["text"],
                "byte_size": blob["byteSize"],
                "last_commit": last["oid"] if last else None,
                "updated_at": last["committedDate"] if last else None,
                "last_author_login": ((last or {}).get("author") or {}).get("user") and last["author"]["user"]["login"],
                "url": f"https://github.com/{owner}/{name}/blob/{branch}/{p}",
            })
        gh.log(f"  docs: {len(docs)}/{len(paths)}")
    return docs


# ---------------------------------------------------------------------------
# Git (commits)
# ---------------------------------------------------------------------------

def _git(git_dir: Path, *args: str) -> str:
    cmd = ["git", "-C", str(git_dir), "-c", "core.quotepath=false", "-c", "i18n.logOutputEncoding=UTF-8", *args]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {res.stderr.decode('utf-8', 'replace')[:500]}")
    return res.stdout.decode("utf-8", "replace")


def ensure_clone(owner: str, name: str, refresh: bool, log: Callable[[str], None]) -> Path:
    git_dir = repo_dir(owner, name) / "git"
    if (git_dir / ".git").exists():
        if refresh:
            log("  git fetch")
            _git(git_dir, "fetch", "--prune", "origin")
    else:
        log("  git clone (blobless)")
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", "-q",
             f"https://github.com/{owner}/{name}.git", str(git_dir)],
            capture_output=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git clone failed: {res.stderr.decode('utf-8', 'replace')[:500]}")
    return git_dir


def read_commits(git_dir: Path, branches: Iterable[str], since: datetime) -> list[dict]:
    """Commits on each branch since `since`, deduped by sha, with a `branches` list."""
    by_sha: dict[str, dict] = {}
    for branch in branches:
        out = _git(
            git_dir, "log", f"origin/{branch}", f"--since={since.isoformat()}",
            "--no-renames", "--numstat", f"--format={GIT_LOG_FORMAT}",
        )
        for c in parse_git_log(out):
            if c["sha"] in by_sha:
                by_sha[c["sha"]]["branches"].append(branch)
            else:
                c["branches"] = [branch]
                by_sha[c["sha"]] = c
    return sorted(by_sha.values(), key=lambda c: c["committed_at"], reverse=True)


def map_logins(gh: GitHub, owner: str, name: str, commits: list[dict], prs: list[dict]) -> dict[str, int]:
    """Set author_login on every commit and drop author_email. Returns counts by mapping source.

    1. noreply emails encode the login directly;
    2. otherwise ask GitHub which user one commit per distinct email belongs to
       (the same email always maps to the same account);
    3. if GitHub has no linked account, fall back to the author of the PR the
       commit names in its subject ("(#1234)"); squash merges carry the PR author.
    """
    sample: dict[str, str] = {}
    for c in commits:
        sample.setdefault(c["author_email"].lower(), c["sha"])

    email_login: dict[str, str | None] = {}
    to_ask = []
    for email, sha in sample.items():
        login = login_from_noreply(email)
        if login:
            email_login[email] = login
        else:
            to_ask.append((email, sha))

    for start in range(0, len(to_ask), 50):
        batch = to_ask[start:start + 50]
        decls = ", ".join(f"$c{i}: GitObjectID!" for i in range(len(batch)))
        objs = " ".join(f"c{i}: object(oid: $c{i}) {{ ... on Commit {{ author {{ user {{ login }} }} }} }}" for i in range(len(batch)))
        q = f"query($owner: String!, $name: String!, {decls}) {{ {RATE} repository(owner: $owner, name: $name) {{ {objs} }} }}"
        variables: dict[str, Any] = {"owner": owner, "name": name}
        variables.update({f"c{i}": sha for i, (_, sha) in enumerate(batch)})
        repo = gh.graphql(q, variables)["repository"]
        for i, (email, _) in enumerate(batch):
            obj = repo.get(f"c{i}") or {}
            user = (obj.get("author") or {}).get("user")
            email_login[email] = user["login"] if user else None

    pr_author = {pr["number"]: (pr.get("author") or {}).get("login") for pr in prs}
    pr_merger = {pr["number"]: (pr.get("mergedBy") or {}).get("login") for pr in prs}
    counts = {"noreply": 0, "api": 0, "pr_author": 0, "pr_merger": 0, "name_only": 0}
    for c in commits:
        email = c.pop("author_email").lower()
        login = email_login.get(email)
        # A "Merge pull request #N" commit is authored by whoever clicked merge.
        by_merger = bool(MERGE_PR_RE.match(c["subject"]))
        pr_login = (pr_merger if by_merger else pr_author).get(c["pr_number"])
        if login:
            c["author_login"] = login
            c["login_source"] = "noreply" if login_from_noreply(email) else "api"
        elif pr_login:
            c["author_login"] = pr_login
            c["login_source"] = "pr_merger" if by_merger else "pr_author"
        else:
            c["author_login"] = None  # commit-only author: keep author_name
            c["login_source"] = "name_only"
        counts[c["login_source"]] += 1
    return counts


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def fetch_repo(gh: GitHub, owner: str, name: str, since: datetime, refresh: bool = False) -> None:
    d = repo_dir(owner, name)
    log = gh.log
    log(f"== {owner}/{name} (since {since.date()})")

    def step(filename: str, fn: Callable[[], Any]) -> Any:
        path = d / filename
        if path.exists() and not refresh:
            log(f"  {filename}: cached")
            return read_json(path)
        result = fn()
        write_json(path, result)
        log(f"  {filename}: written")
        return result

    meta = step("repo.json", lambda: {**gh.graphql(REPO_QUERY, {"owner": owner, "name": name})["repository"],
                                      "since": since.isoformat(), "fetched_at": int(time.time())})
    default_branch = meta["defaultBranchRef"]["name"]
    prs = step("prs.json", lambda: fetch_prs(gh, owner, name, since))
    step("issues.json", lambda: fetch_issues(gh, owner, name, since))
    step("releases.json", lambda: fetch_releases(gh, owner, name))
    step("codeowners.json", lambda: fetch_codeowners(gh, owner, name))

    git_dir = ensure_clone(owner, name, refresh, log)
    step("docs.json", lambda: fetch_docs(gh, owner, name, git_dir, default_branch))

    branches = [default_branch] + EXTRA_BRANCHES.get(f"{owner}/{name}", [])

    def commits() -> dict:
        cs = read_commits(git_dir, branches, since)
        counts = map_logins(gh, owner, name, cs, prs)
        log(f"  commit logins: {counts}")
        return {"branches": branches, "since": since.isoformat(), "login_sources": counts, "commits": cs}

    step("commits.json", commits)


def summarize(owner: str, name: str) -> dict[str, Any]:
    d = repo_dir(owner, name)

    def load(f: str, default: Any) -> Any:
        return read_json(d / f) if (d / f).exists() else default

    prs = load("prs.json", [])
    issues = load("issues.json", [])
    commits_doc = load("commits.json", {"commits": [], "branches": []})
    commits = commits_doc["commits"]

    pr_comments = sum(len(p["comments"]) for p in prs)
    reviews = sum(len(p["reviews"]) for p in prs)
    review_comments = sum(len(r["comments"]["nodes"]) for p in prs for r in p["reviews"])
    issue_comments = sum(len(i["comments"]) for i in issues)
    dates = [c["committed_at"] for c in commits]
    humans = {c["author_login"] or c["author_name"] for c in commits
              if not (c["author_login"] or "").endswith("[bot]") and "bot" not in (c["author_name"] or "").lower()}
    return {
        "repo": f"{owner}/{name}",
        "commits": len(commits),
        "commits_by_branch": {b: sum(b in c["branches"] for c in commits) for b in commits_doc["branches"]},
        "commits_with_login": sum(1 for c in commits if c["author_login"]),
        "commits_linked_to_pr": sum(1 for c in commits if c["pr_number"]),
        "commit_authors_non_bot": len(humans),
        "commit_range": (
            f"{datetime.fromtimestamp(min(dates), timezone.utc).date()} .. {datetime.fromtimestamp(max(dates), timezone.utc).date()}"
            if dates else "-"
        ),
        "prs": len(prs),
        "prs_merged": sum(1 for p in prs if p["mergedAt"]),
        "reviews": reviews,
        "issues": len(issues),
        "comments": pr_comments + review_comments + issue_comments,
        "comments_detail": {"pr": pr_comments, "review": review_comments, "issue": issue_comments},
        "docs": len(load("docs.json", [])),
        "releases": len(load("releases.json", [])),
        "codeowners": (load("codeowners.json", None) or {}).get("path"),
    }
