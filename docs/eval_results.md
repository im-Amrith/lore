# Eval results

Run 2026-10-18 06:53 UTC by `scripts/eval.py` (Navigator via lore-mcp over stdio). Rows keep the run they come from (column `run`): questions that already passed aren't rerun unless asked. Scoring is deterministic: every must_cite URL cited, every key fact mentioned, every shown sentence cited (and, for not-found tests, the answer says so). See the script's docstring.

**Golden q01-q10: 10 of 10 pass. All checks: 14 of 14.**

This run: Average answer time: 2.6 s, 2.1 LLM calls per question, over 14 fresh answers. Largest prompt: 3351 tokens. Endpoints: gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b.

| id | type | pass | must_cite | key facts | tools | llm calls | endpoints | secs | max prompt tok | dropped | run | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | 2 | groq:openai/gpt-oss-20b | 2.3 | 2423 | 1 | 2026-10-18 06:53 UTC |  |
| q02 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.2 | 2340 | 0 | 2026-10-18 06:53 UTC |  |
| q03 | why | PASS | 2/2 | 4/4 | find_entities, trace_decision, trace_decision, trace_decision | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.4 | 3219 | 0 | 2026-10-18 06:53 UTC |  |
| q04 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.5 | 2403 | 0 | 2026-10-18 06:53 UTC |  |
| q05 | who | PASS | 1/1 | 3/3 | find_entities, find_experts | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.5 | 2510 | 0 | 2026-10-18 06:53 UTC |  |
| q06 | who | PASS | 1/1 | 2/2 | find_entities, find_experts, module_owners | 2 | gemini:gemini-3.5-flash-lite | 3.0 | 2564 | 0 | 2026-10-18 06:53 UTC |  |
| q07 | owns | PASS | 2/2 | 3/3 | find_entities, module_owners | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.6 | 2327 | 0 | 2026-10-18 06:53 UTC |  |
| q08 | owns | PASS | 1/1 | 3/3 | find_entities, module_owners | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.3 | 2233 | 0 | 2026-10-18 06:53 UTC |  |
| q09 | risk | PASS | 2/2 | 4/4 | find_entities, knowledge_risk | 2 | gemini:gemini-3.5-flash-lite | 3.3 | 3211 | 0 | 2026-10-18 06:53 UTC |  |
| q10 | impact | PASS | 0/0 | 2/2 | find_entities, impact_radius | 2 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 2.6 | 3351 | 0 | 2026-10-18 06:53 UTC |  |
| s01 | why | PASS | 3/3 | 4/4 | find_entities, trace_decision, trace_decision | 2 | gemini:gemini-3.5-flash-lite | 2.8 | 2943 | 0 | 2026-10-18 06:53 UTC |  |
| s02 | owns | PASS | 0/0 | 2/2 | find_entities, module_owners | 2 | groq:openai/gpt-oss-20b | 1.3 | 2207 | 0 | 2026-10-18 06:53 UTC |  |
| s03 | risk | PASS | 0/0 | 4/4 | find_entities, knowledge_risk | 2 | gemini:gemini-3.5-flash-lite | 2.9 | 2599 | 0 | 2026-10-18 06:53 UTC |  |
| n01 | not-found | PASS | 2/2 | 0/0 | find_entities, trace_decision, find_entities, trace_decision | 3 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 3.8 | 3246 | 0 | 2026-10-18 06:53 UTC |  |

## Answers

### q01: Why did the Rust engine drop all_nodes_matrix?

**PASS** · 2026-10-18 06:53 UTC · intent why · 2 LLM calls via groq:openai/gpt-oss-20b · tools: find_entities, trace_decision

Remove the all_nodes_matrix from the Rust engine graph storage. [1][2][3] The Rust engine dropped all_nodes_matrix because it was only maintained for a reader that no longer existed, caused write performance to scale linearly with the deleted-id set due to GraphBLAS structural upkeep, and bare nodes now cost practically nothing. [1] The decision was proposed by AviAvni and approved by DvirDukhan, and it was implemented in PR #2678. [4][5][2]

