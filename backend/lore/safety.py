"""Guards for anything that writes to GitHub.

Two checks, both enforced in code, both required before a triage comment goes out:
  1. allowlist: the target repo must be exactly SANDBOX_REPO. Any other repo (a real
     project like FalkorDB/FalkorDB) is refused, and an unset SANDBOX_REPO refuses everything.
  2. approval: a token the UI mints when a human clicks approve. It is an HMAC over the
     issue id and the exact draft text, so an agent can't reuse an approval for another
     issue or edit the comment after it was approved. The agents never hold the secret, so
     they can't mint tokens themselves.
"""

import hashlib
import hmac
import re

from lore.config import get_settings

ISSUE_ID_RE = re.compile(r"^issue:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$")


class WriteRefused(PermissionError):
    """A GitHub write that the allowlist or the approval check does not allow."""


def parse_issue_id(issue_id: str) -> tuple[str, int]:
    """issue:<owner>/<repo>#<n> -> ("owner/repo", n)."""
    m = ISSUE_ID_RE.match(issue_id or "")
    if not m:
        raise ValueError(f"not an issue id (issue:<owner>/<repo>#<n>): {issue_id!r}")
    return m.group(1), int(m.group(2))


def check_sandbox_repo(repo: str) -> str:
    """Return repo if it is the sandbox repo, else raise WriteRefused. GitHub names are
    case-insensitive, so the comparison is too."""
    sandbox = get_settings().sandbox_repo.strip()
    if not sandbox:
        raise WriteRefused("SANDBOX_REPO is not set, so no GitHub write is allowed")
    if repo.strip().lower() != sandbox.lower():
        raise WriteRefused(f"{repo} is not the sandbox repo; Lore only writes to {sandbox}")
    return repo


def _digest(issue_id: str, draft: str, secret: str) -> str:
    msg = f"{issue_id}\n{hashlib.sha256(draft.encode('utf-8')).hexdigest()}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def make_approval_token(issue_id: str, draft: str) -> str:
    """Called by the API when a human approves a draft (M13). Never exposed as a tool."""
    secret = get_settings().triage_approval_secret
    if not secret:
        raise WriteRefused("TRIAGE_APPROVAL_SECRET is not set, so approvals can't be made")
    return _digest(issue_id, draft, secret)


def check_approval(issue_id: str, draft: str, token: str) -> None:
    secret = get_settings().triage_approval_secret
    if not secret:
        raise WriteRefused("TRIAGE_APPROVAL_SECRET is not set, so no approval is valid")
    if not token or not hmac.compare_digest(_digest(issue_id, draft, secret), token):
        raise WriteRefused("approval token does not match this issue and draft; a human must approve it in the UI")
