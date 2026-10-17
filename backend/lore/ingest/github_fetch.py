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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

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


class ItemStream:
    """Streams a long step's items to disk as they complete, so memory holds one page at most.

    <out>.partial.jsonl gets one finished item per line (email-scrubbed);
    <out>.partial.state.json holds {key, after, listed}: the page cursor and
    whether paging finished. A rerun skips ids already in the .jsonl and resumes
    at the saved cursor. `key` is the since date: a different --since starts over.
    finish() streams the lines into <out> as a JSON array and removes the partials.
    """

    def __init__(self, out: Path, key: str):
        self.out, self.key = out, key
        self.items_path = out.with_suffix(".partial.jsonl")
        self.state_path = out.with_suffix(".partial.state.json")
        self.state: dict[str, Any] = read_json(self.state_path) if self.state_path.exists() else {}
        if self.state.get("key") != key:
            self.clear()
        self.done_ids: set[str] = set()
        if self.items_path.exists():
            self._drop_torn_line()
            with self.items_path.open(encoding="utf-8") as f:
                self.done_ids = {json.loads(line)["id"] for line in f if line.strip()}

    def _drop_torn_line(self) -> None:
        """A kill mid-write can leave a last line without its newline; cut it off."""
        data = self.items_path.read_bytes()
        if data and not data.endswith(b"\n"):
            self.items_path.write_bytes(data[: data.rfind(b"\n") + 1])

    def append(self, item: dict) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        with self.items_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(scrub(item), ensure_ascii=False) + "\n")
        self.done_ids.add(item["id"])

    def save_cursor(self, after: str | None, listed: bool = False) -> None:
        self.state = {"key": self.key, "after": after, "listed": listed}
        write_json(self.state_path, self.state)

    def finish(self) -> int:
        tmp = self.out.with_suffix(".json.tmp")
        n = 0
        with tmp.open("w", encoding="utf-8") as dst:
            dst.write("[")
            if self.items_path.exists():
                with self.items_path.open(encoding="utf-8") as src:
                    for line in src:
                        if line.strip():
                            dst.write(("," if n else "") + "\n" + line.rstrip("\n"))
                            n += 1
            dst.write("\n]\n")
        os.replace(tmp, self.out)
        self.clear()
        return n

    def clear(self) -> None:
        self.state = {}
        self.done_ids = set()
        self.items_path.unlink(missing_ok=True)
        self.state_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GraphQL client with rate-limit handling
# ---------------------------------------------------------------------------

class TransientError(Exception):
    pass


class GitHub:
    def __init__(self, token: str, log: Callable[[str], None] = lambda m: print(m, flush=True)):
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
        """Follow a connection at `path` (e.g. ["repository", "releases"]) into a list.

        For small connections; big ones go through stream(). `stop(node)` ends
        paging at the first node it returns True for (that node is excluded).
        """
        nodes: list[dict] = []
        for page in self._pages(query, variables, path, page_size, label, None):
            for node in page["nodes"]:
                if stop and stop(node):
                    return nodes
                nodes.append(node)
            if label:
                self.log(f"  {label}: {len(nodes)}")
        return nodes

    def stream(
        self,
        query: str,
        variables: dict[str, Any],
        path: list[str],
        out: ItemStream,
        complete: Callable[[dict], None],
        stop: Callable[[dict], bool] | None = None,
        page_size: int = 50,
        label: str = "",
    ) -> None:
        """Like paginate, but each node is completed (complete(node)) and written to `out`
        straight away, and the cursor is saved after every page. Resumes from `out`."""
        if out.state.get("listed"):
            return
        after = out.state.get("after")
        if out.done_ids:
            self.log(f"  {label}: resuming, {len(out.done_ids)} already saved")
        for page in self._pages(query, variables, path, page_size, label, after):
            for node in page["nodes"]:
                if stop and stop(node):
                    out.save_cursor(after, listed=True)
                    return
                if node["id"] in out.done_ids:
                    continue
                complete(node)
                out.append(node)
            self.log(f"  {label}: {len(out.done_ids)}")
            if page["pageInfo"]["hasNextPage"]:
                after = page["pageInfo"]["endCursor"]
                out.save_cursor(after)
        out.save_cursor(after, listed=True)

    def _pages(self, query: str, variables: dict[str, Any], path: list[str], page_size: int, label: str,
               after: str | None) -> Iterator[dict[str, Any]]:
        """Yield each page of the connection at `path`. Page size halves when GitHub
        keeps timing out on a heavy page."""
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
            yield conn
            if not conn["pageInfo"]["hasNextPage"]:
                return
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
    # The PR's own commits: rebase merges rewrite shas, so the loader matches
    # commits on main to these by subject + author date.
    "commits": (100, "commit { oid messageHeadline authoredDate }"),
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

