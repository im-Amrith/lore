"""Run the golden set through the Navigator and score it; write docs/eval_results.md.

    uv run --directory backend python scripts/eval.py            # q01-q10, s01-s03, n01 (Bolt, not-found)
    uv run --directory backend python scripts/eval.py --only q05 q08
    (--no-cache: fresh LLM calls; --no-remember: don't write memory nodes)

Scoring is deterministic, no LLM judge. A question passes when:
  1. every must_cite URL is among the answer's citations,
  2. every key fact appears in the answer text (or one of its ALIASES below),
  3. every sentence shown carries at least one citation a tool returned,
  4. for not-found tests (expect_not_found), the answer says not found / no reason recorded.
Matching ignores case, spaces and hyphens ("Avi Avni" = "AviAvni", "12-minute" = "12 minute"),
and treats blob/main and tree/main as blob/HEAD, tree/HEAD (the default branch).
For each miss the table also says whether the URL came back from any tool (retrieved but
not cited) or never did (data, extraction or entry point), to help sort failures by cause.
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anyio
import yaml
from mcp.client import Client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lore.agents.navigator import ask, server_params  # noqa: E402
from lore.config import REPO_ROOT, get_settings  # noqa: E402

GOLDEN = REPO_ROOT / "docs" / "golden_set.yaml"
OUT = REPO_ROOT / "docs" / "eval_results.md"
EVAL_USER = "eval"

# Wordings that state the same key fact. Kept short and literal; each is a paraphrase a
# reviewer would accept as "mentions the fact".
ALIASES = {
    "nothing reads it": ["no longer exist", "no longer read", "nothing read", "no reader", "not read by", "unused"],
    "deletion": ["deleted", "delete"],
    "bus factor 1": ["bus factor of 1", "bus factor: 1", "single expert", "single-expert", "one active expert",
                     "only one expert", "single person", "one person"],
    "no owner listed": ["no owner is listed", "not listed", "no listed owner", "no owner in codeowners"],
    "12 minute": ["12 min"],
}
NOT_FOUND_PHRASES = ["not found", "no reason", "not recorded", "no recorded", "not given", "doesn't say",
                     "does not say", "not stated", "no rationale"]


def norm(s: str) -> str:
    return re.sub(r"[\s\-‐-―]+", "", (s or "").lower())


def norm_url(u: str) -> str:
    u = (u or "").strip().lower().rstrip("/")
    return u.replace("/blob/main/", "/blob/head/").replace("/tree/main/", "/tree/head/")


def has_fact(fact: str, text: str) -> bool:
    t = norm(text)
    return any(norm(f) in t for f in [fact, *ALIASES.get(fact, [])])


def cases(only: list[str] | None) -> list[dict]:
    g = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    sandbox_org = get_settings().sandbox_repo.split("/")[0] or "im-Amrith"
    out = [{**q, "org": q.get("org", "FalkorDB")} for q in g["questions"]]
    out += [{**q, "org": sandbox_org} for q in g["sandbox"]]
    out += [{**q, "org": "FalkorDB", "type": "not-found"} for q in g["spares"] if q.get("id")]
    return [c for c in out if not only or c["id"] in only]


def score(case: dict, r: dict) -> dict:
    cited_urls = {norm_url(c["url"]) for c in r["citations"] if c["url"]}
    retrieved = {norm_url(u) for u in r["sources"].values()}
    musts = case.get("must_cite") or []
    missing_cites = [u for u in musts if norm_url(u) not in cited_urls]
    facts = case.get("key_facts") or []
    missing_facts = [f for f in facts if not has_fact(f, r["answer"])]
    uncited = [s["text"] for s in r["sentences"] if not s["cites"]]
    checks = {"cites": not missing_cites, "facts": not missing_facts, "all_cited": not uncited}
    if case.get("expect_not_found"):
        checks["not_found"] = (not r["found"]) or any(p in r["answer"].lower() for p in NOT_FOUND_PHRASES)
    return {
        "pass": all(checks.values()), "checks": checks,
        "missing_cites": [(u, norm_url(u) in retrieved) for u in missing_cites],
        "missing_facts": missing_facts, "cites_hit": len(musts) - len(missing_cites), "cites_total": len(musts),
        "facts_hit": len(facts) - len(missing_facts), "facts_total": len(facts),
    }


def write_report(rows: list[tuple[dict, dict | None, dict | None, str | None]], started: str) -> None:
    golden = [x for x in rows if x[0]["id"].startswith("q")]
    passed_q = sum(1 for _, _, s, _ in golden if s and s["pass"])
    passed = sum(1 for _, _, s, _ in rows if s and s["pass"])
    lines = [
        "# Eval results", "",
        f"Run {started} by `scripts/eval.py` (Navigator via lore-mcp over stdio). Scoring is deterministic: "
        "every must_cite URL cited, every key fact mentioned, every shown sentence cited "
        "(and, for not-found tests, the answer says so). See the script's docstring.", "",
        f"**Golden q01-q10: {passed_q} of {len(golden)} pass. All checks: {passed} of {len(rows)}.**", "",
        "| id | type | pass | must_cite | key facts | tools | dropped | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case, r, s, err in rows:
        if err:
            lines.append(f"| {case['id']} | {case.get('type', '')} | ERROR | | | | | {err[:120]} |")
            continue
        notes = []
        for u, got in s["missing_cites"]:
            notes.append(f"missing cite {u.rsplit('/', 2)[-2:][-1]} ({'retrieved, not cited' if got else 'never retrieved'})")
        if s["missing_facts"]:
            notes.append("missing facts: " + ", ".join(s["missing_facts"]))
        if "not_found" in s["checks"] and not s["checks"]["not_found"]:
            notes.append("did not say not found")
        tools = ", ".join(c["tool"] for c in r["tool_calls"])
        lines.append(f"| {case['id']} | {case.get('type', '')} | {'PASS' if s['pass'] else 'FAIL'} | "
                     f"{s['cites_hit']}/{s['cites_total']} | {s['facts_hit']}/{s['facts_total']} | {tools} | "
                     f"{len(r['dropped'])} | {'; '.join(notes)} |")
    lines += ["", "## Answers", ""]
    for case, r, s, err in rows:
        lines += [f"### {case['id']}: {case['question']}", ""]
        if err:
            lines += [f"ERROR: {err}", ""]
            continue
        lines += [f"**{'PASS' if s['pass'] else 'FAIL'}** · intent {r['intent']} · model {r['model']} · "
                  f"tools: {', '.join(c['tool'] + ('(error)' if c['error'] else '') for c in r['tool_calls'])}", "",
                  r["answer"], ""]
        lines += [f"- [{c['n']}] `{c['id']}` {c['url'] or ''}" for c in r["citations"]]
        if r["dropped"]:
            lines += ["", "Dropped (cited nothing a tool returned):"]
            lines += [f"- {d['text']} `{d['cites']}`" for d in r["dropped"]]
        lines += ["", f"Expected: {' '.join(str(case.get('expected', case.get('expected_before_reversal', ''))).split())}", ""]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(only: list[str] | None, use_cache: bool, remember: bool) -> list:
    rows = []
    session = f"session:{EVAL_USER}:{datetime.now(timezone.utc):%Y-%m-%dT%H%M}"
    async with Client(server_params()) as client:
        for case in cases(only):
            print(f"\n== {case['id']} ({case['org']}) {case['question']}", flush=True)
            t0 = time.time()
            try:
                r = await ask(case["question"], case["org"], EVAL_USER, client, session_id=session,
                              remember=remember, use_cache=use_cache, verbose=True)
            except Exception as e:  # noqa: BLE001 - one failed question shouldn't stop the run
                print(f"   ERROR {type(e).__name__}: {e}", flush=True)
                rows.append((case, None, None, f"{type(e).__name__}: {e}"))
                continue
            s = score(case, r)
            print(f"   {'PASS' if s['pass'] else 'FAIL'} {s['checks']} ({time.time() - t0:.0f}s)\n   {r['answer']}",
                  flush=True)
            rows.append((case, r, s, None))
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="*", help="question ids, e.g. q01 s02")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-remember", action="store_true")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    started = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
    rows = anyio.run(run, a.only, not a.no_cache, not a.no_remember)
    if not a.only:
        write_report(rows, started)
        print(f"\nwrote {OUT}")
    golden = [s for c, _, s, _ in rows if c["id"].startswith("q")]
    print(f"golden: {sum(1 for s in golden if s and s['pass'])} of {len(golden)} pass; "
          f"all: {sum(1 for _, _, s, _ in rows if s and s['pass'])} of {len(rows)}")


if __name__ == "__main__":
    main()
