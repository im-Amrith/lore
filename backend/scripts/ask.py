"""Ask the Navigator a question as a given user; print the answer, the path and the Cypher.

    uv run --directory backend python scripts/ask.py --org FalkorDB --user amrith "Who knows the Cypher parser?"
    (--no-remember: don't write memory nodes; --brief: Cypher query names only; --json: raw result)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.agents.navigator import ask_sync  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question")
    p.add_argument("--org", default="FalkorDB")
    p.add_argument("--user", default="cli")
    p.add_argument("--session", help="session id to continue (default: one per user per day)")
    p.add_argument("--no-remember", action="store_true")
    p.add_argument("--no-cache", action="store_true", help="skip the LLM response cache")
    p.add_argument("--brief", action="store_true", help="print Cypher query names, not the text")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    r = ask_sync(a.question, a.org, a.user, session_id=a.session, remember=not a.no_remember,
                 use_cache=not a.no_cache, verbose=True)
    if a.json:
        print(json.dumps(r, indent=2, default=str))
        return

    print(f"\nQ ({r['user']} @ {r['org']}, intent {r['intent']}, model {r['model']}): {r['question']}\n")
    print(r["answer"], "\n")
    for c in r["citations"]:
        print(f"  [{c['n']}] {c['id']}  {c['url'] or ''}")
    if r["dropped"]:
        print(f"\n  dropped {len(r['dropped'])} sentence(s) citing nothing a tool returned:")
        for s in r["dropped"]:
            print(f"    - {s['text']}  {s['cites']}")
    print("\nPath (edges touching a cited node):")
    for e in r["path"][:40]:
        print(f"  ({e['source']})-[:{e['type']}]->({e['target']})")
    if len(r["path"]) > 40:
        print(f"  ... {len(r['path']) - 40} more")
    print("\nTool calls:")
    for c in r["tool_calls"]:
        args = {k: v for k, v in c["args"].items() if k not in ("org", "user_id")}
        print(f"  {c['tool']} {json.dumps(args)}" + (f"  ERROR {c['error']}" if c["error"] else ""))
    print("\nCypher:")
    for c in r["cypher"]:
        print(f"\n// {c['tool']} -> {c['query']}  params={json.dumps(c['params'], default=str)}  rows={c['rows']}")
        if not a.brief:
            print(c["cypher"].strip())
    if r.get("memory"):
        print(f"\nRemembered in {r['session_id']}: {r['memory']}")


if __name__ == "__main__":
    main()
