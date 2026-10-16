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
| 04 | expert_reset, expert_authored, expert_reviewed, expert_score | Derive `EXPERT_IN`: authored commits with a 180-day half-life, reviews at half weight, combined `score`; skips bots and bulk (> 500 file) commits |
| 05 | who_knows | F2: top experts on a module, with the PRs and commits behind each score |
| 06 | paper_owners, team_owners, module_owners | F3: CODEOWNERS owners with no touch in 12 months vs the real experts; team-owned modules; one module's owners ("no listed owner" when none) |
| 01 | load_topics, load_decisions, load_decisions_reset, load_affects, load_proposed, load_approved, load_about | Load extracted Decisions with DECIDED_IN, AFFECTS, PROPOSED, APPROVED and ABOUT edges |
| 20 | extract_pr_candidates, extract_issue_candidates, extract_doc_candidates | Pick what the LLM reads: merged PRs with real descriptions, closed issues with 5+ human comments, docs/ADRs; bot text excluded |
| 07 | bus_factor | F4: people per module with a real, recent share of authored work (single points of failure first) |

## Setup

Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/). Commands are PowerShell, run from the repo root.

```powershell
copy .env.example .env                        # then fill in values
docker compose up -d falkordb                 # FalkorDB on 6379, browser on http://localhost:3000
cd backend; uv sync; cd ..                    # backend deps (Python 3.11)
uv run --directory backend python scripts/healthcheck.py
uv run --directory backend pytest
uv run --directory backend python scripts/derive.py --org FalkorDB --report   # EXPERT_IN + queries 5-7
```

## Demo

_TBD._

## AI use

This project is built with Claude Code (Anthropic) as a coding assistant. The planning docs in `docs/` were prepared before the event; all code was written during it, with Claude Code generating drafts the team reviewed, ran and committed.

- M0 scaffold (repo layout, Docker Compose, config, FalkorDB client, query loader, healthcheck): written with Claude Code.
- M4 expertise (queries 04-07, `scripts/derive.py`, bus-factor tuning against the golden set): written with Claude Code.
- M5 decisions (`backend/lore/llm/`, `ingest/extract.py`, extraction prompt, queries 01 decision loaders and 20): written with Claude Code. Decision extraction itself runs on Gemini (`LLM_FAST_MODEL`); every decision keeps a verified source quote and link.
