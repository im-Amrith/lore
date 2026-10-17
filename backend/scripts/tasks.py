"""Open triage Tasks for sandbox issues (the Librarian's step before Steward drafts them).

    uv run --directory backend python scripts/tasks.py                 # every open issue without a Task
    uv run --directory backend python scripts/tasks.py --issue 9 10    # just these issue numbers
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import get_settings  # noqa: E402
from lore.ingest.tasks import open_triage_tasks  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--issue", nargs="*", type=int, help="issue numbers in SANDBOX_REPO")
    a = p.parse_args()
    repo = get_settings().sandbox_repo
    if not repo:
        sys.exit("SANDBOX_REPO is not set")
    ids = [f"issue:{repo}#{n}" for n in a.issue] if a.issue else None
    rows = open_triage_tasks(repo.split("/")[0], repo, ids)
    for r in rows:
        print(f"  {r['task_id']}  {r['status']}")
    print(f"{len(rows)} triage task(s) open for {repo}")


if __name__ == "__main__":
    main()
