# Lore: milestone prompts for Claude Code

Paste one prompt at a time, starting a fresh session (or clearing context) for each milestone. Each prompt ends with a "Done when" check. Don't move on until it passes, or until you've decided to cut scope.

Before Oct 15, only commit the docs (`CLAUDE.md`, `docs/`). Project code starts with M0, on Oct 15 after 12:01 AM IST.

| Milestone | Day | Covers |
| --- | --- | --- |
| M0 Scaffold | Day 1 | Repo, Docker, config, query loader |
| M1 Sandbox repo | Day 1 | `lore-sandbox` issues and PRs (mostly by hand) |
| M2 Fetch | Day 1 | GitHub GraphQL fetch with raw cache |
| M3 Load structure | Day 1 | Normalise, load, indexes, modules, CODEOWNERS |
| M4 Expertise | Day 1 | EXPERT_IN, queries 5–7, Day 1 gate |
| M5 Decisions | Day 2 | LLM layer with cache, decision extraction, topics |
| M6 Embeddings | Day 2 | Vector and full-text indexes, queries 2 and 9 |
| M7 Algorithms | Day 2 | COLLABORATES, CO_CHANGED, PageRank, betweenness, label propagation |
| M8 lore-mcp | Day 2 | The ten tools |
| M9 Navigator + eval | Day 2 | CLI agent, memory, golden-set eval, Day 2 gate |
| M10 API | Day 3 | FastAPI endpoints |
| M11 Ask screen | Day 3 | Chat, evidence path, show query |
| M12 Module page + risk map | Day 3 | F2, F3, F4 views |
| M13 Steward | Day 3 | Task board, webhook, triage inbox, post to sandbox |
| M14 Deploy | Day 3 | FalkorDB Cloud, backend, frontend, Day 3 gate |
| M15 Sync + supersession | Day 4 | Incremental sync, decision reversal |
| M16 Polish | Day 4 | Memory screen, empty states, rate limits, snapshot |
| M17 Submission pack | Day 4 | README, queries list, AI use, final checks |

---

## M0 Scaffold

```
Read CLAUDE.md and docs/PLAN.md (Tech stack, Graph data model).

Set up the project skeleton exactly as the layout in CLAUDE.md describes:
- git repo, .gitignore (data/raw, data/cache, .env, node_modules, .venv)
- docker-compose.yml running falkordb/falkordb:latest with a persistent volume, ports 6379 and 3000
- backend/ with uv and pyproject.toml (pin exact versions): falkordb client, fastapi, uvicorn, httpx, pydantic-settings, pytest
- backend/lore/config.py reading env vars; .env.example listing every variable with a comment:
  GITHUB_TOKEN, DEMO_ORG, SANDBOX_REPO, FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASSWORD,
  LLM_PROVIDER, LLM_API_KEY, LLM_MODEL_FAST, LLM_MODEL_SMART, EMBEDDING_MODEL, EMBEDDING_DIM, LLM_DAILY_CALL_CAP, GITHUB_WEBHOOK_SECRET
- backend/lore/graph/: a client helper (select graph by org, query and ro_query wrappers) and a query loader that reads queries/NN_name.cypher by name
- queries/00_healthcheck.cypher that creates and returns a test node
- scripts/healthcheck.py that runs it
- README.md skeleton with headings: What it is, Tracks, Architecture, Graph data model, Queries, Setup, Demo, AI use

Propose the plan first, then build. Commit when done.

Done when: `docker compose up -d falkordb` and the healthcheck script print the test node, and `pytest` runs (even with zero tests).
```


## M1 Sandbox repo (mostly you)

Follow `docs/SANDBOX_STORY.md`: the Tern URL shortener, its cast, CODEOWNERS, 10 issues, 6 PRs (PR 6 stays a draft until the demo), and the order of work. Do the GitHub parts by hand while Claude works on M2. To get the stub code files:

```
Read docs/SANDBOX_STORY.md. In a separate folder (not inside lore/), generate the Tern stub files from the layout section:
a few lines of plausible Python per file, plus README.md, CODEOWNERS and the two ADRs. Don't commit anything;
I'll make the commits myself with the authors the story lists.
```

Optional prompt if you want a seed script for issues only:

```
Write backend/scripts/seed_sandbox.py that creates issues in SANDBOX_REPO from docs/sandbox_seed.yaml using GITHUB_TOKEN.
It must refuse to run against any repo other than SANDBOX_REPO. Show me the YAML format, then wait for me to fill it before running.
```

## M2 Fetch