- [1] `decision:2bf6caaed5caeaca` https://github.com/FalkorDB/FalkorDB/pull/2678
- [2] `pr:FalkorDB/FalkorDB#2678` https://github.com/FalkorDB/FalkorDB/pull/2678
- [3] `issue:FalkorDB/FalkorDB#2677` https://github.com/FalkorDB/FalkorDB/issues/2677
- [4] `person:DvirDukhan` https://github.com/DvirDukhan
- [5] `person:AviAvni` https://github.com/AviAvni

Dropped (cited nothing a tool returned):
- This change was prompted by issue #2677, which showed that writes after a mass delete were far more expensive than the work they performed because all_nodes_matrix was still being updated. `['issue:2677']`

Expected: Writes after a large deletion were slow because every create and delete had to maintain all_nodes_matrix, a GraphBLAS matrix of every live node, and nothing read it any more (the scan already walked ids minus the deleted set, like the C engine). Removing it made node creation flat after mass deletes, level with C, and cut memory for 1M bare nodes from 10.1 MB to 0.1 MB.


### q02: Why does the engine now fold MVCC deltas on every write?

**PASS** · 2026-10-18 06:53 UTC · intent why · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision

Implement an adaptive fold policy governed by a measured cost model to bound MVCC delta growth on every write path. [1][2][3] This was decided because deltas were never folded outside GRAPH.BULK, leading to unbounded delta growth and O(|delta|) materialization overhead on reads, addressing issue #2388. [1][3] The rejected alternative was keeping an LSM-style ratio rule (D >= base/K), which fails because every write transaction re-touches the whole delta. [1] AviAvni proposed this and DvirDukhan approved it in PR #2349. [4][5][2]

- [1] `decision:1017616f47939a04` https://github.com/FalkorDB/FalkorDB/pull/2349
- [2] `pr:FalkorDB/FalkorDB#2349` https://github.com/FalkorDB/FalkorDB/pull/2349
- [3] `issue:FalkorDB/FalkorDB#2388` https://github.com/FalkorDB/FalkorDB/issues/2388
- [4] `person:AviAvni` https://github.com/AviAvni
- [5] `person:DvirDukhan` https://github.com/DvirDukhan

Expected: Outside GRAPH.BULK, deltas were never folded into the base matrix, so a long-lived graph grew its delta layers without limit and every read paid a cost proportional to the delta size. PR #2349 added an adaptive fold policy driven by a measured cost model on every mutation path. An LSM-style ratio rule was rejected because it ignores transaction size.


### q03: Why are there two branches, main and master?

**PASS** · 2026-10-18 06:53 UTC · intent why · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision, trace_decision, trace_decision

Migrate the default development branch to the Rust implementation of FalkorDB while keeping the C engine maintained and released from master. [1][2][3][4][5][6][7][8] Migrate the default development branch to the Rust implementation of FalkorDB while keeping the C engine maintained and released from master as decided in PR #2279. [1][2] This allows version 6.0 and later to be developed using the new Rust engine while preserving the existing C engine lineage and releases, addressing issue #2280. [1][3] DvirDukhan proposed this migration and AviAvni approved it. [1][9][10]

- [1] `decision:10969052dbeec517` https://github.com/FalkorDB/FalkorDB/pull/2279
- [2] `pr:FalkorDB/FalkorDB#2279` https://github.com/FalkorDB/FalkorDB/pull/2279
- [3] `issue:FalkorDB/FalkorDB#2280` https://github.com/FalkorDB/FalkorDB/issues/2280
- [4] `issue:FalkorDB/FalkorDB#996` https://github.com/FalkorDB/FalkorDB/issues/996
- [5] `issue:FalkorDB/FalkorDB#2009` https://github.com/FalkorDB/FalkorDB/issues/2009
- [6] `issue:FalkorDB/FalkorDB#651` https://github.com/FalkorDB/FalkorDB/issues/651
- [7] `issue:FalkorDB/FalkorDB#1018` https://github.com/FalkorDB/FalkorDB/issues/1018
- [8] `issue:FalkorDB/FalkorDB#1947` https://github.com/FalkorDB/FalkorDB/issues/1947
- [9] `person:DvirDukhan` https://github.com/DvirDukhan
- [10] `person:AviAvni` https://github.com/AviAvni

