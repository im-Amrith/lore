"""Run the derive jobs (queries/04_expert_*) on a graph, then optionally print the
expertise report (queries 5, 6 and 7).

    uv run --directory backend python scripts/derive.py --graph lore_falkordb --report
    uv run --directory backend python scripts/derive.py --org im-Amrith --report --module module:lore-sandbox:storage
    uv run --directory backend python scripts/derive.py --graph lore_falkordb --now 2026-10-10   # "as of" a date

EXPERT_IN is dropped and rebuilt each run: authored commits, then reviews at half weight,
then the combined score. Bots and bulk commits are skipped.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import (  # noqa: E402
    BUS_FACTOR_MIN_SCORE,
    BUS_FACTOR_MIN_SHARE,
    BUS_FACTOR_WINDOW,
    graph_name,
)
from lore.graph import get_graph, query, ro_query  # noqa: E402

DERIVE_JOBS = ["expert_reset", "expert_authored", "expert_reviewed", "expert_score"]


def parse_now(value: str | None) -> int:
    if not value:
        return int(time.time())
    if value.isdigit():
        return int(value)
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def day(ts: int | None) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else "-"


def derive(g, now: int) -> None:
    for job in DERIVE_JOBS:
        t = time.perf_counter()
        rows = query(g, job, {"now": now})
        print(f"  {job:<16} {rows[0] if rows else {}}  ({time.perf_counter() - t:.2f}s)")


def report(g, now: int, modules: list[str], top: int) -> None:
    for module in modules:
        print(f"\n[05 who_knows] {module}")
        rows = ro_query(g, "who_knows", {"module": module})
        if not rows:
            print("  not found: no one with score > 0.5")
        for r in rows:
            print(f"  {r['person']:<16} score {r['score']:6.1f} (authored {r['authored'] or 0:.1f}, "
                  f"reviewed {r['reviewed'] or 0:.1f}) last {day(r['last_touch'])}  "
                  f"{r['evidence'] or r['evidence_commits'] or r['evidence_reviews']}")
        print(f"[06 module_owners] {module}")
        for r in ro_query(g, "module_owners", {"module": module, "now": now}):
            owners = ", ".join(f"{o['kind']} {o['name']}{' (paper)' if o['paper'] else ''}" for o in r["owners"])
            experts = ", ".join(f"{e['person']} {e['score']:.1f}" for e in r["active_experts"])
            print(f"  listed owner: {owners if r['listed_owner'] else 'no listed owner'} | experts: {experts}")

    print("\n[06 paper_owners]")
    rows = ro_query(g, "paper_owners", {"now": now})
    if not rows:
        print("  none")
    for r in rows:
        via = f" via team {r['via_team']}" if r["via_team"] else ""
        print(f"  {r['module']:<20} {r['paper_owner']}{via}, last touch {day(r['owner_last_touch'])}"
              f" | real experts: {r['active_experts']}")

    print("\n[06 team_owners]")
    for r in ro_query(g, "team_owners", {"now": now}):
        experts = ", ".join(f"{e['person']} {e['score']:.1f}" for e in r["active_experts"])
        print(f"  {r['module']:<20} team {r['team']} (members known: {r['members'] or 'none'}) | experts: {experts}")

    print(f"\n[07 bus_factor] min_score {BUS_FACTOR_MIN_SCORE}, min_share {BUS_FACTOR_MIN_SHARE}, "
          f"window {BUS_FACTOR_WINDOW // 86400}d (top {top})")
    params = {"now": now, "min_score": BUS_FACTOR_MIN_SCORE,
              "min_share": BUS_FACTOR_MIN_SHARE, "window": BUS_FACTOR_WINDOW}
    for r in ro_query(g, "bus_factor", params)[:top]:
        experts = ", ".join(f"{p} {s:.0f}%" for p, s in zip(r["experts"], r["share_pct"]))
        print(f"  {r['module']:<24} bus_factor {r['bus_factor']}  total {r['total_score']:6.1f}  {experts}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--org", help="org or owner; graph is lore_<org>")
    target.add_argument("--graph", help="explicit graph name")
    ap.add_argument("--now", help="epoch seconds or ISO date (default: current time)")
    ap.add_argument("--report", action="store_true", help="print queries 5-7 after deriving")
    ap.add_argument("--no-derive", action="store_true", help="only print the report")
    ap.add_argument("--module", action="append", default=[], help="module id for who-knows/owners (repeatable)")
    ap.add_argument("--top", type=int, default=25, help="bus-factor rows to print")
    args = ap.parse_args()

    name = args.graph or graph_name(args.org)
    now = parse_now(args.now)
    g = get_graph(name=name)
    print(f"== {name}, now = {now} ({day(now)})")
    if not args.no_derive:
        derive(g, now)
    if args.report or args.no_derive:
        report(g, now, args.module, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
