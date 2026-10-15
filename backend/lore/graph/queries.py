"""Load Cypher from queries/NN_name.cypher by name.

`load_query("healthcheck")` and `load_query("00_healthcheck")` both resolve to
queries/00_healthcheck.cypher.
"""

import re
from functools import lru_cache
from pathlib import Path

from lore.config import QUERIES_DIR

_FILE_RE = re.compile(r"^(\d+)_(.+)\.cypher$")


def _index(queries_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted(queries_dir.glob("*.cypher")):
        m = _FILE_RE.match(path.name)
        if not m:
            continue
        for key in (m.group(2), path.stem):
            if key in index and index[key] != path:
                raise ValueError(f"Duplicate query name {key!r}: {index[key].name}, {path.name}")
            index[key] = path
    return index


@lru_cache
def load_query(name: str, queries_dir: Path = QUERIES_DIR) -> str:
    index = _index(queries_dir)
    if name not in index:
        raise KeyError(f"No query named {name!r} in {queries_dir}")
    return index[name].read_text(encoding="utf-8")