Expected: On Aug 2, 2026 (PR #2279, tracking issue #2280) main became the development line for the Rust engine, versions 6.0 and later, while the C engine stays on master for 5.x maintenance and releases with its own CI. The Rust history is kept on the main-rs branch, which must be preserved because it is the only ref reaching those commits.


### q04: Why were graphblas.sh and redisearch.sh replaced with a native-deps crate?

**PASS** · 2026-10-18 06:53 UTC · intent why · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision

We added deps/GraphBLAS and deps/LAGraph as submodules and replaced graphblas.sh and redisearch.sh with a native-deps crate featuring a content-addressed artifact cache. [1][2][3][4] This was proposed by DvirDukhan and approved by AviAvni to tie builds to reviewable git commits, avoid stale-ABI archives from compiler bumps, and separate dependency builds from other Docker layers so that changing an unrelated line does not trigger a 12-minute rebuild, addressing issue #2315. [1][5][6][3][2] The alternative of keeping graphblas.sh and redisearch.sh scripts with version strings and bash logic was rejected. [1][2]

- [1] `decision:8e1b8d4d5cc194f8` https://github.com/FalkorDB/FalkorDB/pull/2695
- [2] `pr:FalkorDB/FalkorDB#2695` https://github.com/FalkorDB/FalkorDB/pull/2695
- [3] `issue:FalkorDB/FalkorDB#2315` https://github.com/FalkorDB/FalkorDB/issues/2315
- [4] `module:FalkorDB:deps/GraphBLAS` https://github.com/FalkorDB/FalkorDB/tree/HEAD/deps/GraphBLAS
- [5] `person:DvirDukhan` https://github.com/DvirDukhan
- [6] `person:AviAvni` https://github.com/AviAvni

Expected: GraphBLAS and LAGraph weren't tracked by git: the script cloned them at build time from a version string, so no build was tied to a reviewable commit. PR #2695 made them submodules and added a native-deps crate with a content-addressed artifact cache keyed on everything the artifacts are ABI-tied to, so a compiler bump can't reuse stale archives. The Dockerfile was split into stages so a small change no longer invalidates a ~12 minute GraphBLAS build.


### q05: Who should I ask about indexes in the Rust engine?

**PASS** · 2026-10-18 06:53 UTC · intent who-knows · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, find_experts

The experts for graph/src/index are Dvir Dukhan with a score of 42.9 percent (contributing PR #3307, PR #2350, and PR #2278), Avi Avni with a score of 31.1 percent (contributing PR #3285, PR #2897, and PR #3081), and Guy Korland with a score of 0.7 percent. [1][2][3][4][5][6][7][8][9][10]

- [1] `person:DvirDukhan` https://github.com/DvirDukhan
- [2] `pr:FalkorDB/FalkorDB#3307` https://github.com/FalkorDB/FalkorDB/pull/3307
- [3] `pr:FalkorDB/FalkorDB#2350` https://github.com/FalkorDB/FalkorDB/pull/2350
- [4] `pr:FalkorDB/FalkorDB#2278` https://github.com/FalkorDB/FalkorDB/pull/2278
- [5] `person:AviAvni` https://github.com/AviAvni
- [6] `pr:FalkorDB/FalkorDB#3285` https://github.com/FalkorDB/FalkorDB/pull/3285
- [7] `pr:FalkorDB/FalkorDB#2897` https://github.com/FalkorDB/FalkorDB/pull/2897
- [8] `pr:FalkorDB/FalkorDB#3081` https://github.com/FalkorDB/FalkorDB/pull/3081
- [9] `person:gkorland` https://github.com/gkorland
- [10] `module:FalkorDB:graph/src/index` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/index

Expected: Dvir Dukhan (DvirDukhan) is the top expert on graph/src/index (decayed score ~40; he built the native numeric index and the CoW B-tree), with Avi Avni (AviAvni) close behind (~27; recent range and vector index fixes).


### q06: Who knows the Cypher parser?

**PASS** · 2026-10-18 06:53 UTC · intent who-knows · 2 LLM calls via gemini:gemini-3.5-flash-lite · tools: find_entities, find_experts, module_owners

No owner is listed in CODEOWNERS for graph/src/parser. [1][2] Avi Avni is an expert with a score of 28.2, contributing through PR #3335, PR #3104, and PR #2910. [3][4][5][6] Dvir Dukhan is an expert with a score of 4.5. [7] Guy Korland is an expert with a score of 1.3. [8]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser
- [3] `person:AviAvni` https://github.com/AviAvni
- [4] `pr:FalkorDB/FalkorDB#3335` https://github.com/FalkorDB/FalkorDB/pull/3335
- [5] `pr:FalkorDB/FalkorDB#3104` https://github.com/FalkorDB/FalkorDB/pull/3104
- [6] `pr:FalkorDB/FalkorDB#2910` https://github.com/FalkorDB/FalkorDB/pull/2910
- [7] `person:DvirDukhan` https://github.com/DvirDukhan
- [8] `person:gkorland` https://github.com/gkorland

Expected: Avi Avni (AviAvni), by a wide margin: about 95% of human commits to graph/src/parser since Apr 2025, including recent lexer and syntax fixes.


### q07: Who owns the build folder, and who actually works on it?

**PASS** · 2026-10-18 06:53 UTC · intent owns · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, module_owners

CODEOWNERS lists @FalkorDB/falkordb-core for build. [1][2][3] The active experts who actually work on build are DvirDukhan with a 37.2% share, AviAvni with a 22.3% share, and dudizimber with a 6.3% share. [3][4][5][6][7][8][9][10][11][12][13][14][15]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `team:FalkorDB/falkordb-core` https://github.com/orgs/FalkorDB/teams/falkordb-core
- [3] `module:FalkorDB:build` https://github.com/FalkorDB/FalkorDB/tree/HEAD/build
- [4] `person:DvirDukhan` https://github.com/DvirDukhan
- [5] `pr:FalkorDB/FalkorDB#3181` https://github.com/FalkorDB/FalkorDB/pull/3181
- [6] `pr:FalkorDB/FalkorDB#3179` https://github.com/FalkorDB/FalkorDB/pull/3179
- [7] `pr:FalkorDB/FalkorDB#2695` https://github.com/FalkorDB/FalkorDB/pull/2695
- [8] `person:AviAvni` https://github.com/AviAvni
- [9] `pr:FalkorDB/FalkorDB#3163` https://github.com/FalkorDB/FalkorDB/pull/3163
- [10] `pr:FalkorDB/FalkorDB#2873` https://github.com/FalkorDB/FalkorDB/pull/2873
- [11] `pr:FalkorDB/FalkorDB#2824` https://github.com/FalkorDB/FalkorDB/pull/2824
- [12] `person:dudizimber` https://github.com/dudizimber
- [13] `pr:FalkorDB/FalkorDB#2060` https://github.com/FalkorDB/FalkorDB/pull/2060
- [14] `pr:FalkorDB/FalkorDB#1585` https://github.com/FalkorDB/FalkorDB/pull/1585
- [15] `pr:FalkorDB/FalkorDB#1576` https://github.com/FalkorDB/FalkorDB/pull/1576

Expected: CODEOWNERS assigns /build/ to the @FalkorDB/falkordb-core team. The most active people there are Dvir Dukhan (score ~33; e.g. the native-deps crate, running redis-server as a non-root user) and Avi Avni (~19).


### q08: Who owns the query planner?

**PASS** · 2026-10-18 06:53 UTC · intent owns · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, module_owners

No owner is listed in CODEOWNERS for graph/src/planner. [1][2] The active experts who actually do the work are AviAvni with a score of 51.6 (contributing via PR #3335, PR #3102, and PR #2845), DvirDukhan with a score of 14.6 (contributing via PR #2390 and PR #2570), and gkorland with a score of 6.7. [3][4][5][6][7][8][9][10]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `module:FalkorDB:graph/src/planner` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/planner
- [3] `person:AviAvni` https://github.com/AviAvni
- [4] `pr:FalkorDB/FalkorDB#3335` https://github.com/FalkorDB/FalkorDB/pull/3335
- [5] `pr:FalkorDB/FalkorDB#3102` https://github.com/FalkorDB/FalkorDB/pull/3102
- [6] `pr:FalkorDB/FalkorDB#2845` https://github.com/FalkorDB/FalkorDB/pull/2845
- [7] `person:DvirDukhan` https://github.com/DvirDukhan
- [8] `pr:FalkorDB/FalkorDB#2390` https://github.com/FalkorDB/FalkorDB/pull/2390
- [9] `pr:FalkorDB/FalkorDB#2570` https://github.com/FalkorDB/FalkorDB/pull/2570
- [10] `person:gkorland` https://github.com/gkorland

Expected: No owner is listed for graph/src/planner in CODEOWNERS. In practice Avi Avni (AviAvni) does most of the work (score ~49), followed by Dvir Dukhan (~11).


### q09: Which parts of the engine depend on a single person?

**PASS** · 2026-10-18 06:53 UTC · intent risk · 2 LLM calls via gemini:gemini-3.5-flash-lite · tools: find_entities, knowledge_risk

For the graph/src/parser module, the single expert is AviAvni with a share of 96.0%. [1][2] For the graph/src/udf module, the single expert is AviAvni with a share of 100.0%. [3][2] For the fuzz/fuzz_targets module, the single expert is AviAvni with a share of 94.0%. [4][2] For the runtime-fuzz-target/src module, the single expert is AviAvni with a share of 92.0%. [5][2] For the tests/memcheck module, the single expert is DvirDukhan with a share of 89.0%. [6][7]

- [1] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser
- [2] `person:AviAvni` https://github.com/AviAvni
- [3] `module:FalkorDB:graph/src/udf` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/udf
- [4] `module:FalkorDB:fuzz/fuzz_targets` https://github.com/FalkorDB/FalkorDB/tree/HEAD/fuzz/fuzz_targets
- [5] `module:FalkorDB:runtime-fuzz-target/src` https://github.com/FalkorDB/FalkorDB/tree/HEAD/runtime-fuzz-target/src
- [6] `module:FalkorDB:tests/memcheck` https://github.com/FalkorDB/FalkorDB/tree/HEAD/tests/memcheck
- [7] `person:DvirDukhan` https://github.com/DvirDukhan

Expected: graph/src/parser (~95% Avi Avni), graph/src/udf (100% Avi Avni) and fuzz/ (~97% Avi Avni) each have one active expert. Most other engine modules have only two (Avi Avni and Dvir Dukhan).


### q10: If we change the parser, what else usually has to change?

**PASS** · 2026-10-18 06:53 UTC · intent impact · 2 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, impact_radius

When changing graph/src/parser, the modules that most frequently change along with it are graph/src/runtime with 26 co-changes (58.0% share), graph/src/planner with 22 co-changes (49.0% share), and graph/src/graph with 12 co-changes (27.0% share). [1][2][3][4] Additional co-changed areas include the root module / with 14 co-changes (31.0% share) and tests/flow with 10 co-changes (22.0% share). [5][6]

- [1] `module:FalkorDB:graph/src/runtime` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/runtime
- [2] `module:FalkorDB:graph/src/planner` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/planner
- [3] `module:FalkorDB:graph/src/graph` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/graph
- [4] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser
- [5] `module:FalkorDB:/` https://github.com/FalkorDB/FalkorDB
- [6] `module:FalkorDB:tests/flow` https://github.com/FalkorDB/FalkorDB/tree/HEAD/tests/flow

Expected: The runtime and the planner, in either order. About half of parser-touching commits also touch graph/src/runtime and graph/src/planner. Lore measures runtime ~58% (26 of 45 commits) and planner ~49% (22 of 45); the hand count gave planner 50%, runtime 47%.


### s01: Why do we cache links in Redis?

**PASS** · 2026-10-18 06:53 UTC · intent why · 2 LLM calls via gemini:gemini-3.5-flash-lite · tools: find_entities, trace_decision, trace_decision

The team decided to use a shared Redis link cache with a 24-hour TTL instead of keeping in-process LRU caches with pub/sub invalidation. [1][2][3][4][5] This addresses issue #1 where cache misses spike after every deploy, and was proposed by im-Amrith and approved by im-Angel2305. [3][6][7] Moving to a shared Redis cache keeps the cache warm across deploys, makes edits a single delete, and avoids the complexity of pub/sub invalidation across 3 replicas spanning 2 regions. [4][5] Keeping the in-process LRU and adding pub/sub invalidation was rejected because it introduces more moving parts than a single Redis with 3 replicas across 2 regions. [4]

- [1] `decision:3dd18586343e603b` https://github.com/im-Amrith/lore-sandbox/pull/11
- [2] `pr:im-Amrith/lore-sandbox#11` https://github.com/im-Amrith/lore-sandbox/pull/11
- [3] `issue:im-Amrith/lore-sandbox#1` https://github.com/im-Amrith/lore-sandbox/issues/1
- [4] `decision:07bda31bd72e1a95` https://github.com/im-Amrith/lore-sandbox/blob/main/docs/adr/0001-link-cache.md
- [5] `doc:im-Amrith/lore-sandbox:docs/adr/0001-link-cache.md` https://github.com/im-Amrith/lore-sandbox/blob/main/docs/adr/0001-link-cache.md
- [6] `person:im-Amrith` https://github.com/im-Amrith
- [7] `person:im-Angel2305` https://github.com/im-Angel2305

Expected: PR 1 moved the link cache to a shared Redis instance (24h TTL) because each of 3 replicas had its own cache that went cold on every deploy and served stale links after edits. In-process LRU + pub/sub was rejected as more moving parts across 2 regions. Cites PR 1, issue #1, ADR 0001.


### s02: Who owns analytics?

**PASS** · 2026-10-18 06:53 UTC · intent owns · 2 LLM calls via groq:openai/gpt-oss-20b · tools: find_entities, module_owners

The CODEOWNERS file lists im-Angel2305 as the owner of the analytics module. [1][2][3] The work on analytics is performed by Priya Raman. [4][3][5]

- [1] `codeowners` https://github.com/im-Amrith/lore-sandbox/blob/HEAD/CODEOWNERS
- [2] `person:im-Angel2305` https://github.com/im-Angel2305
- [3] `module:lore-sandbox:analytics` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/analytics
- [4] `person:name:priya-raman` 
- [5] `pr:im-Amrith/lore-sandbox#14` https://github.com/im-Amrith/lore-sandbox/pull/14

Expected: CODEOWNERS lists <reviewer-login>, but all analytics commits are by Priya Raman. Ask Priya.


### s03: Which modules depend on one person?

**PASS** · 2026-10-18 06:53 UTC · intent risk · 2 LLM calls via gemini:gemini-3.5-flash-lite · tools: find_entities, knowledge_risk

For the storage module, Marta Silva is the single expert. [1][2] For the analytics module, Priya Raman is the single expert. [3][4] For the docs module, im-Amrith is the single expert. [5][6] For the api module, im-Amrith is the single expert. [5][7] For the cache module, im-Amrith is the single expert. [5][8] For the tests module, im-Amrith is the single expert. [5][9]

- [1] `person:name:marta-silva` 
- [2] `module:lore-sandbox:storage` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/storage
- [3] `person:name:priya-raman` 
- [4] `module:lore-sandbox:analytics` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/analytics
- [5] `person:im-Amrith` https://github.com/im-Amrith
- [6] `module:lore-sandbox:docs` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/docs
- [7] `module:lore-sandbox:api` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/api
- [8] `module:lore-sandbox:cache` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/cache
- [9] `module:lore-sandbox:tests` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/tests

Expected: Every sandbox module has one author, so all seven are single-expert. First come the two where that expert is not the CODEOWNERS owner: storage/ (every commit by Marta Silva; listed owner im-Amrith) and analytics/ (Priya Raman; listed owner im-Angel2305).


### n01: Why was Bolt support removed?

**PASS** · 2026-10-18 06:53 UTC · intent why · 3 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision, find_entities, trace_decision

Not found: No decision or rationale was recorded for PR #2170 removing Bolt support.. Nearest evidence: PR #2170 removed Bolt support as requested in issue #2169. [1][2]

- [1] `pr:FalkorDB/FalkorDB#2170` https://github.com/FalkorDB/FalkorDB/pull/2170
- [2] `issue:FalkorDB/FalkorDB#2169` https://github.com/FalkorDB/FalkorDB/issues/2169

Expected: Removed in PR #2170 (Jul 2026). Neither page gives a reason, so the right answer is 'no reason recorded' plus the links. Use as a second not-found test.

