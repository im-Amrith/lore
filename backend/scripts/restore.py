"""Local setup without GitHub or LLM keys: load the v0.1-snapshot graphs into the local FalkorDB.

    docker compose up -d falkordb
    uv run --directory backend python scripts/restore.py           # asks before replacing local graphs
    uv run --directory backend python scripts/restore.py --yes

1. Downloads lore.rdb, answers.tar.gz and SHA256SUMS from the GitHub release into data/snapshots/
   (skipped when already there and the checksums match) and verifies them.
2. Stops the FalkorDB container, copies lore.rdb in as its dump.rdb, starts it again: FalkorDB loads
   lore_falkordb and lore_im-amrith (knowledge, decisions, embeddings, triage Tasks) on start.
   This REPLACES every graph in that FalkorDB.
3. Unpacks the cached answers into data/cache/answers, so the demo questions answer without an LLM.
"""

import argparse
import hashlib
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from lore.config import ANSWER_CACHE_DIR, SNAPSHOTS_DIR  # noqa: E402
from lore.graph.client import get_db  # noqa: E402

RELEASE = "https://github.com/im-Amrith/lore/releases/download/v0.1-snapshot"
FILES = ("lore.rdb", "answers.tar.gz")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(name: str, url: str) -> Path:
    out = SNAPSHOTS_DIR / name
    with httpx.stream("GET", f"{url}/{name}", follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(out.with_suffix(out.suffix + ".part"), "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    out.with_suffix(out.suffix + ".part").replace(out)
    return out


def fetch(url: str) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    sums = {name: digest for digest, name in
            (line.split() for line in download("SHA256SUMS", url).read_text(encoding="utf-8").splitlines() if line)}
    for name in FILES:
        path = SNAPSHOTS_DIR / name
        if not (path.exists() and sha256(path) == sums[name]):
            print(f"downloading {name}")
            download(name, url)
        if sha256(path) != sums[name]:
            sys.exit(f"{name}: checksum mismatch")
        print(f"{name}: ok ({path.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--container", default="lore-falkordb")
    p.add_argument("--url", default=RELEASE, help="where the release assets are")
    p.add_argument("--yes", action="store_true", help="don't ask before replacing the local graphs")
    a = p.parse_args()

    fetch(a.url)
    if not a.yes and input(f"Replace every graph in container {a.container} with the snapshot? [y/N] ").lower() != "y":
        sys.exit("stopped; nothing replaced")
    docker = lambda *args: subprocess.run(["docker", *args], check=True, capture_output=True)  # noqa: E731
    docker("stop", a.container)  # a running FalkorDB would save its own data over the copy
    docker("cp", str(SNAPSHOTS_DIR / "lore.rdb"), f"{a.container}:/var/lib/falkordb/data/dump.rdb")
    docker("start", a.container)
    for _ in range(60):
        try:
            print(f"graphs: {sorted(get_db().list_graphs())}")
            break
        except Exception:  # noqa: BLE001 - still loading
            time.sleep(1)

    ANSWER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(SNAPSHOTS_DIR / "answers.tar.gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile() and not (ANSWER_CACHE_DIR / m.name).exists()]
        tf.extractall(ANSWER_CACHE_DIR, members=members, filter="data")
    print(f"cached answers: {len(members)} added to {ANSWER_CACHE_DIR}")


if __name__ == "__main__":
    main()
