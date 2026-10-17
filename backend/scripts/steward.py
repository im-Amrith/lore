"""Steward as a standalone worker: check SANDBOX_REPO for new issues, then claim and draft open Tasks.

    uv run --directory backend python scripts/steward.py              # one pass
    uv run --directory backend python scripts/steward.py --poll 60    # every 60 s until Ctrl+C
    uv run --directory backend python scripts/steward.py --no-intake  # only draft Tasks already open

The API runs the same loop itself (STEWARD_POLL_SECONDS); running both is safe: each Task is taken
by one worker through the atomic claim. Graph access goes through lore-mcp over stdio. Nothing is
posted: approving a draft in the triage inbox does that.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anyio  # noqa: E402
from mcp.client import Client  # noqa: E402

from lore.agents import steward  # noqa: E402
from lore.agents.navigator import server_params  # noqa: E402
from lore.config import get_settings  # noqa: E402
from lore.ingest.live import intake  # noqa: E402


async def one_pass(client: Client, repo: str, agent: str, do_intake: bool) -> None:
    if do_intake:
        taken = intake(repo)
        print(f"intake: {len(taken['loaded'])} new issue(s) {taken['loaded']}, {len(taken['tasks'])} Task(s) opened")
    for r in await steward.run_once(client, repo.split("/")[0], agent, log=print):
        if r["status"] == "drafted":
            print(f"\n--- {r['task_id']} (Playbook v{r['playbook_version']}, {r['model']})\n{r['draft']}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--poll", type=int, default=0, metavar="SECONDS", help="repeat every SECONDS")
    p.add_argument("--no-intake", action="store_true", help="don't check GitHub for new issues")
    a = p.parse_args()
    repo = get_settings().sandbox_repo
    if not repo:
        sys.exit("SANDBOX_REPO is not set")
    agent = steward.agent_name()

    async def run() -> None:
        async with Client(server_params()) as client:
            while True:
                await one_pass(client, repo, agent, not a.no_intake)
                if not a.poll:
                    return
                await anyio.sleep(a.poll)
    print(f"{agent} on {repo}" + (f", every {a.poll} s" if a.poll else ""))
    try:
        anyio.run(run)
    except KeyboardInterrupt:
        print("stopped")
    time.sleep(0)


if __name__ == "__main__":
    main()
