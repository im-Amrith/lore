"""Turn cached raw GitHub JSON (data/raw/<owner>/<repo>/) into rows for the loaders.

Each row is a plain dict ready for `UNWIND $rows AS row`. Ids follow CLAUDE.md:
pr:<owner>/<repo>#<n>, issue:<owner>/<repo>#<n>, commit:<sha>, person:<login>,
person:name:<slug> (commit authors with no GitHub login), module:<repo>:<path>.
Timestamps are epoch seconds (UTC).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from lore.config import BULK_COMMIT_FILES, RAW_DIR
from lore.ingest.github_fetch import read_json
from lore.ingest.modules import module_path, parse_codeowners, rule_module

# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------

BOT_LOGINS = {"dependabot", "copilot", "copilot-swe-agent", "github-actions", "renovate", "codecov"}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unknown"


def canonical_login(login: str) -> str:
    """'dependabot[bot]' (commits) and 'dependabot' (GraphQL Bot actor) are one account."""
    return login[:-5] if login.lower().endswith("[bot]") else login


def is_bot_name(name: str) -> bool:
    n = name.lower()
    return n.endswith("[bot]") or canonical_login(n) in BOT_LOGINS


def person_id(login: str) -> str:
    return f"person:{canonical_login(login)}"


def person_name_id(name: str) -> str:
    return f"person:name:{slug(name)}"


def pr_id(repo: str, n: int) -> str:
    return f"pr:{repo}#{n}"


def issue_id(repo: str, n: int) -> str:
    return f"issue:{repo}#{n}"


def commit_id(sha: str) -> str:
    return f"commit:{sha}"


def module_id(repo_name: str, path: str) -> str:
    return f"module:{repo_name}:{path}"


def doc_id(repo: str, path: str) -> str:
    return f"doc:{repo}:{path}"


def epoch(iso: str | None) -> int | None:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) if iso else None


# ---------------------------------------------------------------------------
# Commit -> PR links
# ---------------------------------------------------------------------------

def commit_pr_links(
    commits: list[dict],
    merge_commit_pr: dict[str, int],
    pr_commits: dict[int, list[tuple[str, str, int]]] | None = None,
) -> dict[str, int]:
    """sha -> PR number for every commit we can tie to a PR.

    1. the subject names the PR: squash merges "Title (#12)", merge commits
       "Merge pull request #12 from ...";
    2. the PR's mergeCommit oid;
    3. the PR's own commits (pr_commits: number -> [(oid, subject, authored_at)]):
       by sha, or for rebase merges (new shas) by subject + author date, which a
       rebase keeps;
    4. for a merge commit, every commit on its branch side: ancestors of the second
       parent, stopping at the first-parent mainline (what `git log M^1..M^2` shows).
    """
    by_sha = {c["sha"]: c for c in commits}
    links: dict[str, int] = {}
    for c in commits:
        if c["pr_number"]:
            links[c["sha"]] = c["pr_number"]
    for sha, n in merge_commit_pr.items():
        if sha in by_sha:
            links.setdefault(sha, n)
    if pr_commits:
        by_subject = {(c["subject"], c["authored_at"]): c["sha"] for c in commits}
        for n, pcs in pr_commits.items():
            for oid, subject, authored_at in pcs:
                sha = oid if oid in by_sha else by_subject.get((subject, authored_at))
                if sha:
                    links.setdefault(sha, n)

    # First-parent chains from every head (a commit nobody in the set lists as a parent).
    parents_seen = {p for c in commits for p in c["parents"]}
    mainline: set[str] = set()
    for head in (s for s in by_sha if s not in parents_seen):
        s = head
        while s in by_sha and s not in mainline:
            mainline.add(s)
            s = by_sha[s]["parents"][0] if by_sha[s]["parents"] else None

    for c in commits:
        n = links.get(c["sha"])
        if not n or len(c["parents"]) < 2:
            continue
        stack = list(c["parents"][1:])
        while stack:
            s = stack.pop()
            if s not in by_sha or s in mainline or s in links:
                continue
            links[s] = n
            stack.extend(by_sha[s]["parents"])
    return links


# ---------------------------------------------------------------------------
# References in text
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/(issues|pull|commit)/([0-9a-f]{7,40}|\d+)")
CROSS_RE = re.compile(r"(?<![\w/])([\w.-]+/[\w.-]+)#(\d+)\b")
LOCAL_RE = re.compile(r"(?<![\w/&#])#(\d+)\b")
SHA_RE = re.compile(r"(?<![\w/])([0-9a-f]{7,40})\b")


@dataclass
class RefIndex:
    """Everything a reference can resolve to inside the graph."""
    numbers: dict[tuple[str, int], str] = field(default_factory=dict)  # (repo, n) -> pr/issue id
    shas: dict[str, str] = field(default_factory=dict)                 # 7-char prefix -> full sha (ambiguous -> "")
    doc_paths: dict[tuple[str, str], str] = field(default_factory=dict)  # (repo, path) -> doc id

    def add_sha(self, sha: str) -> None:
        p = sha[:7]
        self.shas[p] = "" if p in self.shas and self.shas[p] != sha else sha

    def sha(self, token: str) -> str | None:
        full = self.shas.get(token[:7])
        return full if full and full.startswith(token) else None


def find_references(text: str | None, repo: str, idx: RefIndex) -> set[str]:
    """Node ids referenced by a text written in repo ('owner/name')."""
    if not text:
        return set()
    out: set[str] = set()
    for r, kind, ref in URL_RE.findall(text):
        if kind == "commit":
            if sha := idx.sha(ref):
                out.add(commit_id(sha))
        elif (r, int(ref)) in idx.numbers:
            out.add(idx.numbers[(r, int(ref))])
    stripped = URL_RE.sub(" ", text)
    for r, n in CROSS_RE.findall(stripped):
        if (r, int(n)) in idx.numbers:
            out.add(idx.numbers[(r, int(n))])
    for n in LOCAL_RE.findall(CROSS_RE.sub(" ", stripped)):
        if (repo, int(n)) in idx.numbers:
            out.add(idx.numbers[(repo, int(n))])
    for token in SHA_RE.findall(stripped):
        if not token.isdigit() and (sha := idx.sha(token)):
            out.add(commit_id(sha))
    for (r, path), did in idx.doc_paths.items():
        # Only paths with a directory; a bare "README.md" is too ambiguous.
        if r == repo and "/" in path and path in text:
            out.add(did)
    return out


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

@dataclass
class Rows:
    repos: list[dict] = field(default_factory=list)
    persons: list[dict] = field(default_factory=list)
    teams: list[dict] = field(default_factory=list)
    modules: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    touches: list[dict] = field(default_factory=list)
    part_of: list[dict] = field(default_factory=list)
    prs: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    closes: list[dict] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    docs: list[dict] = field(default_factory=list)
    releases: list[dict] = field(default_factory=list)
    owns: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)


class _People:
    """Collects every person seen, with activity range and display name."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.names: dict[str, Counter] = defaultdict(Counter)
        self.case: dict[str, str] = {}  # lower login -> canonical spelling

    def actor(self, actor: dict | None, at: int | None) -> str | None:
        """Person id for a GraphQL actor ({login, __typename}); None for deleted users."""
        if not actor or not actor.get("login"):
            return None
        return self.login(actor["login"], at, bot=actor.get("__typename") == "Bot")

    def login(self, login: str, at: int | None, bot: bool = False, name: str | None = None) -> str:
        login = self.case.setdefault(canonical_login(login).lower(), canonical_login(login))
        pid = person_id(login)
        row = self.rows.setdefault(pid, {"id": pid, "login": login, "name": login,
                                         "is_bot": False, "first_seen": None, "last_active": None})
        row["is_bot"] = row["is_bot"] or bot or is_bot_name(login)
        if name:
            self.names[pid][name] += 1
        self._seen(row, at)
        return pid

    def named(self, name: str, at: int | None) -> str:
        pid = person_name_id(name)
        row = self.rows.setdefault(pid, {"id": pid, "login": None, "name": name,
                                         "is_bot": is_bot_name(name), "first_seen": None, "last_active": None})
        self._seen(row, at)
        return pid

    @staticmethod
    def _seen(row: dict, at: int | None) -> None:
        if at is None:
            return
        row["first_seen"] = at if row["first_seen"] is None else min(row["first_seen"], at)
        row["last_active"] = at if row["last_active"] is None else max(row["last_active"], at)

    def finish(self) -> list[dict]:
        for pid, names in self.names.items():
            # Prefer a real name ("Avi Avni") over the login echoed back as a name.
            real = [n for n, _ in names.most_common() if n.lower() != self.rows[pid]["login"].lower()]
            if real:
                self.rows[pid]["name"] = real[0]
        return list(self.rows.values())


