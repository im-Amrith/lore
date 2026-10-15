"""Load cached repos (data/raw) into FalkorDB and print counts per label and relationship type.

    uv run --directory backend python scripts/load.py --repo im-Amrith/lore-sandbox
    uv run --directory backend python scripts/load.py --repo FalkorDB/FalkorDB

The graph is lore_<owner of the first repo> unless --graph is given.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import graph_name  # noqa: E402
from lore.graph import get_graph, ro_query  # noqa: E402
from lore.ingest.load import load_rows  # noqa: E402
from lore.ingest.normalize import normalize_repos  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="append", required=True, help="owner/name (repeatable)")
    ap.add_argument("--graph", help="graph name (default lore_<owner>)")
    args = ap.parse_args()

    repos = [tuple(r.split("/", 1)) for r in args.repo]
    name = args.graph or graph_name(repos[0][0])
    print(f"== normalise {', '.join(args.repo)}")
    rows = normalize_repos(repos)
    print(f"== load into graph {name}")
    g = get_graph(name=name)
    load_rows(g, rows)

    print("\nNodes")
    for r in ro_query(g, "stats_nodes"):
        print(f"  {r['label']:<12} {r['count']}")
    print("Relationships")
    for r in ro_query(g, "stats_edges"):
        print(f"  {r['type']:<12} {r['count']}")
    print("\nSample (Person)-[:AUTHORED]->(PullRequest)-[:CLOSES]->(Issue)")
    for r in ro_query(g, "check_authored_closes", {"limit": 5}):
        print(f"  {r['person']} -> PR #{r['pr']} {r['pr_title'][:50]!r} -> #{r['issue']} {r['issue_title'][:50]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
