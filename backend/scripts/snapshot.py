"""Snapshot the local graphs for deployment and the local setup: the v0.1-snapshot release assets.

    uv run --directory backend python scripts/snapshot.py                 # container lore-falkordb
    uv run --directory backend python scripts/snapshot.py --no-export     # only re-package
    gh release create v0.1-snapshot data/snapshots/lore.rdb data/snapshots/answers.tar.gz data/snapshots/SHA256SUMS

1. BGSAVE on the local FalkorDB and wait for it, so dump.rdb holds every graph as it is now
   (lore_falkordb, lore_im-amrith: knowledge, decisions, embeddings, Tasks with drafts).
2. Copy the dump out of the Docker container to data/snapshots/lore.rdb.
3. Check that no string property in any org graph looks like an email address (the repo is
   public and Lore never stores emails); refuse to keep the snapshot if one does.
4. Pack data/cache/answers into data/snapshots/answers.tar.gz: a server loaded from this dump has
   the same data version, so these cached answers are hits there and pre-warming costs no LLM calls.
5. Write data/snapshots/SHA256SUMS for both files.
These are not committed (data/snapshots/* is gitignored): they go to the GitHub release, which
deploy/ec2-setup.sh and scripts/restore.py download. Nothing is fetched or extracted at deploy time.
"""

import argparse
import hashlib
import re
import subprocess
import tarfile
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import ANSWER_CACHE_DIR, SNAPSHOTS_DIR, get_settings, graph_name  # noqa: E402
from lore.graph.client import get_db  # noqa: E402

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def bgsave(r) -> None:
    before = r.lastsave()
    r.bgsave()
    for _ in range(120):
        time.sleep(1)
        if r.lastsave() != before:
            info = r.info("persistence")
            if info.get("rdb_last_bgsave_status") != "ok":
                sys.exit(f"BGSAVE failed: {info.get('rdb_last_bgsave_status')}")
            return
    sys.exit("BGSAVE did not finish in 2 minutes")


def email_like(graph) -> int:
    hits, skip = 0, 0
    while rows := graph.ro_query("MATCH (n) RETURN properties(n) SKIP $s LIMIT 2000", {"s": skip}).result_set:
        for (props,) in rows:
            for v in props.values():
                hits += sum(1 for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) and EMAIL.search(x))
        skip += 2000
    return hits


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--container", default="lore-falkordb")
    p.add_argument("--path", default="/var/lib/falkordb/data/dump.rdb", help="dump.rdb inside the container")
    p.add_argument("--no-export", action="store_true", help="keep data/snapshots/lore.rdb; only re-package")
    a = p.parse_args()
    out = SNAPSHOTS_DIR / "lore.rdb"
    if not a.no_export:
        export(a)
    elif not out.exists():
        sys.exit(f"{out} doesn't exist; run without --no-export")
    package(out)


def export(a) -> None:
    db = get_db()
    s = get_settings()
    orgs = [s.demo_org] + ([s.sandbox_repo.split("/")[0]] if s.sandbox_repo else [])
    for org in orgs:
        n = email_like(db.select_graph(graph_name(org)))
        print(f"{graph_name(org)}: {n} email-like strings")
        if n:
            sys.exit("refusing to snapshot: a graph holds email addresses")

    bgsave(db.connection)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOTS_DIR / "lore.rdb"
    subprocess.run(["docker", "cp", f"{a.container}:{a.path}", str(out)], check=True, capture_output=True)
    print(f"{out}: {out.stat().st_size / 1e6:.1f} MB, graphs {sorted(g for g in db.list_graphs())}")


def package(rdb) -> None:
    tar = SNAPSHOTS_DIR / "answers.tar.gz"
    files = sorted(ANSWER_CACHE_DIR.rglob("*.json")) if ANSWER_CACHE_DIR.exists() else []
    with tarfile.open(tar, "w:gz") as tf:  # paths relative to the answers dir: <2 hex>/<key>.json
        for f in files:
            tf.add(f, arcname=f.relative_to(ANSWER_CACHE_DIR).as_posix())
    print(f"{tar}: {len(files)} cached answers")
    sums = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" for f in (rdb, tar)]
    (SNAPSHOTS_DIR / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(sums))


if __name__ == "__main__":
    main()
