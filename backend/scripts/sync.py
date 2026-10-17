"""Incremental sync of the sandbox repo (M15): a merged PR updates the graph. See lore/ingest/sync.py.

    uv run --directory backend python scripts/sync.py --check          # sync any PR merged on GitHub but not in the graph
    uv run --directory backend python scripts/sync.py --pr 16          # sync PR #16 (after it was merged)
    uv run --directory backend python scripts/sync.py --prime          # fetch the raw cache once (fresh server)

Test only, never against the live graph: --simulate-merge treats the PR as merged now and reads its
commits and docs from its head branch. Point it at a test FalkorDB (FALKORDB_PORT) and a copy of the
raw cache (LORE_RAW_DIR); nothing is merged or written on GitHub.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import get_settings  # noqa: E402
from lore.ingest.sync import prime, sync_check, sync_merged  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pr", type=int, action="append", help="PR number in SANDBOX_REPO (repeatable)")
    p.add_argument("--check", action="store_true", help="find merged PRs the graph lacks and sync them")
    p.add_argument("--prime", action="store_true", help="fetch the raw cache if this machine has none")
    p.add_argument("--simulate-merge", action="store_true", help="TEST ONLY: treat --pr as merged now")
    a = p.parse_args()
    repo = get_settings().sandbox_repo
    if not repo:
        sys.exit("SANDBOX_REPO is not set")
    if a.prime:
        print("raw cache fetched" if prime(repo) else "raw cache already there")
    if a.check:
        r = sync_check(repo)
        print(json.dumps(r, indent=1, default=str) if r else "nothing merged since the last sync")
    if a.pr:
        print(json.dumps(sync_merged(repo, a.pr, simulate=a.simulate_merge), indent=1, default=str))


if __name__ == "__main__":
    main()
