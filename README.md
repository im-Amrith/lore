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
| 13 | task_open, open_issues, triage_inbox, task_approve | F5 work board: open a triage `Task -[:FOR]-> Issue` per open sandbox issue (MERGE on a deterministic id, never two), the inbox, and a one-time approval that records whether the comment was posted or a dry run |
| 13 | open_tasks, task_claim, task_draft, task_release, task_reopen | Steward's side of the board: the atomic claim from the plan (`WHERE t.status = 'open' SET t.status = 'claimed'`; a second worker gets 0 rows), draft and release only by the claimer, reopen a drafted Task for a redraft |
| 13 | issues_known, issue_upsert | Librarian intake of new sandbox issues (poll or webhook): Issue + author `Person` (ON CREATE only, no emails), then embedded like loaded issues |
| 13 | playbook, feedback_add | Procedural memory: the triage `Playbook` and `(Feedback)-[:ADJUSTS]->(Playbook)`; an approved edit adds its rule to the Playbook's steps and bumps its version |
| 14 | users_list, user_upsert | Username picker: users with question counts; create a user and link `(User)-[:IS]->(Person)` |
| 93 | data_version | Fingerprint of an org graph's knowledge (counts, latest timestamps, EXPERT_IN / CO_CHANGED totals; memory excluded), keying the Navigator's answer cache |
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
uv run --directory backend python -m lore.mcp_server                          # lore-mcp over stdio (ten tools + data_version)
uv run --directory backend python scripts/ask.py --org FalkorDB --user amrith "Who knows the Cypher parser?"   # Navigator
uv run --directory backend python scripts/eval.py                             # golden set (not-yet-passed questions) -> docs/eval_results.md
uv run --directory backend python scripts/warm.py                             # pre-answer the demo questions (answer cache)
uv run --directory backend python scripts/tasks.py                            # open triage Tasks for open sandbox issues
uv run --directory backend python scripts/steward.py                          # Steward worker: new issues -> Tasks -> drafts (--poll 60, --no-intake)
uv run --directory backend uvicorn lore.api.app:app --port 8000               # API (+ Steward polling the sandbox every 60 s), docs at http://localhost:8000/docs
cd frontend; copy .env.example .env.local; npm install; npm run dev           # UI on http://localhost:3001
```

### Frontend

`frontend/` is Next.js 16 + Tailwind 4, with Cytoscape.js for the evidence graph. The Ask screen has the conversation on the left and, on the right, the answer's subgraph with the walked path (the edges touching a cited node) drawn in teal and the rest of what was retrieved dimmed. Every sentence carries numbered citations that open the GitHub page; hovering one lights its node. Each answer shows which model wrote it, a "cached" badge when it came from the answer cache, and a "Show query" toggle with every Cypher query, its parameters and row count. While the Navigator works, `POST /ask/stream` streams each tool call and LLM step, so the screen shows what is being looked up. "Not found" answers get their own state with the nearest evidence; claims that rest on an unmerged proposal get a "draft PR proposes changing this" callout.

### API

`backend/lore/api/app.py` (FastAPI, OpenAPI docs at `/docs`), one route per screen:

| Route | Returns |
| --- | --- |
| `POST /ask` `{org, user, question}` | The Navigator's answer: cited sentences, citations with links, the subgraph and the walked path, every Cypher query that ran, the tools and LLM endpoints used. At most `ASK_PER_MINUTE` (5) and `ASK_PER_DAY` (100) per user; 429 with `Retry-After` past that, 503 when every free-tier LLM endpoint is out |
| `GET /module/{id}` | CODEOWNERS owners vs active experts (paper owners, mismatch), experts with evidence PRs, decisions on the module split into current / pending proposals / history, co-changed modules |
| `GET /risk` | Bus factor per module (single-expert first), bridge people (betweenness), working groups (label propagation) |
| `GET /triage`, `POST /triage/{task}/approve` | Triage Tasks with their issue, Steward's draft and the facts it was written from; approve mints the approval token for that issue and exact text, calls `post_triage` (sandbox only; posts for real only with `DRY_RUN=false`) and marks the Task approved. An edited draft is stored as Feedback and adds a rule to the Playbook |
| `POST /triage/{task}/redraft`, `POST /triage/sync`, `GET /playbook` | Draft a Task again (after the Playbook changed); check the sandbox for new issues now; the Playbook's steps and Feedback |
| `POST /webhook/github` | Sandbox `issues` events (opened, reopened, edited), verified with `X-Hub-Signature-256` and `GITHUB_WEBHOOK_SECRET`; the issue is loaded, gets a Task and Steward drafts it in the background |
| `GET /memory/{user}` | Past questions per org and what changed since in the nodes their answers cited |
| `GET /users`, `POST /users` | Username picker (no passwords); a GitHub login links `(User)-[:IS]->(Person)` |

`/ask`, Steward and approve go through lore-mcp (an in-process MCP session); the read-only screens call the same named-query tool functions. CORS allows `CORS_ORIGINS` (the frontend on port 3001).

### lore-mcp

`backend/lore/mcp_server/` exposes Lore's ten tools (plus `data_version`, a cache key the agents read but the LLM is never offered, and Steward's work board: `open_tasks`, `claim_task`, `save_draft`, `release_task`, `get_playbook`) over MCP (Python MCP SDK 2.x): `find_entities`, `trace_decision`, `find_experts`, `module_owners`, `knowledge_risk`, `related_work`, `impact_radius`, `recall`, `remember`, `post_triage`. Each takes `org` (graph `lore_<org>`), runs only named queries from `queries/` (read-only except `remember`), and returns `results`, the `nodes` and `edges` it touched, `sources` (node id -> GitHub URL) and the `cypher` that ran. Decisions are always split into `decisions` (active), `pending_proposals` (open or draft PRs, never presented as current) and `history` (superseded); decisions below confidence 0.6 never appear. `post_triage` only targets `SANDBOX_REPO` (checked in `lore/safety.py`) and needs an approval token, an HMAC of the issue id and exact draft signed with `TRIAGE_APPROVAL_SECRET`, which only the UI's approve action mints. With `DRY_RUN=true` (the default) it only prints the comment; with `DRY_RUN=false` it posts it with `GITHUB_TOKEN`.

### Navigator

`backend/lore/agents/navigator.py` answers a question through a real MCP client session with `lore-mcp` (stdio). It lists the server's tools and gives their schemas to the LLM, which comes from a pool of free-tier endpoints tried quality first (`AGENT_LLM_POOL`: gemini-3.8-flash, Groq gpt-oss-120b, gemini-3.6-flash, Groq llama-3.3-70b, gemini-3.5-flash-lite). A per-minute 429 cools an endpoint down for its retry-after and a daily quota marks it exhausted until its reset, so no endpoint is hammered; the state is shared across runs in `data/cache/llm/endpoint_state.json`. A question usually costs two LLM calls: call 1 picks every tool it needs at once (they run in parallel from the model's point of view), call 2 writes the answer; a third call happens only when every tool result came back empty. Answers are cached under the normalized question, the org, the graph's data version (the `data_version` tool, query 93, which changes after a load, sync or derive) and a hash of the prompts; `scripts/warm.py` pre-answers the demo questions. Tool results reach the LLM compacted (short field names, capped lists, no Cypher or embeddings; under ~4K tokens a call); the UI and eval get the full results. The loop: classify the intent (keyword rules, a hint only), always resolve names with `find_entities`, let the LLM pick up to three more tools (four calls per question in total), then a separate compose call with no tools and a strict JSON schema writes the answer as sentences, each citing node ids. Any cited id that no tool returned for this question is dropped, and a sentence left without a valid id is not shown. If nothing answers the question, the answer says "Not found" and shows the nearest evidence. `org` and `user_id` are filled in by code, never by the LLM, so a question can't read another org's graph or another user's memory. The answer, its citations, the subgraph, the path (edges touching a cited node) and every Cypher query that ran are returned, and the `remember` tool stores the question, answer and CITED edges (query 11 reads them back for "what changed since I last asked").

### Steward

`backend/lore/agents/steward.py` triages new issues in `SANDBOX_REPO` (F5). The agents hand off through the graph: the Librarian (`ingest/live.py`) loads a new issue, from the API's 60-second poll locally or the GitHub webhook when deployed, and opens a `Task {type: 'triage', status: 'open'}` for it. Steward claims it with the plan's atomic claim query, so two workers never draft the same issue. It then calls four lore-mcp tools: `related_work` (similar issues, the PRs that fixed them, their modules and decisions), `module_owners` on the main module (the fix's module, not `tests/`), `find_experts` with a low threshold for a reviewer, and `trace_decision` on the decision made in the earlier fix. Code, not the LLM, picks the facts:

- the related issues (the nearest, plus any within distance 0.30)
- the owner (the person who actually works there)
- a paper-owner warning when CODEOWNERS lists someone with no activity on the module
- the reviewer (the next person by expertise, else the CODEOWNERS owner)

The LLM pool then writes the comment from those facts, following the Playbook's steps. Links that no tool returned are stripped, and the draft and its facts are stored on the Task. Nothing is posted until a human approves in the triage inbox. If the human edits the draft first, the edit becomes a `Feedback` node that `ADJUSTS` the `Playbook`, and the rule it teaches is added to the Playbook's steps: the human's own words, or one LLM call that generalises the edit. The next draft follows it.

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
- M11 Ask screen (`frontend/`, `POST /ask/stream`, node labels and pending flags in Navigator answers): written with Claude Code.
- M10 API (`backend/lore/api/`, queries 13 and 14, `ingest/tasks.py`, `scripts/tasks.py`, API tests): written with Claude Code.
- M13 Steward (`agents/steward.py`, `ingest/live.py`, the work-board, intake and Playbook queries in 13, the work-board MCP tools, webhook, poll loop, approve with Feedback, real posting behind `DRY_RUN`, `scripts/steward.py`, the triage inbox screen, `tests/test_steward.py`): written with Claude Code. The related-issue distance (0.30) and reviewer threshold (0.1) were checked against the two demo issues on a copy of the sandbox graph. The drafts and the rules learned from edits are written by the free-tier agent pool; the owner, reviewer and related issues are picked by code from tool results.
- M6 embeddings (`ingest/embed.py`, `graph/search.py`, queries 02, 09 and 21, `scripts/embed.py`, `scripts/find.py`): written with Claude Code, including the fusion tuning against q01-q04 and s01 (measured ranks are in `queries/02_entry_decisions.cypher`). Embeddings run locally with fastembed (`BAAI/bge-small-en-v1.5`).
