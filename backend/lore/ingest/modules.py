"""Map file paths to modules, and parse CODEOWNERS.

A module is a directory: the file's first MODULE_DEPTH directories (one level
deeper under a repo's MODULE_DEEP_PREFIXES), unless a CODEOWNERS directory
pattern contains the file, in which case the longest such pattern wins.
Files at the repo root belong to the module "/".
"""

from __future__ import annotations

from dataclasses import dataclass

from lore.config import MODULE_DEEP_PREFIXES, MODULE_DEPTH

ROOT = "/"


@dataclass(frozen=True)
class OwnerRule:
    pattern: str        # as written in CODEOWNERS
    owners: list[str]   # "@login" or "@org/team" (emails are skipped)
    directory: str | None  # "api" for "/api/"; None for file or glob patterns


def parse_codeowners(text: str) -> list[OwnerRule]:
    rules = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        owners = [o for o in owners if o.startswith("@")]
        rules.append(OwnerRule(pattern, owners, _pattern_dir(pattern)))
    return rules


def _pattern_dir(pattern: str) -> str | None:
    """'/api/' or 'api/' -> 'api'; '/build/**' -> 'build'. Globs and single files -> None.

    Unanchored directory patterns ('docs/') can match at any depth in git; we
    treat them as root-anchored, which is what small repos mean by them.
    """
    p = pattern.strip("/")
    if p.endswith("/**"):
        p = p[:-3]
    if not p or any(ch in p for ch in "*?[") or not pattern.rstrip("*").endswith("/"):
        return None
    return p


def module_path(path: str, repo: str, owner_dirs: list[str] = ()) -> str:
    """Module of a file path in repo ('owner/name')."""
    containing = [d for d in owner_dirs if path.startswith(d + "/")]
    if containing:
        return max(containing, key=len)
    dirs = path.split("/")[:-1]
    depth = MODULE_DEPTH
    for prefix in MODULE_DEEP_PREFIXES.get(repo, []):
        if path.startswith(prefix + "/"):
            depth = max(depth, prefix.count("/") + 2)
    return "/".join(dirs[:depth]) or ROOT


def rule_module(rule: OwnerRule, repo: str, owner_dirs: list[str]) -> str | None:
    """The module a CODEOWNERS rule owns: its directory, or the module of a single file. Globs -> None."""
    if rule.directory:
        return rule.directory
    p = rule.pattern.lstrip("/")
    if any(ch in p for ch in "*?[") or not p:
        return None
    return module_path(p, repo, owner_dirs)
