# Lore: project guide for Claude Code

Lore is an agent that turns a public GitHub org's history into a company graph in FalkorDB and answers "who owns this", "who knows this" and "why was this decided" with the traced path and links. It also triages new issues in a sandbox repo.

Built for the Graph Hacks hackathon (WeMakeDevs x FalkorDB), Oct 15 12:01 AM to Oct 18 11:59 PM IST.

## Environment and timeline

- **Machine:** Windows, PowerShell, Antigravity IDE, Claude Code CLI run from this `lore/` folder. Docker Desktop (WSL2 backend) runs FalkorDB.
- Give PowerShell commands, not bash. Write helper scripts in Python (cross-platform), never `.sh` or `.ps1`. Use `pathlib` for paths. Open text files with `encoding="utf-8"` (Windows defaults to cp1252).
- **Repo root is this `lore/` folder.** It is pushed to a public GitHub repo.
- **Work started Oct 15 ~7 PM IST,** so the build plan in `docs/PLAN.md` is compressed:

| When | Milestones | Gate |
| --- | --- | --- |
| Oct 15 night | M0 scaffold, M1 sandbox (human), M2 fetch | Raw data cached for the sandbox and FalkorDB/FalkorDB |
| Oct 16 | M3 load, M4 expertise, M5 decisions, M6 embeddings, M7 algorithms | Golden-set "who/owns/risk" questions right; decisions loaded |
| Oct 17 | M8 lore-mcp, M9 Navigator + eval, M10 API, M11 Ask screen, M13 Steward | 7 of 10 golden questions; demo flow works locally |
| Oct 18 (submit by 8 PM) | M14 deploy, M15 sync + supersession, M16 polish, M17 submission pack | Submitted naming all three tracks |

If a day slips, cut using the cut order in `docs/PLAN.md` (Risks and scope cuts). Never cut F1–F5, the evidence path or "show query".

- **Source of truth:** `docs/PLAN.md` (graph model, features F1–F10, the 12 core queries, agents, build plan). Read the relevant section before starting any milestone.
- **Milestone prompts:** `docs/PROMPTS.md`. Work one milestone at a time.
- **Golden set:** `docs/golden_set.yaml`, 10 hand-checked questions used as the eval. Its header lists data caveats about the FalkorDB repo (the `main-rs` history, bots, logins); respect them.
- **Topics:** `docs/TOPICS.md`, the fixed topic list for extraction.
- **Sandbox:** `docs/SANDBOX_STORY.md`, the synthetic `lore-sandbox` repo (Tern) and the demo moments it supports.

## Hackathon rules the code must respect

1. **FalkorDB is the product.** Every feature is a Cypher traversal or a FalkorDB graph algorithm. If a feature would still work with FalkorDB removed, redesign it. Vector search only picks the starting node.
2. **Public data only.** Public GitHub data of open-source orgs plus our own `lore-sandbox` repo. Never store email addresses. Never load private, login-protected or paywalled data.
3. **Main project code is written during the event** (from Oct 15). The docs in `docs/` were prepared before; all code is new.
4. **AI use must be disclosed.** Keep the "AI use" section of `README.md` current. The team must be able to explain every query and design choice, so explain non-obvious code when you write it.
5. **Required submission items:** public repo, README with setup + graph data model, the Cypher queries and algorithms used (in `queries/`), demo video, live deployment or full local setup, track names.

## Stack

- Python 3.11, `uv` for dependencies, FastAPI, the official `falkordb` Python client
- `lore-mcp`: our MCP tool server, built with the Python MCP SDK
- Next.js + Tailwind frontend; Cytoscape.js for the evidence path and maps
- FalkorDB in Docker locally (`falkordb/falkordb:latest`); FalkorDB Cloud for the deployed demo
- LLM: two OpenAI-compatible endpoints, one per role, called through the `openai` package with `base_url`: fast (Gemini: `LLM_FAST_BASE_URL`, `LLM_FAST_API_KEY`, `LLM_FAST_MODEL`) for extraction, smart (Groq: `LLM_SMART_BASE_URL`, `LLM_SMART_API_KEY`, `LLM_SMART_MODEL`) for the agents; keep one thin wrapper so endpoints can be swapped
- Embeddings: local `fastembed` with `BAAI/bge-small-en-v1.5` (384 dimensions). Free, no API key, works on Windows. `EMBEDDING_DIM=384`
- Pin exact versions in `pyproject.toml` and `package.json`

## Repository layout

```
lore/
  CLAUDE.md
  README.md
  docker-compose.yml        # FalkorDB (+ browser), backend
  .env.example              # every env var, no real values
  docs/                     # PLAN.md, PROMPTS.md, golden_set.yaml, AI_USE notes
  queries/                  # one .cypher file per query, numbered as in PLAN.md
  backend/
    lore/
      config.py             # env vars, graph names, embedding dimension, caps
      graph/                # FalkorDB client, schema + indexes, query loader
      ingest/               # github_fetch, normalize, load, modules, extract, embed, derive, sync
      llm/                  # LLM + embedding wrappers with disk cache and spend cap
      mcp_server/           # lore-mcp tools
      agents/               # navigator, steward, librarian
      api/                  # FastAPI routes
    scripts/                # CLI entry points (fetch, load, derive, ask, eval, snapshot)
    tests/
  frontend/
  data/                     # gitignored except data/snapshots/README.md
    raw/<org>/              # cached GitHub JSON
    cache/llm/              # cached LLM and embedding outputs
    snapshots/              # demo snapshot
```

