"""Extract decisions and topic tags from a loaded repo with the fast LLM, print them next to
their sources, and (with --load) write them to the graph.

    uv run --directory backend python scripts/extract.py --repo FalkorDB/FalkorDB --list          # candidates only, no LLM
    uv run --directory backend python scripts/extract.py --repo FalkorDB/FalkorDB --sample 30     # sample run, print, no load
    uv run --directory backend python scripts/extract.py --repo FalkorDB/FalkorDB --load          # full run (ask first)
    uv run --directory backend python scripts/extract.py --repo im-Amrith/lore-sandbox --all-prs --load

Results are cached (data/cache/llm), so re-running a sample or a full run after a sample
only pays for new candidates. A review file is written to data/cache/extract/.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.config import CACHE_DIR, DECISION_MIN_CONFIDENCE, graph_name  # noqa: E402
from lore.graph import get_graph  # noqa: E402
from lore.ingest.extract import (  # noqa: E402
    Extraction,
    extract,
    load_candidates,
    load_extractions,
    sample,
    source_text,
)
from lore.llm import calls_today  # noqa: E402


def render(results: list[Extraction]) -> str:
    out = []
    n = 0
    for r in results:
        c = r.candidate
        out.append(f"\n## {c.label}: {c.title}\n{c.url}")
        out.append(f"topics: {', '.join(r.topics) or '-'} | status: {c.status} | modules offered: {len(c.modules)}")
        if r.error:
            out.append(f"ERROR: {r.error}")
            continue
        if not r.decisions:
            out.append("(no decisions)")
        for d in r.decisions:
            n += 1
            used = "" if d["confidence"] >= DECISION_MIN_CONFIDENCE else "   << below 0.6, excluded from answers"
            out.append(f"\n  [{n}] ({d['kind']}) {d['statement']}")
            out.append(f"      why:          {d['rationale'] or '(not stated)'}")
            out.append(f"      alternatives: {'; '.join(d['alternatives']) or '-'}")
            out.append(f"      modules:      {', '.join(m.split(':', 2)[2] for m in d['affected_modules']) or '-'}")
            out.append(f"      proposed_by:  {', '.join(d['proposed_by']) or '-'} | approved_by: {', '.join(d['approved_by']) or '-'}")
            out.append(f"      topics:       {', '.join(d['topics'])}")
            out.append(f"      quote:        \"{d['quote']}\" (match {d['quote_match']:.2f}"
                       f"{'' if d['quote_verified'] else ', NOT FOUND in source'})")
            out.append(f"      confidence:   {d['confidence']:.2f} (llm {d['llm_confidence']:.2f}){used}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name, already loaded")
    ap.add_argument("--graph", help="graph name (default lore_<owner>)")
    ap.add_argument("--sample", type=int, help="extract only N candidates (must-include PRs first)")
    ap.add_argument("--all-prs", action="store_true", help="every PR, open and draft included (sandbox)")
    ap.add_argument("--list", action="store_true", help="list candidates and prompt sizes; no LLM calls")
    ap.add_argument("--show-prompt", help="print the prompt text for one candidate id and exit")
    ap.add_argument("--load", action="store_true", help="write the decisions to the graph")
    args = ap.parse_args()

    owner, name = args.repo.split("/", 1)
    gname = args.graph or graph_name(owner)
    g = get_graph(name=gname)
    cands = load_candidates(g, args.repo, all_prs=args.all_prs)
    kinds = {k: sum(c.kind == k for c in cands) for k in ("pr", "issue", "doc")}
    print(f"== {args.repo} -> {gname}: {len(cands)} candidates ({kinds['pr']} PRs, {kinds['issue']} issues, {kinds['doc']} docs)")

    if args.show_prompt:
        c = next(c for c in cands if c.id == args.show_prompt)
        print(source_text(c))
        return 0
    if args.sample:
        cands = sample(cands, args.sample, args.repo)
    if args.list:
        for c in cands:
            print(f"  {c.label:<34} {len(source_text(c)):>6} chars  {len(c.modules):>2} modules  {c.url}")
        return 0

    print(f"== extracting {len(cands)} (LLM calls today so far: {calls_today()})")
    results = extract(cands, args.repo, owner)
    text = render(results)
    print(text)

    n_dec = sum(len(r.decisions) for r in results)
    n_used = sum(d["confidence"] >= DECISION_MIN_CONFIDENCE for r in results for d in r.decisions)
    n_err = sum(r.error is not None for r in results)
    print(f"\n== {len(results)} candidates, {n_dec} decisions ({n_used} at confidence >= {DECISION_MIN_CONFIDENCE}), "
          f"{n_err} errors. LLM calls today: {calls_today()}")

    out_dir = CACHE_DIR / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{owner}_{name}_{'sample' + str(args.sample) if args.sample else 'full'}"
    (out_dir / f"{tag}.md").write_text(text, encoding="utf-8")
    (out_dir / f"{tag}.json").write_text(json.dumps(
        [{"source": r.candidate.id, "url": r.candidate.url, "topics": r.topics, "error": r.error,
          "decisions": r.decisions} for r in results], indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"== review file: {out_dir / (tag + '.md')}")

    if args.load:
        print(f"== load into {gname}")
        load_extractions(g, results, owner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
