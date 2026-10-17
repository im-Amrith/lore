# Lore

## What it is

Lore is an agent that turns a public GitHub org's history into a company graph in FalkorDB. It answers "who owns this", "who knows this" and "why was this decided" with the traced graph path and links to the source. It also triages new issues in a sandbox repo.

Built for Graph Hacks (WeMakeDevs x FalkorDB), Oct 15–18, 2026.

## Tracks

_TBD. All three tracks will be named here at submission._

## Architecture

_TBD._ Python backend (FastAPI, the official `falkordb` client, `lore-mcp` tool server, agents), a Next.js + Tailwind frontend with Cytoscape.js, and FalkorDB (Docker locally, FalkorDB Cloud for the demo).

## Graph data model

_TBD._ One graph per org, `lore_<org>`. The full model is in [`docs/PLAN.md`](docs/PLAN.md#graph-data-model).

## Queries

Every Cypher query lives in [`queries/`](queries/) as `NN_name.cypher` and is loaded by name.

| # | Name | Purpose |
| --- | --- | --- |
| 00 | healthcheck | Creates and returns a test node in the `lore_healthcheck` graph |
| 02 | entry_decisions | Entry point, tried first: Decision vector search (cosine distance) fused with full-text on the question's specific terms by weighted reciprocal rank fusion; confidence >= 0.6, parity at half weight |
| 02 | entry_docs, entry_prs, entry_issues | Fallback starting nodes: nearest doc chunks and issues (vector), PRs (full-text) |
| 09 | similar_issues | F5 triage: nearest past issues (vector), the PRs that closed them and the modules those PRs touched |
| 01 | load_indexes, load_doc_chunks, load_doc_chunks_reset | Range, full-text and vector indexes (`EMBEDDING_DIM`, cosine); docs cut into ~800-char overlapping `DocChunk`s, `(DocChunk)-[:PART_OF]->(Doc)` |
| 21 | embed_*_texts, embed_set_* | Read the text to embed per Decision (statement + rationale + quote), Issue (title + 500 body chars) and DocChunk; write `vecf32` embeddings |
| 04 | expert_reset, expert_authored, expert_reviewed, expert_score | Derive `EXPERT_IN`: authored commits with a 180-day half-life, reviews at half weight, combined `score`; skips bots and bulk (> 500 file) commits |
| 05 | who_knows | F2: top experts on a module, with the PRs and commits behind each score |
| 06 | paper_owners, team_owners, module_owners | F3: CODEOWNERS owners with no touch in 12 months vs the real experts; team-owned modules; one module's owners ("no listed owner" when none) |
| 01 | load_topics, load_decisions, load_decisions_reset, load_affects, load_proposed, load_approved, load_about | Load extracted Decisions with DECIDED_IN, AFFECTS, PROPOSED, APPROVED and ABOUT edges |
| 20 | extract_pr_candidates, extract_issue_candidates, extract_doc_candidates, extract_repo_modules | Pick what the LLM reads: merged PRs with real descriptions, closed issues with 5+ human comments, docs/ADRs; bot text excluded |
| 07 | bus_factor | F4: people per module with a real, recent share of authored work (single points of failure first) |
| 08 | collaborates_reset, collaborates, collaborates_strong | Derive `COLLABORATES` author -> reviewer, `weight` = distinct PRs; skips bots and self-reviews; `COLLABORATES_STRONG` (weight >= 2) for label propagation, which doesn't settle on the full graph |
| 08 | pagerank, betweenness, label_propagation | `algo.pageRank` (most relied-on reviewers), `algo.betweenness` with fixed `samplingSeed` (F4 bridge people), `algo.labelPropagation` (F10 working groups, on COLLABORATES_STRONG) |
| 03 | trace_decision | F1 why-trace: a decision's sources, the issues they close or reference (top 6: closed and linking back first, then by `vec.cosineDistance` to the question), PROPOSED / APPROVED people, affected modules, SUPERSEDES history both ways, and open/draft PRs proposing to change it (a proposed decision sharing a module and a topic) |
| 02 | entry_modules, entry_topics | Names in a question -> Module (path segment, most active first) and Topic (all name parts present) ids |
| 05 | resolve_module, who_knows_topic | A module given by id, path or last segment -> Module id; F2 for a topic: authors and reviewers of PRs ABOUT it, time-decayed |
| 09 | issue_text, module_decisions | Triage helpers: an issue's text (to embed it like stored issues); decisions affecting the modules where similar issues were fixed |
| 11 | remember, recall_questions, what_changed | F6 memory: write User / Session / Question / Answer / CITED; read a user's past questions; query 11, cited nodes something newer SUPERSEDES or REFERENCES |
| 10 | co_changed_reset, co_changed, impact_radius | Derive `CO_CHANGED` from commits touching 2-6 modules (bulk skipped); F8: co-changed modules with share of commits, active decisions and top experts |
| 92 | check_evidence_prs | Eval only (golden q06): which cited PRs contain a person's non-bulk commits on a module |

## Setup

Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/). Commands are PowerShell, run from the repo root.

