# Eval results

Run 2026-10-18 06:04 UTC by `scripts/eval.py` (Navigator via lore-mcp over stdio). Rows keep the run they come from (column `run`): questions that already passed aren't rerun unless asked. Scoring is deterministic: every must_cite URL cited, every key fact mentioned, every shown sentence cited (and, for not-found tests, the answer says so). See the script's docstring.

**Golden q01-q10: 7 of 10 pass. All checks: 10 of 14.**

This run: Average answer time: 4.2 s, 2.2 LLM calls per question, over 6 fresh answers. Largest prompt: 3336 tokens. Endpoints: gemini:gemini-3.5-flash-lite, gemini:gemini-3.6-flash, groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b.

| id | type | pass | must_cite | key facts | tools | llm calls | endpoints | secs | max prompt tok | dropped | run | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | cache | gemini:gemini-3.8-flash, groq:openai/gpt-oss-120b | 0.2 | 2423 | 0 | 2026-10-18 06:04 UTC |  |
| q02 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | cache | gemini:gemini-3.6-flash, gemini:gemini-3.8-flash | 0.2 | 2340 | 0 | 2026-10-18 06:04 UTC |  |
| q03 | why | PASS | 2/2 | 4/4 | find_entities, trace_decision | 2 | groq:openai/gpt-oss-120b | 0.2 | 2513 | 0 | 2026-10-18 06:04 UTC |  |
| q04 | why | FAIL | 1/1 | 2/4 | find_entities, trace_decision | 2 | groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b | 0.2 | 2471 | 0 | 2026-10-18 06:04 UTC | missing facts: submodule, cache |
| q05 | who | PASS | 1/1 | 3/3 | find_entities, find_experts, module_owners, find_experts | cache | gemini:gemini-3.6-flash, gemini:gemini-3.8-flash | 0.2 | 3125 | 0 | 2026-10-18 06:04 UTC |  |
| q06 | who | FAIL | 0/1 | 1/2 | find_entities, find_experts | 2 | groq:openai/gpt-oss-120b | 4.1 | 2378 | 0 | 2026-10-18 06:04 UTC | missing cite any evidence PR of person:AviAvni on module:FalkorDB:graph/src/parser (not cited); missing facts: graph/src/parser |
| q07 | owns | PASS | 2/2 | 3/3 | find_entities, module_owners | 2 | gemini:gemini-3.6-flash, groq:openai/gpt-oss-120b | 3.5 | 2327 | 0 | 2026-10-18 06:04 UTC |  |
| q08 | owns | FAIL | 0/1 | 3/3 | find_entities, module_owners | 2 | groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b | 2.7 | 2305 | 0 | 2026-10-18 06:04 UTC | missing cite CODEOWNERS (retrieved, not cited) |
| q09 | risk | PASS | 2/2 | 4/4 | find_entities, knowledge_risk | cache | gemini:gemini-3.6-flash, gemini:gemini-3.8-flash | 0.1 | 3214 | 0 | 2026-10-18 06:04 UTC |  |
| q10 | impact | PASS | 0/0 | 2/2 | find_entities, impact_radius | 2 | groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b | 2.2 | 3336 | 0 | 2026-10-18 06:04 UTC |  |
| s01 | why | FAIL | 2/3 | 4/4 | find_entities, trace_decision, trace_decision | cache | gemini:gemini-3.8-flash, groq:openai/gpt-oss-20b | 0.0 | 2994 | 0 | 2026-10-18 06:04 UTC | missing cite 1 (retrieved, not cited) |
| s02 | owns | PASS | 0/0 | 2/2 | find_entities, module_owners, module_owners | cache | gemini:gemini-3.6-flash, groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b | 0.0 | 2283 | 0 | 2026-10-18 06:04 UTC |  |
| s03 | risk | PASS | 0/0 | 4/4 | find_entities, knowledge_risk | 2 | groq:openai/gpt-oss-120b | 3.0 | 2686 | 0 | 2026-10-18 06:04 UTC |  |
| n01 | not-found | PASS | 2/2 | 0/0 | find_entities, trace_decision, trace_decision | 3 | gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b | 9.8 | 2102 | 0 | 2026-10-18 06:04 UTC |  |

## Answers

### q01: Why did the Rust engine drop all_nodes_matrix?

**PASS** · 2026-10-18 06:04 UTC · intent why · answer cache · tools: find_entities, trace_decision

