"""Check FalkorDB is reachable: run queries/00_healthcheck.cypher and print the node.

    uv run --directory backend python scripts/healthcheck.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import HEALTHCHECK_GRAPH, get_settings  # noqa: E402
from lore.graph import get_graph, query  # noqa: E402


def main() -> int:
    s = get_settings()
    try:
        g = get_graph(name=HEALTHCHECK_GRAPH)
        rows = query(g, "healthcheck", {"now": int(time.time())})
    except Exception as e:  # connection errors, query errors
        print(f"FAIL: FalkorDB at {s.falkordb_host}:{s.falkordb_port}: {e}")
        return 1
    print(f"OK: FalkorDB at {s.falkordb_host}:{s.falkordb_port}, graph {HEALTHCHECK_GRAPH}")
    for row in rows:
        print(f"  test node: {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