```powershell
copy .env.example .env                        # then fill in values
docker compose up -d falkordb                 # FalkorDB on 6379, browser on http://localhost:3000
cd backend; uv sync; cd ..                    # backend deps (Python 3.11)
uv run --directory backend python scripts/healthcheck.py
uv run --directory backend pytest
uv run --directory backend python scripts/derive.py --org FalkorDB --report --algo --impact module:FalkorDB:graph/src/parser   # derived edges + queries 5-8, 10
uv run --directory backend python scripts/embed.py --org FalkorDB            # chunk docs, embeddings, vector indexes
uv run --directory backend python scripts/find.py --check                     # queries 2 and 9 against the golden set
uv run --directory backend python -m lore.mcp_server                          # lore-mcp over stdio (ten tools)
uv run --directory backend python scripts/ask.py --org FalkorDB --user amrith "Who knows the Cypher parser?"   # Navigator
uv run --directory backend python scripts/eval.py                             # golden set -> docs/eval_results.md
```

### lore-mcp

`backend/lore/mcp_server/` exposes Lore's ten tools over MCP (Python MCP SDK 2.x): `find_entities`, `trace_decision`, `find_experts`, `module_owners`, `knowledge_risk`, `related_work`, `impact_radius`, `recall`, `remember`, `post_triage`. Each takes `org` (graph `lore_<org>`), runs only named queries from `queries/` (read-only except `remember`), and returns `results`, the `nodes` and `edges` it touched, `sources` (node id -> GitHub URL) and the `cypher` that ran. Decisions are always split into `decisions` (active), `pending_proposals` (open or draft PRs, never presented as current) and `history` (superseded); decisions below confidence 0.6 never appear. `post_triage` only targets `SANDBOX_REPO` (checked in `lore/safety.py`) and needs an approval token, an HMAC of the issue id and exact draft signed with `TRIAGE_APPROVAL_SECRET`, which only the UI's approve action mints. For now it is a dry run that prints the comment.

### Navigator

`backend/lore/agents/navigator.py` answers a question through a real MCP client session with `lore-mcp` (stdio). It lists the server's tools and gives their schemas to the LLM (Gemini `gemini-3.8-flash`, `LLM_AGENT_MODEL`; after a 429, an error or a too-large request it retries once, then falls back to Groq `gpt-oss-120b`, whose free tier of 8K tokens a minute is too tight to be primary). Tool results reach the LLM compacted (short field names, capped lists, no Cypher or embeddings; under ~4K tokens a call); the UI and eval get the full results. The loop: classify the intent (keyword rules, a hint only), always resolve names with `find_entities`, let the LLM pick up to three more tools (four calls per question in total), then a separate compose call with no tools and a strict JSON schema writes the answer as sentences, each citing node ids. Any cited id that no tool returned for this question is dropped, and a sentence left without a valid id is not shown. If nothing answers the question, the answer says "Not found" and shows the nearest evidence. `org` and `user_id` are filled in by code, never by the LLM, so a question can't read another org's graph or another user's memory. The answer, its citations, the subgraph, the path (edges touching a cited node) and every Cypher query that ran are returned, and the `remember` tool stores the question, answer and CITED edges (query 11 reads them back for "what changed since I last asked").

## Demo

_TBD._

## AI use

This project is built with Claude Code (Anthropic) as a coding assistant. The planning docs in `docs/` were prepared before the event; all code was written during it, with Claude Code generating drafts the team reviewed, ran and committed.

- M0 scaffold (repo layout, Docker Compose, config, FalkorDB client, query loader, healthcheck): written with Claude Code.
- M4 expertise (queries 04-07, `scripts/derive.py`, bus-factor tuning against the golden set): written with Claude Code.
- M7 algorithms (queries 08 and 10, COLLABORATES / CO_CHANGED derive jobs, co-change module cap checked against golden q10): written with Claude Code.
- M5 decisions (`backend/lore/llm/`, `ingest/extract.py`, extraction prompt, queries 01 decision loaders and 20): written with Claude Code. Decision extraction itself runs on Gemini (`LLM_FAST_MODEL`); every decision keeps a verified source quote and link.
- M8 lore-mcp (`backend/lore/mcp_server/`, `lore/safety.py`, queries 03, 02 entry_modules/topics, 05 resolve_module/who_knows_topic, 09 helpers and 11, tests per tool): written with Claude Code. Thresholds were checked against the loaded graphs (e.g. duplicate distance 0.15 from measured sandbox distances).
- M9 Navigator + eval (`agents/navigator.py`, `llm/agent.py`, `scripts/ask.py`, `scripts/eval.py`, eval fields for the sandbox and Bolt entries in `golden_set.yaml`): written with Claude Code. The Navigator itself runs on Gemini `gemini-3.8-flash` with Groq `gpt-oss-120b` as fallback; the eval scores its answers deterministically (no LLM judge).
- M6 embeddings (`ingest/embed.py`, `graph/search.py`, queries 02, 09 and 21, `scripts/embed.py`, `scripts/find.py`): written with Claude Code, including the fusion tuning against q01-q04 and s01 (measured ranks are in `queries/02_entry_decisions.cypher`). Embeddings run locally with fastembed (`BAAI/bge-small-en-v1.5`).