```
Read docs/PLAN.md "Data source and ingestion" steps 1–2.

Build backend/lore/ingest/github_fetch.py and scripts/fetch.py using the GitHub GraphQL API (GITHUB_TOKEN):
- inputs: org or a single repo, and a "since" date (default 18 months ago)
- per repo: commits with changed file paths and additions/deletions, PRs with author, body, reviews (author, state, date), linked closing issues, merged date; issues with labels, body, comments; CODEOWNERS file; markdown files under docs/, design/, rfcs/, adr/ and READMEs with last-changed date; releases
- paginate, handle rate limits (respect reset time), write raw JSON to data/raw/<org>/<repo>/...
- skip anything already cached unless --refresh
- never store email addresses (drop them at fetch time)
- store the GitHub login (author.user.login) with every commit; when it's null (commit-only authors), keep the author name
- support extra branches per repo from config. For FalkorDB/FalkorDB also fetch the `main-rs` branch:
  the Rust engine's 2,917-commit history lives only there, because `main` got the whole tree in one commit (PR #2279)
- print a volume summary per repo: commits, PRs, issues, comments, docs

Run it on SANDBOX_REPO first, then on FalkorDB/FalkorDB (main + main-rs), and show me the summary before fetching other repos.
Start the org scope small: FalkorDB/FalkorDB first; add other repos only if there's time.

Done when: the whole DEMO_ORG and the sandbox are cached, and the volume summary looks like enough history (if it's thin, tell me and suggest widening the window).
```

## M3 Load structure

```
Read docs/PLAN.md "Graph data model" and queries 1 (bulk load).

Build normalize.py, modules.py and load.py in backend/lore/ingest/, plus scripts/load.py:
- normalise raw JSON into entity records with the stable ids from CLAUDE.md
- Person ids from GitHub logins; a commit author with no login becomes person:name:<slug>
- mark bot accounts (dependabot, copilot, github-actions, *[bot]) with is_bot = true
- mark tree-replacing commits (more than 500 changed files, e.g. FalkorDB PR #2279) with bulk = true
- module mapping: file path -> first two directory levels, overridden by CODEOWNERS patterns; unit-test it.
  For FalkorDB, `graph/src/<x>` should map to the module `graph/src/<x>` (three levels), since that's where the engine's parts live
- CODEOWNERS -> Team nodes, OWNS edges (Person or Team -> Module), MEMBER_OF where team members are known
- REFERENCES edges from #123, commit SHAs and GitHub URLs found in text (unit-test the regex)
- create all range and full-text indexes from the plan (vector indexes come in M6)
- write every load query as a file in queries/ (01_load_*.cypher), batched UNWIND ... MERGE

Load the sandbox first and print node and edge counts per label and type. Then load the org.

Done when: counts per label and relationship type are printed for both graphs, and a sample path
(Person)-[:AUTHORED]->(:PullRequest)-[:CLOSES]->(:Issue) returns rows.
```

## M4 Expertise (Day 1 gate)

```
Read docs/PLAN.md queries 4–7.

- Put queries 4 (EXPERT_IN from commits, plus the reviews variant and the score combine), 5 (who-knows), 6 (paper owners, plus the team-owner variant) and 7 (bus factor) into queries/.
- Build scripts/derive.py to run the derive jobs, passing $now.
- Run each query against the org graph and the sandbox graph and show me the output.
- Fix any syntax FalkorDB rejects and note the fix in a comment in the .cypher file.
- EXPERT_IN must skip bot authors and commits marked bulk = true.

Done when: query 5 matches golden set q05 and q06 (graph/src/index -> Dvir Dukhan then Avi Avni; graph/src/parser -> Avi Avni),
query 7 lists graph/src/parser and graph/src/udf with bus_factor 1, query 6 finds the planted sandbox paper owner,
and the sandbox shows storage/ with bus_factor 1.
```

## M5 Decisions

```
Read docs/PLAN.md "Data source and ingestion" steps 6–7 and the Decision node.

1. Build backend/lore/llm/: one wrapper for chat calls and one for embeddings, both with a disk cache in data/cache/llm keyed by a hash of model + prompt + input, a call counter, and a hard stop at LLM_DAILY_CALL_CAP. Structured output via JSON schema.
2. Build ingest/extract.py:
   - candidates only: merged PRs with a body over ~300 characters, closed issues with 5+ comments, docs/ADR files
   - output per decision: statement, rationale, alternatives, affected module ids (from the candidate's touched modules), proposed_by and approved_by logins (from the candidate's author and approving reviewers only), a source quote under 30 words, confidence 0–1
   - zero decisions is a valid answer; don't force one
   - topic tagging: 1–3 topics from the fixed list in docs/TOPICS.md (load it into config; use its path, label and scope hints in the prompt; the sandbox has its own short list)
3. Load Decision nodes with DECIDED_IN, AFFECTS, PROPOSED, APPROVED and ABOUT edges (queries in queries/).

Run a sample of 30 candidates first, print every decision next to its source URL, and stop.

Done when: I've spot-checked 20 decisions and approved a full run, the full run is loaded, and decisions under 0.6 confidence are excluded from answers.
```

