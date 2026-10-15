"""Fetch GitHub history into data/raw/<owner>/<repo>/ and print a volume summary.

    uv run --directory backend python scripts/fetch.py --repo FalkorDB/FalkorDB
    uv run --directory backend python scripts/fetch.py --org FalkorDB --since 2025-04-15
    uv run --directory backend python scripts/fetch.py --repo FalkorDB/FalkorDB --summary   # cached data only
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import FETCH_SINCE_DAYS, get_settings  # noqa: E402
from lore.ingest.github_fetch import GitHub, fetch_repo, list_org_repos, summarize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="append", default=[], help="owner/name (repeatable)")
    ap.add_argument("--org", help="fetch every non-fork, non-archived repo pushed since --since")
    ap.add_argument("--since", help="YYYY-MM-DD (default: ~18 months ago)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    ap.add_argument("--summary", action="store_true", help="only print the summary of cached data")
    args = ap.parse_args()

    since = (
        datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        if args.since else datetime.now(timezone.utc) - timedelta(days=FETCH_SINCE_DAYS)
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    targets = [tuple(r.split("/", 1)) for r in args.repo]
    gh = None
    if args.org:
        gh = GitHub(get_settings().github_token)
        targets += [(args.org, n) for n in list_org_repos(gh, args.org, since)]
    if not targets:
        ap.error("give --repo owner/name or --org org")

    if not args.summary:
        gh = gh or GitHub(get_settings().github_token)
        for owner, name in targets:
            fetch_repo(gh, owner, name, since, refresh=args.refresh)
        print(f"GraphQL calls this run: {gh.calls}")

    print("\nVolume summary")
    for owner, name in targets:
        print(json.dumps(summarize(owner, name), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
