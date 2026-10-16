"""Entry points (query 2) and similar issues (query 9) from the command line, plus the M6 check.

    uv run --directory backend python scripts/find.py --org FalkorDB "Why did the Rust engine drop all_nodes_matrix?"
    uv run --directory backend python scripts/find.py --org im-Amrith --issue "Links with capital letters 404 in the mobile app"
    uv run --directory backend python scripts/find.py --check     # golden "why" questions + sandbox triage

--check: q01-q04 and s01 must put the right decision in the top 3 (query 2); the demo triage
issues must return their planted related issues (query 9). Exit code 1 if any check fails.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import get_settings, graph_name  # noqa: E402
from lore.graph import get_graph  # noqa: E402
from lore.graph.search import find_start, similar_issues  # noqa: E402

# Golden "why" questions and the decision each must start from (DECIDED_IN source in brackets).
WHY_CHECKS = [
    ("FalkorDB", "q01", "Why did the Rust engine drop all_nodes_matrix?", "decision:2bf6caaed5caeaca"),  # PR 2678
    ("FalkorDB", "q02", "Why does the engine now fold MVCC deltas on every write?", "decision:1017616f47939a04"),  # PR 2349
    ("FalkorDB", "q03", "Why are there two branches, main and master?", "decision:10969052dbeec517"),  # PR 2279
    ("FalkorDB", "q04", "Why were graphblas.sh and redisearch.sh replaced with a native-deps crate?",
     "decision:8e1b8d4d5cc194f8"),  # PR 2695
    ("sandbox", "s01", "Why do we cache links in Redis?", "decision:3dd18586343e603b"),  # PR 11
    ("sandbox", "s01 ADR", "Why do we cache links in Redis?", "decision:07bda31bd72e1a95"),  # ADR 0001
]
# Demo triage issues (SANDBOX_STORY.md, "Live triage") and the issue numbers they must find.
TRIAGE_CHECKS = [
    ("Links with capital letters 404 in the mobile app",
     "Opening /Xk9fT2a from the iOS app shows 'not found'; the same link works on desktop.", {3}),
    ("Yesterday's clicks are missing from the CSV export", "", {4, 9}),
]
TOP = 3


def org_of(key: str) -> str:
    return get_settings().sandbox_repo.split("/")[0] if key == "sandbox" else key


def print_start(res: dict) -> None:
    print("decisions (vector + full-text, RRF x kind weight):")
    for i, r in enumerate(res["decisions"], 1):
        print(f"  {i}. {r['id']}  rank={r['rank']:.4f} vec#{r['vec_rank']} text#{r['text_rank']} "
              f"[{r['kind']}, {r['status']}] {', '.join(r['sources'])}\n     {r['statement'][:110]}")
    print("docs:");   [print(f"  {r['distance']:.3f} {r['id']}") for r in res["docs"][:3]]
    print("prs:");    [print(f"  {r['score']:.2f} #{r['number']} {r['title'][:90]}") for r in res["prs"][:3]]
    print("issues:"); [print(f"  {r['distance']:.3f} #{r['number']} {r['title'][:90]}") for r in res["issues"][:3]]


def print_similar(rows: list[dict]) -> None:
    for r in rows:
        mods = ", ".join(m.split(":", 2)[2] for m in r["modules"]) or "-"
        print(f"  {r['distance']:.3f} #{r['number']} [{r['state']}] {r['title'][:80]}\n"
              f"        fixed by: {', '.join(r['fixes']) or '-'} | modules: {mods}")


def check() -> int:
    failed = 0
    print(f"== query 2: right starting decision in the top {TOP}")
    for org, qid, q, want in WHY_CHECKS:
        ids = [r["id"] for r in find_start(get_graph(name=graph_name(org_of(org))), q, limit=5)["decisions"]]
        rank = ids.index(want) + 1 if want in ids else None
        ok = rank is not None and rank <= TOP
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'} {qid:8s} rank {rank or '-'}  {q}")
    print("== query 9: planted related issue among similar issues")
    g = get_graph(name=graph_name(org_of("sandbox")))
    for title, body, want in TRIAGE_CHECKS:
        rows = similar_issues(g, title, body)
        got = [r["number"] for r in rows]
        ok = want <= set(got[:TOP])
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'} \"{title}\" -> {got} (want {sorted(want)} in top {TOP})")
        print_similar(rows[:TOP])
    print(f"\n{'all checks passed' if not failed else f'{failed} check(s) failed'}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="question to find starting nodes for (query 2)")
    ap.add_argument("--org", help="org graph (lore_<org>)")
    ap.add_argument("--issue", help="new issue title: list similar issues (query 9)")
    ap.add_argument("--body", default="", help="new issue body, with --issue")
    ap.add_argument("--check", action="store_true", help="run the M6 golden checks")
    args = ap.parse_args()
    if args.check:
        return check()
    if not args.org or not (args.question or args.issue):
        ap.error("give --org and a question or --issue, or --check")
    g = get_graph(name=graph_name(args.org))
    if args.issue:
        print_similar(similar_issues(g, args.issue, args.body))
    else:
        print_start(find_start(g, args.question))
    return 0


if __name__ == "__main__":
    sys.exit(main())
