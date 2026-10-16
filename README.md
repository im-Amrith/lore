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
| 08 | collaborates_reset, collaborates | Derive `COLLABORATES` author -> reviewer, `weight` = distinct PRs; skips bots and self-reviews |
| 08 | pagerank, betweenness, label_propagation | `algo.pageRank` (most relied-on reviewers), `algo.betweenness` with fixed `samplingSeed` (F4 bridge people), `algo.labelPropagation` (F10 working groups) on COLLABORATES |
| 10 | co_changed_reset, co_changed, impact_radius | Derive `CO_CHANGED` from commits touching 2-6 modules (bulk skipped); F8: co-changed modules with share of commits, active decisions and top experts |

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
```

## Demo

_TBD._

## AI use

This project is built with Claude Code (Anthropic) as a coding assistant. The planning docs in `docs/` were prepared before the event; all code was written during it, with Claude Code generating drafts the team reviewed, ran and committed.

- M0 scaffold (repo layout, Docker Compose, config, FalkorDB client, query loader, healthcheck): written with Claude Code.
- M4 expertise (queries 04-07, `scripts/derive.py`, bus-factor tuning against the golden set): written with Claude Code.
- M7 algorithms (queries 08 and 10, COLLABORATES / CO_CHANGED derive jobs, co-change module cap checked against golden q10): written with Claude Code.
- M5 decisions (`backend/lore/llm/`, `ingest/extract.py`, extraction prompt, queries 01 decision loaders and 20): written with Claude Code. Decision extraction itself runs on Gemini (`LLM_FAST_MODEL`); every decision keeps a verified source quote and link.
- M6 embeddings (`ingest/embed.py`, `graph/search.py`, queries 02, 09 and 21, `scripts/embed.py`, `scripts/find.py`): written with Claude Code, including the fusion tuning against q01-q04 and s01 (measured ranks are in `queries/02_entry_decisions.cypher`). Embeddings run locally with fastembed (`BAAI/bge-small-en-v1.5`).
