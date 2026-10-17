"""Pre-answer the live demo's questions so the answer cache serves them instantly on stage.

    uv run --directory backend python scripts/warm.py            # answer what isn't cached yet
    uv run --directory backend python scripts/warm.py --check    # only report cached / not cached

Questions: golden q01, q02, q05, q09, s01, s02 and the two live-triage issues from
docs/SANDBOX_STORY.md. An answer is cached under question + org + the graph's data version +
the prompt version, so re-run this after a load, sync, derive or prompt change. The UI must ask
these questions with the same wording (case, spaces and trailing ?.! don't matter).
Memory isn't written (user "warm").
"""

import argparse
import sys
import time
from pathlib import Path

import anyio
import yaml
from mcp.client import Client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.agents.navigator import _cache_path, ask, server_params  # noqa: E402
from lore.config import REPO_ROOT, get_settings  # noqa: E402

DEMO_IDS = ["q01", "q02", "q05", "q09", "s01", "s02"]
TRIAGE = [
    'New issue: "Links with capital letters 404 in the mobile app. Opening /Xk9fT2a from the iOS app shows '
    "'not found'; the same link works on desktop.\" What past work is related, and who should handle it?",
    'New issue: "Yesterday\'s clicks are missing from the CSV export." What past work is related, and who '
    "should handle it?",
]


def demo_questions() -> list[tuple[str, str, str]]:
    """(label, org, question) for every demo question."""
    g = yaml.safe_load((REPO_ROOT / "docs" / "golden_set.yaml").read_text(encoding="utf-8"))
    sandbox = get_settings().sandbox_repo.split("/")[0] or "im-Amrith"
    by_id = {q["id"]: (q.get("org", "FalkorDB"), q["question"]) for q in g["questions"]}
    by_id |= {q["id"]: (sandbox, q["question"]) for q in g["sandbox"]}
    out = [(i, *by_id[i]) for i in DEMO_IDS]
    out += [(f"triage{n + 1}", sandbox, q) for n, q in enumerate(TRIAGE)]
    return out


async def run(check: bool, pause: float) -> int:
    missing = 0
    async with Client(server_params()) as client:
        versions: dict[str, str] = {}
        for i, (label, org, q) in enumerate(demo_questions()):
            if org not in versions:
                dv = await client.call_tool("data_version", {"org": org})
                versions[org] = dv.structured_content["results"]["version"]
            if _cache_path(q, org, versions[org]).exists():
                print(f"  {label:8} cached      {q[:70]}")
                continue
            if check:
                missing += 1
                print(f"  {label:8} NOT CACHED  {q[:70]}")
                continue
            if i and pause:
                time.sleep(pause)
            try:
                r = await ask(q, org, "warm", client, remember=False)
            except Exception as e:  # noqa: BLE001 - keep warming the rest
                missing += 1
                print(f"  {label:8} FAILED      {type(e).__name__}: {str(e)[:150]}")
                continue
            eps = sorted({c.get("endpoint") or "?" for c in r["llm_calls"]})
            print(f"  {label:8} answered    {r['seconds']:5.1f}s {len(r['llm_calls'])} calls via {', '.join(eps)}"
                  f"{'' if r['found'] else '  (not found)'}")
    return missing


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="report only, no LLM calls")
    p.add_argument("--pause", type=float, default=5.0, help="seconds between fresh answers (default 5)")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    missing = anyio.run(run, a.check, a.pause)
    print(f"{'all demo questions cached' if not missing else f'{missing} not cached'}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
