"""Chunk docs into DocChunk nodes, embed Decision / Issue / DocChunk text, create the vector
indexes (M6).

    uv run --directory backend python scripts/embed.py --org im-Amrith
    uv run --directory backend python scripts/embed.py --org FalkorDB

The first run downloads the embedding model into data/cache/fastembed. Embeddings are cached
per text, so re-running after a sync only computes new or changed texts.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import graph_name  # noqa: E402
from lore.graph import get_graph  # noqa: E402
from lore.ingest.embed import embed_graph  # noqa: E402
from lore.ingest.load import create_indexes  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", help="org whose graph to embed (lore_<org>)")
    ap.add_argument("--graph", help="graph name, instead of --org")
    args = ap.parse_args()
    if not (args.org or args.graph):
        ap.error("give --org or --graph")
    gname = args.graph or graph_name(args.org)
    g = get_graph(name=gname)
    t = time.time()
    print(f"== {gname}")
    create_indexes(g)
    embed_graph(g)
    print(f"done in {time.time() - t:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