## M6 Embeddings

```
Read docs/PLAN.md query 2 and query 9.

- Embed Decision.statement, Issue title + first 500 chars of body, and DocChunk text (chunk docs at ~800 chars with overlap) through the cached embedding wrapper.
- Create vector indexes on Decision, Issue and DocChunk embedding with EMBEDDING_DIM and cosine similarity.
- Put queries 2 (vector + full-text entry point) and 9 (similar issues and where they were fixed) in queries/.
- Check whether the vector score is a distance or a similarity and document it in the .cypher file; rank accordingly.

Done when: for 3 golden-set questions, query 2 returns the right starting node in its top 5, and query 9 on a sandbox issue returns the planted related issue.
```

## M7 Algorithms

```
Read docs/PLAN.md queries 8 and 10.

- Add the COLLABORATES and CO_CHANGED derive jobs to scripts/derive.py.
- Put PageRank, betweenness (fixed samplingSeed) and label propagation queries in queries/, plus query 10 (impact radius).
- Run each on the org graph and print the top 10 results.

Done when: all four algorithm queries return results that look plausible to me, and runtime for each is under a few seconds.
```

## M8 lore-mcp

```
Read docs/PLAN.md "Agent architecture" (MCP tools table and guardrails).

Build backend/lore/mcp_server/ with the Python MCP SDK, exposing the ten tools in the plan.
Each tool:
- calls only queries from queries/ (read-only except remember and post_triage)
- returns structured JSON: results, the node and edge ids touched, and the Cypher that ran
- takes an org argument that selects the graph
post_triage: enforce the SANDBOX_REPO allowlist in code and require an approval token; for now, make it a dry run that prints the comment.
Write a small test per tool against the sandbox graph.

Done when: tests pass, and you can list the tools and call trace_decision and find_experts from a test client.
```

## M9 Navigator + eval (Day 2 gate)

```
Read docs/PLAN.md "Navigator's loop", "Memory, coordination and freshness", query 11, and docs/golden_set.yaml.

- Build agents/navigator.py following the 7-step loop, using lore-mcp tools only, max 4 tool calls, answers built only from tool results with node ids on every claim, a "not found" path.
- Write memory nodes (User, Session, Question, Answer, CITED) through the remember tool. Add query 11 for "what changed".
- scripts/ask.py: ask a question as a given user from the terminal; print the answer, the path and the Cypher.
- scripts/eval.py: run every golden-set question, compare cited nodes and key facts to the expected answer, and write a results table to docs/eval_results.md.

Done when: eval shows at least 7 of 10 correct. If not, show me which failed and why (missing data, extraction, entry point or reasoning) before changing anything.
```

## M10 API

```
Read docs/PLAN.md "UI screens".

Build FastAPI routes in backend/lore/api/:
- POST /ask {org, user, question} -> answer, citations, subgraph, cypher
- GET /module/{id} -> owners vs experts, decisions with status, co-changed modules
- GET /risk -> modules with bus factor, bridge people, working groups
- GET /triage, POST /triage/{task}/approve -> inbox items and approval
- GET /memory/{user} -> past questions and what changed
- GET /users, POST /users -> simple username picker (no passwords)
Add per-user rate limiting on /ask, CORS for the frontend, and OpenAPI docs.

Done when: each route returns real data from the sandbox and org graphs, shown with curl.
```

## M11 Ask screen

```
Use the frontend-design guidance if available. Read docs/PLAN.md "UI screens" and "What every answer includes".

Create the Next.js + Tailwind app in frontend/:
- username picker
- Ask screen: chat on the left; Cytoscape graph on the right showing the returned subgraph with the walked path highlighted; each claim links to its GitHub source; a "show query" toggle with the Cypher
- clear "not found" state

Done when: I can ask two golden-set questions in the browser and see the path light up and the sources link out.
```

## M12 Module page + risk map