The Rust engine removed the all_nodes_matrix from its graph storage (PR #2678). [1][2] It was only kept for a reader that no longer existed, and it caused write performance to scale linearly with the deleted‑id set due to GraphBLAS structural upkeep, while bare nodes now cost practically nothing (issue #2677). [1][3] An alternative of optimising the MVCC snapshot's deleted_nodes bitmap was considered but rejected. [1] The change was proposed by AviAvni and approved by DvirDukhan. [4][5] Rust additionally maintained all_nodes_matrix as a GraphBLAS diagonal of every live node, updating it on every create and delete and duplicating it into every write snapshot. [1]

- [1] `decision:2bf6caaed5caeaca` https://github.com/FalkorDB/FalkorDB/pull/2678
- [2] `pr:FalkorDB/FalkorDB#2678` https://github.com/FalkorDB/FalkorDB/pull/2678
- [3] `issue:FalkorDB/FalkorDB#2677` https://github.com/FalkorDB/FalkorDB/issues/2677
- [4] `person:AviAvni` https://github.com/AviAvni
- [5] `person:DvirDukhan` https://github.com/DvirDukhan

Expected: Writes after a large deletion were slow because every create and delete had to maintain all_nodes_matrix, a GraphBLAS matrix of every live node, and nothing read it any more (the scan already walked ids minus the deleted set, like the C engine). Removing it made node creation flat after mass deletes, level with C, and cut memory for 1M bare nodes from 10.1 MB to 0.1 MB.


### q02: Why does the engine now fold MVCC deltas on every write?

**PASS** · 2026-10-18 06:04 UTC · intent why · answer cache · tools: find_entities, trace_decision

The engine decided to implement an adaptive fold policy governed by a measured cost model to bound MVCC delta growth on every write path. [1][2] This was done because deltas were never folded outside GRAPH.BULK, leading to unbounded delta growth and O(|delta|) materialization overhead on reads. [1] This decision fixed issue #2388, issue #767, and issue #785. [3][4][5] They considered and rejected keeping an LSM-style ratio rule (D >= base/K), which fails because every write transaction re-touches the whole delta. [1] The policy was proposed by AviAvni and approved by DvirDukhan. [6][7][1]

- [1] `decision:1017616f47939a04` https://github.com/FalkorDB/FalkorDB/pull/2349
- [2] `pr:FalkorDB/FalkorDB#2349` https://github.com/FalkorDB/FalkorDB/pull/2349
- [3] `issue:FalkorDB/FalkorDB#2388` https://github.com/FalkorDB/FalkorDB/issues/2388
- [4] `issue:FalkorDB/FalkorDB#767` https://github.com/FalkorDB/FalkorDB/issues/767
- [5] `issue:FalkorDB/FalkorDB#785` https://github.com/FalkorDB/FalkorDB/issues/785
- [6] `person:AviAvni` https://github.com/AviAvni
- [7] `person:DvirDukhan` https://github.com/DvirDukhan

Expected: Outside GRAPH.BULK, deltas were never folded into the base matrix, so a long-lived graph grew its delta layers without limit and every read paid a cost proportional to the delta size. PR #2349 added an adaptive fold policy driven by a measured cost model on every mutation path. An LSM-style ratio rule was rejected because it ignores transaction size.


### q03: Why are there two branches, main and master?

**PASS** · 2026-10-18 06:04 UTC · intent why · 2 LLM calls via groq:openai/gpt-oss-120b · tools: find_entities, trace_decision

The decision is to migrate the default development branch to the Rust implementation of FalkorDB while keeping the C engine maintained and released from master. [1] This allows version 6.0 and later to be developed using the new Rust engine while preserving the existing C engine lineage and releases, addressing the need described in issue #2280. [1][2] The change was proposed by DvirDukhan and approved by AviAvni. [3][4]

- [1] `decision:10969052dbeec517` https://github.com/FalkorDB/FalkorDB/pull/2279
- [2] `issue:FalkorDB/FalkorDB#2280` https://github.com/FalkorDB/FalkorDB/issues/2280
- [3] `person:DvirDukhan` https://github.com/DvirDukhan
- [4] `person:AviAvni` https://github.com/AviAvni

Expected: On Aug 2, 2026 (PR #2279, tracking issue #2280) main became the development line for the Rust engine, versions 6.0 and later, while the C engine stays on master for 5.x maintenance and releases with its own CI. The Rust history is kept on the main-rs branch, which must be preserved because it is the only ref reaching those commits.


### q04: Why were graphblas.sh and redisearch.sh replaced with a native-deps crate?

**FAIL** · 2026-10-18 06:04 UTC · intent why · 2 LLM calls via groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision

The decision to replace graphblas.sh and redisearch.sh with a native-deps crate was made to tie builds to reviewable git commits, avoid stale-ABI archives from compiler bumps, and separate dependency builds from other Docker layers so that changing an unrelated line does not trigger a 12-minute rebuild. [1][2] The alternative of keeping the scripts with version strings and bash logic was rejected. [1]

- [1] `decision:8e1b8d4d5cc194f8` https://github.com/FalkorDB/FalkorDB/pull/2695
- [2] `pr:FalkorDB/FalkorDB#2695` https://github.com/FalkorDB/FalkorDB/pull/2695

Expected: GraphBLAS and LAGraph weren't tracked by git: the script cloned them at build time from a version string, so no build was tied to a reviewable commit. PR #2695 made them submodules and added a native-deps crate with a content-addressed artifact cache keyed on everything the artifacts are ABI-tied to, so a compiler bump can't reuse stale archives. The Dockerfile was split into stages so a small change no longer invalidates a ~12 minute GraphBLAS build.


### q05: Who should I ask about indexes in the Rust engine?

**PASS** · 2026-10-18 06:04 UTC · intent who-knows · answer cache · tools: find_entities, find_experts, module_owners, find_experts

For graph/src/index, no owner is listed in CODEOWNERS. [1] You should ask DvirDukhan (score 42.9) or AviAvni (score 31.1), who actively work on graph/src/index. [2][3][4][5][6][7]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `pr:FalkorDB/FalkorDB#3307` https://github.com/FalkorDB/FalkorDB/pull/3307
- [3] `pr:FalkorDB/FalkorDB#2350` https://github.com/FalkorDB/FalkorDB/pull/2350
- [4] `pr:FalkorDB/FalkorDB#2278` https://github.com/FalkorDB/FalkorDB/pull/2278
- [5] `pr:FalkorDB/FalkorDB#3285` https://github.com/FalkorDB/FalkorDB/pull/3285
- [6] `pr:FalkorDB/FalkorDB#2897` https://github.com/FalkorDB/FalkorDB/pull/2897
- [7] `pr:FalkorDB/FalkorDB#3081` https://github.com/FalkorDB/FalkorDB/pull/3081

Expected: Dvir Dukhan (DvirDukhan) is the top expert on graph/src/index (decayed score ~40; he built the native numeric index and the CoW B-tree), with Avi Avni (AviAvni) close behind (~27; recent range and vector index fixes).


### q06: Who knows the Cypher parser?

**FAIL** · 2026-10-18 06:04 UTC · intent who-knows · 2 LLM calls via groq:openai/gpt-oss-120b · tools: find_entities, find_experts

Avi Avni is the leading expert on the Cypher parser, scoring 28.2 and having authored 49 commits. [1] Dvir Dukhan also works on the parser, with a score of 4.5 and ten reviews. [2] Guy Korland has contributed to the parser as well, with two commits. [3]

- [1] `person:AviAvni` https://github.com/AviAvni
- [2] `person:DvirDukhan` https://github.com/DvirDukhan
- [3] `person:gkorland` https://github.com/gkorland

Expected: Avi Avni (AviAvni), by a wide margin: about 95% of human commits to graph/src/parser since Apr 2025, including recent lexer and syntax fixes.


### q07: Who owns the build folder, and who actually works on it?

**PASS** · 2026-10-18 06:04 UTC · intent owns · 2 LLM calls via gemini:gemini-3.6-flash, groq:openai/gpt-oss-120b · tools: find_entities, module_owners

CODEOWNERS lists FalkorDB/falkordb-core as the owner of the build module. [1] The people who actually work on the build module are DvirDukhan (score: 37.2), AviAvni (score: 22.3), and dudizimber (score: 6.3). [2][3][4][5][6][7][8][9][10]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `pr:FalkorDB/FalkorDB#3181` https://github.com/FalkorDB/FalkorDB/pull/3181
- [3] `pr:FalkorDB/FalkorDB#3179` https://github.com/FalkorDB/FalkorDB/pull/3179
- [4] `pr:FalkorDB/FalkorDB#2695` https://github.com/FalkorDB/FalkorDB/pull/2695
- [5] `pr:FalkorDB/FalkorDB#3163` https://github.com/FalkorDB/FalkorDB/pull/3163
- [6] `pr:FalkorDB/FalkorDB#2873` https://github.com/FalkorDB/FalkorDB/pull/2873
- [7] `pr:FalkorDB/FalkorDB#2824` https://github.com/FalkorDB/FalkorDB/pull/2824
- [8] `pr:FalkorDB/FalkorDB#2060` https://github.com/FalkorDB/FalkorDB/pull/2060
- [9] `pr:FalkorDB/FalkorDB#1585` https://github.com/FalkorDB/FalkorDB/pull/1585
- [10] `pr:FalkorDB/FalkorDB#1576` https://github.com/FalkorDB/FalkorDB/pull/1576

Expected: CODEOWNERS assigns /build/ to the @FalkorDB/falkordb-core team. The most active people there are Dvir Dukhan (score ~33; e.g. the native-deps crate, running redis-server as a non-root user) and Avi Avni (~19).


### q08: Who owns the query planner?

**FAIL** · 2026-10-18 06:04 UTC · intent owns · 2 LLM calls via groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b · tools: find_entities, module_owners

No owner is listed in CODEOWNERS for the query planner module graph/src/planner. [1] The primary expert on this module is AviAvni, who has contributed to PR #3335, PR #3102, and PR #2845. [2][3][4][5] Other active experts include DvirDukhan and gkorland. [6][7]

- [1] `module:FalkorDB:graph/src/planner` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/planner
- [2] `person:AviAvni` https://github.com/AviAvni
- [3] `pr:FalkorDB/FalkorDB#3335` https://github.com/FalkorDB/FalkorDB/pull/3335
- [4] `pr:FalkorDB/FalkorDB#3102` https://github.com/FalkorDB/FalkorDB/pull/3102
- [5] `pr:FalkorDB/FalkorDB#2845` https://github.com/FalkorDB/FalkorDB/pull/2845
- [6] `person:DvirDukhan` https://github.com/DvirDukhan
- [7] `person:gkorland` https://github.com/gkorland

Expected: No owner is listed for graph/src/planner in CODEOWNERS. In practice Avi Avni (AviAvni) does most of the work (score ~49), followed by Dvir Dukhan (~11).


### q09: Which parts of the engine depend on a single person?

**PASS** · 2026-10-18 06:04 UTC · intent risk · answer cache · tools: find_entities, knowledge_risk

The graph/src/parser module depends solely on single expert AviAvni. [1][2] The graph/src/udf module depends solely on single expert AviAvni. [3][2] The fuzz/fuzz_targets module depends solely on single expert AviAvni. [4][2] The runtime-fuzz-target/src module depends solely on single expert AviAvni. [5][2] The tests/memcheck module depends solely on single expert DvirDukhan. [6][7] The src/udf module depends solely on single expert swilly22. [8][9]

- [1] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser
- [2] `person:AviAvni` https://github.com/AviAvni
- [3] `module:FalkorDB:graph/src/udf` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/udf
- [4] `module:FalkorDB:fuzz/fuzz_targets` https://github.com/FalkorDB/FalkorDB/tree/HEAD/fuzz/fuzz_targets
- [5] `module:FalkorDB:runtime-fuzz-target/src` https://github.com/FalkorDB/FalkorDB/tree/HEAD/runtime-fuzz-target/src
- [6] `module:FalkorDB:tests/memcheck` https://github.com/FalkorDB/FalkorDB/tree/HEAD/tests/memcheck
- [7] `person:DvirDukhan` https://github.com/DvirDukhan
- [8] `module:FalkorDB:src/udf` https://github.com/FalkorDB/FalkorDB/tree/HEAD/src/udf
- [9] `person:swilly22` https://github.com/swilly22

Expected: graph/src/parser (~95% Avi Avni), graph/src/udf (100% Avi Avni) and fuzz/ (~97% Avi Avni) each have one active expert. Most other engine modules have only two (Avi Avni and Dvir Dukhan).


### q10: If we change the parser, what else usually has to change?

**PASS** · 2026-10-18 06:04 UTC · intent impact · 2 LLM calls via groq:openai/gpt-oss-120b, groq:openai/gpt-oss-20b · tools: find_entities, impact_radius

When the parser changes, modules graph/src/runtime, graph/src/planner, the root module, graph/src/graph, and tests/flow usually need to be updated. [1][2][3][4][5]

- [1] `module:FalkorDB:graph/src/runtime` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/runtime
- [2] `module:FalkorDB:graph/src/planner` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/planner
- [3] `module:FalkorDB:/` https://github.com/FalkorDB/FalkorDB
- [4] `module:FalkorDB:graph/src/graph` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/graph
- [5] `module:FalkorDB:tests/flow` https://github.com/FalkorDB/FalkorDB/tree/HEAD/tests/flow

Expected: The runtime and the planner, in either order. About half of parser-touching commits also touch graph/src/runtime and graph/src/planner. Lore measures runtime ~58% (26 of 45 commits) and planner ~49% (22 of 45); the hand count gave planner 50%, runtime 47%.


### s01: Why do we cache links in Redis?

**FAIL** · 2026-10-18 06:04 UTC · intent why · answer cache · tools: find_entities, trace_decision, trace_decision

The team decided to use a shared Redis link cache with a 24‑hour TTL instead of keeping in‑process LRU caches with pub/sub invalidation. [1] This keeps the cache warm across deploys, makes edits a single delete, and avoids the complexity of pub/sub invalidation across 3 replicas spanning 2 regions. [1][2]

- [1] `decision:3dd18586343e603b` https://github.com/im-Amrith/lore-sandbox/pull/11
- [2] `decision:07bda31bd72e1a95` https://github.com/im-Amrith/lore-sandbox/blob/main/docs/adr/0001-link-cache.md

Expected: PR 1 moved the link cache to a shared Redis instance (24h TTL) because each of 3 replicas had its own cache that went cold on every deploy and served stale links after edits. In-process LRU + pub/sub was rejected as more moving parts across 2 regions. Cites PR 1, issue #1, ADR 0001.


### s02: Who owns analytics?

**PASS** · 2026-10-18 06:04 UTC · intent owns · answer cache · tools: find_entities, module_owners, module_owners

The CODEOWNERS file lists im‑Angel2305 as the owner of the analytics module. [1] The active expert for analytics is Priya Raman, who authored PR #14. [2][3]

- [1] `codeowners` https://github.com/im-Amrith/lore-sandbox/blob/HEAD/CODEOWNERS
- [2] `person:name:priya-raman` 
- [3] `pr:im-Amrith/lore-sandbox#14` https://github.com/im-Amrith/lore-sandbox/pull/14

Expected: CODEOWNERS lists <reviewer-login>, but all analytics commits are by Priya Raman. Ask Priya.


### s03: Which modules depend on one person?

**PASS** · 2026-10-18 06:04 UTC · intent risk · 2 LLM calls via groq:openai/gpt-oss-120b · tools: find_entities, knowledge_risk

The storage module is maintained solely by Marta Silva. [1][2] The analytics module is maintained solely by Priya Raman. [3][4] The docs, api, root (/) and cache modules each depend on a single person, im‑Amrith. [5][6][7][8][9] The tests module also has only im‑Amrith as its expert. [10][9]

- [1] `module:lore-sandbox:storage` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/storage
- [2] `person:name:marta-silva` 
- [3] `module:lore-sandbox:analytics` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/analytics
- [4] `person:name:priya-raman` 
- [5] `module:lore-sandbox:docs` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/docs
- [6] `module:lore-sandbox:api` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/api
- [7] `module:lore-sandbox:/` https://github.com/im-Amrith/lore-sandbox
- [8] `module:lore-sandbox:cache` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/cache
- [9] `person:im-Amrith` https://github.com/im-Amrith
- [10] `module:lore-sandbox:tests` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/tests

Expected: Every sandbox module has one author, so all seven are single-expert. First come the two where that expert is not the CODEOWNERS owner: storage/ (every commit by Marta Silva; listed owner im-Amrith) and analytics/ (Priya Raman; listed owner im-Angel2305).


### n01: Why was Bolt support removed?

**PASS** · 2026-10-18 06:04 UTC · intent why · 3 LLM calls via gemini:gemini-3.5-flash-lite, groq:openai/gpt-oss-20b · tools: find_entities, trace_decision, trace_decision

Not found: no recorded decision or reason for removing bolt support in pr:FalkorDB/FalkorDB#2170. Nearest evidence: PR #2170 and issue #2169 removed bolt support from src/bolt. [1][2][3]

- [1] `pr:FalkorDB/FalkorDB#2170` https://github.com/FalkorDB/FalkorDB/pull/2170
- [2] `issue:FalkorDB/FalkorDB#2169` https://github.com/FalkorDB/FalkorDB/issues/2169
- [3] `module:FalkorDB:src/bolt` https://github.com/FalkorDB/FalkorDB/tree/HEAD/src/bolt

Expected: Removed in PR #2170 (Jul 2026). Neither page gives a reason, so the right answer is 'no reason recorded' plus the links. Use as a second not-found test.