PR_FIELDS = f"""
        id number title body state isDraft url createdAt updatedAt closedAt mergedAt
        author {ACTOR} mergedBy {ACTOR}
        baseRefName headRefName mergeCommit {{ oid }}
        additions deletions changedFiles
        labels(first: 20) {{ nodes {{ name }} }}
        {_nested_block(PR_NESTED)}"""

PRS_QUERY = f"""
query($owner: String!, $name: String!, $first: Int!, $after: String) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    pullRequests(first: $first, after: $after, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      {PAGE}
      nodes {{ {PR_FIELDS} }}
    }}
  }}
}}"""

# One PR by number (M15 sync: re-fetch just the PR that was merged).
PR_QUERY = f"""
query($owner: String!, $name: String!, $number: Int!) {{
  {RATE}
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{ {PR_FIELDS} }}
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


def fetch_prs(gh: GitHub, owner: str, name: str, since: datetime, out: ItemStream) -> None:
    cutoff = since.timestamp()
    gh.stream(
        PRS_QUERY, {"owner": owner, "name": name}, ["repository", "pullRequests"], out,
        complete=lambda n: _complete_nested(gh, "PullRequest", n, PR_NESTED),
        stop=lambda n: iso_to_epoch(n["updatedAt"]) < cutoff, page_size=20, label="PRs",
    )


def fetch_pr(gh: GitHub, owner: str, name: str, number: int) -> dict:
    """One PR with every nested connection complete, in the same shape as prs.json items."""
    node = gh.graphql(PR_QUERY, {"owner": owner, "name": name, "number": number})["repository"]["pullRequest"]
    if node is None:
        raise ValueError(f"no PR #{number} in {owner}/{name}")
    _complete_nested(gh, "PullRequest", node, PR_NESTED)
    return scrub(node)


def fetch_issues(gh: GitHub, owner: str, name: str, since: datetime, out: ItemStream) -> None:
    gh.stream(
        ISSUES_QUERY, {"owner": owner, "name": name, "since": since.isoformat()}, ["repository", "issues"], out,
        complete=lambda n: _complete_nested(gh, "Issue", n, ISSUE_NESTED), page_size=50, label="issues",
    )


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

def _git(git_dir: Path, *args: str, stdin: str | None = None, env: dict[str, str] | None = None,
         check: bool = True) -> str:
    cmd = ["git", "-C", str(git_dir), "-c", "core.quotepath=false", "-c", "i18n.logOutputEncoding=UTF-8", *args]
    res = subprocess.run(cmd, capture_output=True, input=stdin.encode() if stdin is not None else None,
                         env={**os.environ, **env} if env else None)
    if check and res.returncode != 0:
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


def raw_blob_ids(raw: str) -> set[str]:
    """Blob ids (old and new side) in `git log --raw --no-abbrev` output, minus submodules and the null id."""
    oids: set[str] = set()
    for line in raw.splitlines():
        if not line.startswith(":"):
            continue
        old_mode, new_mode, old_oid, new_oid = line[1:].split("\t", 1)[0].split()[:4]
        if old_mode != "160000":  # 160000 = submodule pointer, not a blob
            oids.add(old_oid)
        if new_mode != "160000":
            oids.add(new_oid)
    oids.discard("0" * 40)
    return oids


def prefetch_blobs(git_dir: Path, branches: list[str], since: datetime, log: Callable[[str], None]) -> None:
    """Download, in bulk, the blobs `git log --numstat` needs to count lines.

    A blobless clone has no file contents, and --numstat would fetch them lazily,
    one request per commit (thousands of round trips and pack files). `--raw` lists
    each change's old and new blob ids without needing the blobs, so we ask for all
    the missing ones in a few `git fetch --stdin` calls instead.
    """
    raw = _git(git_dir, "log", *[f"origin/{b}" for b in branches], f"--since={since.isoformat()}",
               "--raw", "--no-abbrev", "--no-renames", "--format=")
    oids = raw_blob_ids(raw)
    # Older git (2.39, Debian bookworm) exits non-zero when some objects are missing, which is the
    # point of the check; the "missing" lines are still printed, so the exit code is ignored here.
    check = _git(git_dir, "cat-file", "--batch-check", stdin="\n".join(sorted(oids)) + "\n",
                 env={"GIT_NO_LAZY_FETCH": "1"}, check=False)
    missing = [l.split()[0] for l in check.splitlines() if l.endswith(" missing")]
    log(f"  blobs: {len(oids)} needed, {len(missing)} to fetch")
    for start in range(0, len(missing), 2000):
        _git(git_dir, "-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags",
             "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin",
             stdin="\n".join(missing[start:start + 2000]) + "\n")
        log(f"  blobs fetched: {min(start + 2000, len(missing))}/{len(missing)}")


def read_commits(git_dir: Path, branches: Iterable[str], since: datetime) -> list[dict]:
    """Commits on each branch since `since`, deduped by sha, with a `branches` list.
    Call prefetch_blobs first in a blobless clone."""
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


def lookup_commit_logins(gh: GitHub, owner: str, name: str, shas: list[str]) -> dict[str, str | None]:
    """Ask GitHub for author.user.login of every commit (50 per query). None = no linked account."""
    out: dict[str, str | None] = {}
    for start in range(0, len(shas), 50):
        batch = shas[start:start + 50]
        decls = ", ".join(f"$c{i}: GitObjectID!" for i in range(len(batch)))
        objs = " ".join(f"c{i}: object(oid: $c{i}) {{ ... on Commit {{ author {{ user {{ login }} }} }} }}" for i in range(len(batch)))
        q = f"query($owner: String!, $name: String!, {decls}) {{ {RATE} repository(owner: $owner, name: $name) {{ {objs} }} }}"
        variables: dict[str, Any] = {"owner": owner, "name": name}
        variables.update({f"c{i}": sha for i, sha in enumerate(batch)})
        repo = gh.graphql(q, variables)["repository"]
        for i, sha in enumerate(batch):
            user = ((repo.get(f"c{i}") or {}).get("author") or {}).get("user")
            out[sha] = user["login"] if user else None
        if len(shas) > 50:
            gh.log(f"  commit logins: {len(out)}/{len(shas)}")
    return out


def assign_logins(commits: list[dict], api_login: dict[str, str | None]) -> dict[str, int]:
    """Set author_login + login_source on every commit and drop author_email. Returns counts per source.

    1. api: GitHub's author.user.login for that commit (authoritative);
    2. noreply: the login encoded in a users.noreply.github.com email (e.g. deleted
       accounts the API no longer links);
    3. name_match: the author name appears on api-resolved commits with exactly one
       login (same person, unlinked work email);
    4. name_only: no login; the loader makes person:name:<slug> from author_name.

    The PR author is deliberately not used: commit-only authors (the sandbox's
    Priya and Marta) commit inside PRs someone else opened.
    """
    for c in commits:
        email = c.pop("author_email")
        login = api_login.get(c["sha"])
        if login:
            c["author_login"], c["login_source"] = login, "api"
        elif noreply := login_from_noreply(email):
            c["author_login"], c["login_source"] = noreply, "noreply"
        else:
            c["author_login"], c["login_source"] = None, "name_only"

    name_logins: dict[str, set[str]] = {}
    for c in commits:
        if c["author_login"]:
            name_logins.setdefault(c["author_name"], set()).add(c["author_login"])
    for c in commits:
        logins = name_logins.get(c["author_name"], set())
        if not c["author_login"] and len(logins) == 1:
            c["author_login"], c["login_source"] = next(iter(logins)), "name_match"

    counts = {"api": 0, "noreply": 0, "name_match": 0, "name_only": 0}
    for c in commits:
        counts[c["login_source"]] += 1
    return counts


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def fetch_repo(gh: GitHub, owner: str, name: str, since: datetime, refresh: bool = False) -> None:
    d = repo_dir(owner, name)
    log = gh.log
    log(f"== {owner}/{name} (since {since.date()})")

    def step(filename: str, fn: Callable[[], Any]) -> None:
        """Run fn and write its result unless the file is cached (cached files aren't read back)."""
        path = d / filename
        if path.exists() and not refresh:
            log(f"  {filename}: cached")
            return
        write_json(path, fn())
        log(f"  {filename}: written")

    def stream_step(filename: str, fn: Callable[[ItemStream], None]) -> None:
        """Like step, for big lists: fn writes items to an ItemStream, which resumes a failed run."""
        path = d / filename
        if path.exists() and not refresh:
            log(f"  {filename}: cached")
            return
        out = ItemStream(path, since.isoformat())
        if refresh:
            out.clear()
        fn(out)
        log(f"  {filename}: written ({out.finish()} items)")

    step("repo.json", lambda: {**gh.graphql(REPO_QUERY, {"owner": owner, "name": name})["repository"],
                               "since": since.isoformat(), "fetched_at": int(time.time())})
    default_branch = read_json(d / "repo.json")["defaultBranchRef"]["name"]
    stream_step("prs.json", lambda out: fetch_prs(gh, owner, name, since, out))
    stream_step("issues.json", lambda out: fetch_issues(gh, owner, name, since, out))
    step("releases.json", lambda: fetch_releases(gh, owner, name))
    step("codeowners.json", lambda: fetch_codeowners(gh, owner, name))

    git_dir = ensure_clone(owner, name, refresh, log)
    step("docs.json", lambda: fetch_docs(gh, owner, name, git_dir, default_branch))

    branches = [default_branch] + EXTRA_BRANCHES.get(f"{owner}/{name}", [])

    def commits() -> dict:
        prefetch_blobs(git_dir, branches, since, log)
        cs = read_commits(git_dir, branches, since)
        counts = assign_logins(cs, lookup_commit_logins(gh, owner, name, [c["sha"] for c in cs]))
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
        "commit_login_sources": commits_doc.get("login_sources"),
        "commit_authors_top": Counter(
            c["author_login"] or f"name:{c['author_name']}" for c in commits
        ).most_common(12),
        "issue_pr_numbers": len({p["number"] for p in prs} | {i["number"] for i in issues}),
        "prs": len(prs),
        "prs_merged": sum(1 for p in prs if p["mergedAt"]),
        "prs_open": sum(1 for p in prs if p["state"] == "OPEN"),
        "prs_draft": sum(1 for p in prs if p["isDraft"]),
        "reviews": reviews,
        "issues": len(issues),
        "comments": pr_comments + review_comments + issue_comments,
        "comments_detail": {"pr": pr_comments, "review": review_comments, "issue": issue_comments},
        "docs": len(load("docs.json", [])),
        "releases": len(load("releases.json", [])),
        "codeowners": (load("codeowners.json", None) or {}).get("path"),
    }