```
Build the Module page (owners vs real experts with evidence, decisions with status, co-changed modules) and the Knowledge-risk map (module tiles coloured by bus factor, bridge people from betweenness, working groups from label propagation). Clicking a tile opens the Module page.

Done when: the planted sandbox paper owner and single-expert module are visible, and the org's map renders.
```

## M13 Steward

```
Read docs/PLAN.md F5 and "Agents coordinate through the graph".

- Webhook endpoint for SANDBOX_REPO issue events (verify the webhook secret). A new issue is loaded and a Task {type:'triage', status:'open'} is created.
- agents/steward.py: claims open Tasks with the atomic claim query, calls related_work, find_experts and module_owners, applies Playbook rules, and writes a draft triage (related issues, likely duplicate, suggested owner and reviewer, links) onto the Task.
- Feedback: when I edit a draft before approving, store the edit as Feedback and update the Playbook.
- Triage inbox screen: drafts with Edit and Approve buttons. Approve calls post_triage for real (sandbox only).
- Run two Steward workers and show no Task is claimed twice.

Done when: opening an issue in lore-sandbox produces a draft in the inbox within a minute, and approving posts the comment on GitHub.
```

## M14 Deploy (Day 3 gate)

```
Deploy:
- create the graphs on FalkorDB Cloud by running the loaders from cached data (no new LLM calls; the cache should cover it)
- backend to Render/Railway/Fly with env vars set there (never in the repo)
- frontend to Vercel pointing at the backend
- point the sandbox webhook at the deployed backend
Write the deploy steps into README.md.

Done when: the full demo flow from docs/PLAN.md works on the deployed URLs.
```

## M15 Sync + supersession

```
Read docs/PLAN.md "Keeping knowledge current".

- Incremental sync every 15 minutes (APScheduler) for DEMO_ORG using the last sync time, and on webhook events for the sandbox.
- After sync: re-derive EXPERT_IN, CO_CHANGED and COLLABORATES only for touched modules and people.
- Supersession: when a new decision affects the same module and topic as an active one, ask the LLM whether it replaces it; if yes, add SUPERSEDES, set status and valid_to.
- Run the stale-docs query (12) after each sync.

Done when: I merge the decision-reversing PR in lore-sandbox, and within one sync the why-question shows the new decision with the old one marked superseded, and "what changed since I last asked" lists it.
```

## M16 Polish

```
- My memory screen: past questions, "changed since" badges, stale-doc warnings.
- Empty, loading and error states on every screen.
- Daily LLM cap and rate limit verified on the deployed site.
- scripts/snapshot.py: save the raw cache and LLM cache to data/snapshots/ and restore from it, so the demo graph can be rebuilt without GitHub or new LLM calls.
- Fix anything ugly in the demo path; nothing new.

Done when: I can run the full demo script twice in a row without a hitch.
```

## M17 Submission pack

```
Read docs/PLAN.md "Submission checklist".

Finish README.md:
- what Lore is, the three tracks entered, the demo video link, the live link
- architecture (Mermaid) and graph data model (schema diagram + label and relationship tables)
- the query list: every file in queries/ with one line on what it does and which feature uses it; call out the graph algorithms
- "Why a graph": decision lineage, bus factor, impact radius cannot be done with vector search alone
- setup: local (docker compose + snapshot restore) and deployed
- golden-set results from docs/eval_results.md
- data note: public GitHub data only, no emails
- AI use: which coding assistants were used and for what; what the team designed, verified and wrote

Then check the repo is public, has no secrets in git history, and local setup works from a fresh clone.

Done when: a fresh clone follows the README to a working local demo.
```

---

## Prompts to reuse any time

**Start of a session**
```
Read CLAUDE.md and the docs/PLAN.md sections for milestone <M#>. Summarise what's already built (check git log and the repo), then propose the plan for <M#>.
```

**Understand what was built (do this for every query; judges may ask)**
```
Explain queries/<file>.cypher line by line: what each MATCH walks, why the filters are there, what it returns, and how it would behave on an empty or huge graph.
```

**Debugging**
```
<paste error>. Find the cause before changing code. If it's Cypher, reproduce it with a minimal query against the local FalkorDB first.
```

**End of day**
```
Run all tests, the healthcheck and scripts/eval.py. Update README.md, list what's done against today's checklist in docs/PLAN.md, list what's left, and commit.
```

**When a gate fails**
```
The <Day N> gate failed: <what happened>. List the likely causes ranked by likelihood with a quick check for each. Don't change code until we pick one. If it can't be fixed in 2 hours, propose what to cut using the cut order in docs/PLAN.md.
```