def _doc_title(text: str, path: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.rsplit("/", 1)[-1]


def normalize_repos(repos: list[tuple[str, str]], raw_dir: Path = RAW_DIR) -> Rows:
    """Normalise one or more cached repos (owner, name) into one set of rows."""
    rows = Rows()
    people = _People()
    idx = RefIndex()
    modules: dict[str, dict] = {}
    texts: list[tuple[str, str, str | None, int | None]] = []  # (src id, repo, text, at)

    def module(repo_full: str, repo_name: str, path: str) -> str:
        mid = module_id(repo_name, path)
        modules.setdefault(mid, {"id": mid, "path": path, "repo": repo_name, "repo_id": f"repo:{repo_full}"})
        return mid

    loaded = []
    for owner, name in repos:
        d = raw_dir / owner / name
        repo = f"{owner}/{name}"
        data = {f: read_json(d / f"{f}.json") if (d / f"{f}.json").exists() else None
                for f in ("repo", "prs", "issues", "commits", "docs", "releases", "codeowners")}
        loaded.append((owner, name, repo, data))
        for pr in data["prs"] or []:
            idx.numbers[(repo, pr["number"])] = pr_id(repo, pr["number"])
        for issue in data["issues"] or []:
            idx.numbers[(repo, issue["number"])] = issue_id(repo, issue["number"])
        for c in (data["commits"] or {}).get("commits", []):
            idx.add_sha(c["sha"])
        for doc in data["docs"] or []:
            idx.doc_paths[(repo, doc["path"])] = doc_id(repo, doc["path"])

    for owner, name, repo, data in loaded:
        meta = data["repo"] or {}
        fetched_at = meta.get("fetched_at")
        rows.repos.append({"id": f"repo:{repo}", "name": name, "full_name": repo,
                           "description": meta.get("description"), "url": meta.get("url")})

        # CODEOWNERS: directory patterns override the default module mapping.
        commits = (data["commits"] or {}).get("commits", [])
        all_paths = {f["path"] for c in commits for f in c["files"]}
        all_paths |= {f["path"] for pr in data["prs"] or [] for f in pr["files"]}
        rules = parse_codeowners((data["codeowners"] or {}).get("text", ""))
        owner_dirs = [r.directory for r in rules if r.directory]
        # "/docs" without a trailing slash is still a directory if files live under it.
        owner_dirs += [r.pattern.strip("/") for r in rules if not r.directory and "*" not in r.pattern
                       and any(p.startswith(r.pattern.strip("/") + "/") for p in all_paths)]

        def mod(path: str) -> str:
            return module(repo, name, module_path(path, repo, owner_dirs))

        for rule in rules:
            p = rule.pattern.strip("/")
            target = p if p in owner_dirs else rule_module(rule, repo, owner_dirs)
            if target is None:
                continue
            mid = module(repo, name, target)
            for o in rule.owners:
                handle = o[1:]
                if "/" in handle:
                    tid = f"team:{handle}"
                    if not any(t["id"] == tid for t in rows.teams):
                        rows.teams.append({"id": tid, "name": handle})
                    owner_ref = tid
                else:
                    owner_ref = people.login(handle, None)
                rows.owns.append({"owner_id": owner_ref, "module_id": mid, "pattern": rule.pattern, "at": fetched_at})

        # Commits
        merge_commit_pr = {pr["mergeCommit"]["oid"]: pr["number"]
                           for pr in data["prs"] or [] if pr.get("mergeCommit")}
        pr_commits = {pr["number"]: [(pc["commit"]["oid"], pc["commit"]["messageHeadline"],
                                      epoch(pc["commit"]["authoredDate"])) for pc in pr.get("commits", [])]
                      for pr in data["prs"] or []}
        links = commit_pr_links(commits, merge_commit_pr, pr_commits)
        for c in commits:
            at = c["committed_at"]
            author = (people.login(c["author_login"], at, name=c["author_name"]) if c["author_login"]
                      else people.named(c["author_name"], at))
            files = c["files"]
            rows.commits.append({
                "id": commit_id(c["sha"]), "sha": c["sha"], "repo": repo, "message": c["message"],
                "at": at, "authored_at": c["authored_at"], "author_id": author,
                "branches": c["branches"], "files_changed": len(files),
                "additions": sum(f["additions"] for f in files), "deletions": sum(f["deletions"] for f in files),
                "bulk": len(files) > BULK_COMMIT_FILES, "is_merge": len(c["parents"]) > 1,
            })
            per_module: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
            for f in files:
                agg = per_module[mod(f["path"])]
                agg[0] += f["additions"]
                agg[1] += f["deletions"]
                agg[2] += 1
            for mid, (add, dele, n) in per_module.items():
                rows.touches.append({"commit_id": commit_id(c["sha"]), "module_id": mid,
                                     "additions": add, "deletions": dele, "files": n, "at": at})
            if c["sha"] in links and (repo, links[c["sha"]]) in idx.numbers:
                rows.part_of.append({"commit_id": commit_id(c["sha"]), "pr_id": pr_id(repo, links[c["sha"]]), "at": at})

        # Pull requests, reviews, comments
        for pr in data["prs"] or []:
            pid = pr_id(repo, pr["number"])
            created = epoch(pr["createdAt"])
            paths = [f["path"] for f in pr["files"]]
            rows.prs.append({
                "id": pid, "number": pr["number"], "repo": repo, "title": pr["title"], "body": pr["body"],
                "state": pr["state"].lower(), "is_draft": pr["isDraft"], "url": pr["url"],
                "created_at": created, "merged_at": epoch(pr["mergedAt"]), "closed_at": epoch(pr["closedAt"]),
                "labels": pr["labels"], "files": paths,
                "modules": sorted({mod(p) for p in paths}),
                "additions": pr["additions"], "deletions": pr["deletions"],
                "author_id": people.actor(pr["author"], created),
                "merged_by_id": people.actor(pr.get("mergedBy"), epoch(pr["mergedAt"])),
            })
            texts.append((pid, repo, f"{pr['title']}\n{pr['body'] or ''}", created))
            for ref in pr["closingIssuesReferences"]:
                r = ref["repository"]["nameWithOwner"]
                if (r, ref["number"]) in idx.numbers:
                    rows.closes.append({"pr_id": pid, "issue_id": issue_id(r, ref["number"]),
                                        "at": epoch(pr["mergedAt"]) or created})
            for rv in pr["reviews"]:
                at = epoch(rv["submittedAt"])
                reviewer = people.actor(rv["author"], at)
                if reviewer:
                    rows.reviews.append({"id": rv["id"], "person_id": reviewer, "pr_id": pid,
                                         "state": rv["state"].lower(), "at": at})
                if (rv["body"] or "").strip():
                    rows.comments.append(_comment(rv, pid, "review", people))
                for rc in rv["comments"]["nodes"]:
                    rows.comments.append(_comment(rc, pid, "review_comment", people))
            for cm in pr["comments"]:
                rows.comments.append(_comment(cm, pid, "comment", people))

        # Issues
        for issue in data["issues"] or []:
            iid = issue_id(repo, issue["number"])
            opened = epoch(issue["createdAt"])
            rows.issues.append({
                "id": iid, "number": issue["number"], "repo": repo, "title": issue["title"], "body": issue["body"],
                "state": issue["state"].lower(), "state_reason": (issue.get("stateReason") or "").lower() or None,
                "labels": issue["labels"], "url": issue["url"],
                "opened_at": opened, "closed_at": epoch(issue["closedAt"]),
                "author_id": people.actor(issue["author"], opened),
            })
            texts.append((iid, repo, f"{issue['title']}\n{issue['body'] or ''}", opened))
            for cm in issue["comments"]:
                rows.comments.append(_comment(cm, iid, "comment", people))

        # Docs
        for doc in data["docs"] or []:
            at = epoch(doc["updated_at"])
            did = doc_id(repo, doc["path"])
            rows.docs.append({
                "id": did, "path": doc["path"], "repo": repo, "title": _doc_title(doc["text"], doc["path"]),
                "text": doc["text"], "updated_at": at, "url": doc["url"], "module_id": mod(doc["path"]),
                "author_id": people.login(doc["last_author_login"], at) if doc.get("last_author_login") else None,
            })
            texts.append((did, repo, doc["text"], at))

        # Releases
        for rel in data["releases"] or []:
            at = epoch(rel["publishedAt"] or rel["createdAt"])
            rows.releases.append({"id": f"release:{repo}@{rel['tagName']}", "tag": rel["tagName"], "repo": repo,
                                  "name": rel["name"], "url": rel["url"], "at": at,
                                  "is_prerelease": rel["isPrerelease"]})

        for cm in rows.comments:
            if cm["repo"] is None:
                cm["repo"] = repo
                texts.append((cm["id"], repo, cm["body"], cm["at"]))

    for src, repo, text, at in texts:
        for dst in sorted(find_references(text, repo, idx) - {src}):
            rows.references.append({"src_id": src, "dst_id": dst, "at": at})

    rows.persons = people.finish()
    rows.modules = list(modules.values())
    return rows


def _comment(cm: dict, parent_id: str, kind: str, people: _People) -> dict[str, Any]:
    at = epoch(cm.get("createdAt") or cm.get("submittedAt"))
    return {"id": f"comment:{cm['id']}", "body": cm["body"], "at": at, "url": cm["url"], "kind": kind,
            "path": cm.get("path"), "parent_id": parent_id, "repo": None,
            "author_id": people.actor(cm["author"], at)}