Update the command list below whenever you add a script.

## Commands

PowerShell, from the `lore/` folder:

```
docker compose up -d falkordb                 # FalkorDB on 6379, browser on http://localhost:3000
cd backend; uv sync; cd ..                    # backend deps
uv run --directory backend python scripts/healthcheck.py
uv run --directory backend pytest             # unit tests
uv run --directory backend python scripts/fetch.py --repo FalkorDB/FalkorDB   # GitHub -> data/raw (cached; --refresh, --since, --org, --summary)
uv run --directory backend python scripts/load.py --repo im-Amrith/lore-sandbox  # data/raw -> graph lore_<owner>; prints counts
uv run --directory backend python scripts/derive.py --org FalkorDB --report --algo  # rebuild EXPERT_IN, COLLABORATES, CO_CHANGED; print queries 5-7 and 8 (--module <id>, --impact <id>: query 10, --now <date>, --no-derive)
uv run --directory backend python scripts/extract.py --repo FalkorDB/FalkorDB --sample 30   # LLM decisions + topics, printed (--list: no LLM; --load: write; --all-prs: sandbox)
uv run --directory backend python scripts/embed.py --org FalkorDB     # chunk docs, embed Decision/Issue/DocChunk, vector indexes
uv run --directory backend python scripts/find.py --org FalkorDB "Why ...?"   # query 2 entry points (--issue "title": query 9; --check: M6 golden checks)
uv run --directory backend python -m lore.mcp_server            # lore-mcp tool server over stdio (ten tools)
# add: ask, eval, serve commands as they are created
```

## Conventions

**Cypher**
- Every query lives in `queries/NN_name.cypher` and is loaded by name. No Cypher strings scattered in Python, except tiny one-off checks in tests.
- Always use parameters (`$module`, `$now`). Never format user input into a query string.
- Use read-only execution (`ro_query`) for everything except loaders, derive jobs, `remember`, Task updates and sync.
- FalkorDB is not Neo4j: no APOC, no GDS. Algorithms are `CALL algo.pageRank(...)`, `algo.betweenness({...})`, `algo.labelPropagation({...})`, `algo.BFS`, `algo.SPpaths`, `algo.SSpaths`. Vector search is `db.idx.vector.queryNodes(label, attr, k, vecf32($v))`; full-text is `db.idx.fulltext.queryNodes(label, $text)`. When unsure about syntax, check https://docs.falkordb.com/llms.txt and the known-limitations page instead of guessing.
- **Before wiring a new or changed query into code, run it against the local FalkorDB** with realistic parameters and show the result. A query is not done until it has returned sensible rows.
- Batch writes with `UNWIND $rows AS row ... MERGE`, about 500 rows per batch.

**Data**
- Timestamps: epoch seconds, UTC, in properties named `at`, `*_at`.
- Stable ids: `pr:<owner>/<repo>#<n>`, `issue:<owner>/<repo>#<n>`, `commit:<sha>`, `person:<login>`, `module:<repo>:<path>`, `decision:<hash>`.
- One graph per org, named `lore_<org>` (lowercase). Memory nodes live in the same graph.
- Raw GitHub responses are cached in `data/raw/`; never re-fetch something already cached unless syncing.

**LLM and embeddings**
- All LLM and embedding calls go through `backend/lore/llm/`, which caches results on disk keyed by a hash of model + prompt + input, and refuses calls past `LLM_DAILY_CALL_CAP`.
- One embedding model everywhere; its dimension is set once in `config.py` and used by the vector indexes.
- Before any full-dataset LLM run, do a sample run (about 30 items), print the results, and stop for review.

**Agents**
- Agents reach the graph only through `lore-mcp` tools (the Librarian's loaders are the exception).
- Answers are built only from tool results. Every claim carries the node id it came from; the API returns the answer, the subgraph (node and edge ids) and the Cypher that ran.
- No path found means say "not found" and show the nearest evidence. Never guess.
- Navigator: at most 4 tool calls per question.

**Safety**
- `post_triage` and any GitHub write may only target the repo in `SANDBOX_REPO`, enforced in code with an allowlist check, and only after an explicit approval from the UI.
- Secrets only in `.env` (gitignored). Never commit, print or log tokens or keys. Keep `.env.example` in sync with every new variable.
- Rate-limit public endpoints that call the LLM.

## How to work in this repo

- Work one milestone from `docs/PROMPTS.md` at a time. Propose a short plan first, then build.
- Time is short: prefer the simplest thing that meets the milestone's "Done when". No speculative abstractions.
- Commit after each working step with a clear message. Small commits make the work during the event easy to show.
- At each milestone's "Done when" check, run the check, show the output, and stop. Don't start the next milestone unasked.
- Stay inside `docs/PLAN.md`. Ask before adding features, dependencies or services it doesn't mention. If time is short, follow the plan's cut order.
- Write tests for normalisation, id building, module mapping and the sandbox allowlist. Graph queries are checked by running them, plus `scripts/eval` against the golden set.
- Keep `README.md` current: setup, graph model, query list, architecture, AI use.

**Ask the human before:**
- deleting or dropping a graph, index or cached data
- any write to GitHub
- a full LLM extraction run, or any step likely to cost more than a few dollars
- changing the graph model in `docs/PLAN.md`
- skipping a failed "Done when" check
