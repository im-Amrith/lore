# Eval results

Run 2026-10-17 05:24 UTC by `scripts/eval.py` (Navigator via lore-mcp over stdio). Scoring is deterministic: every must_cite URL cited, every key fact mentioned, every shown sentence cited (and, for not-found tests, the answer says so). See the script's docstring.

**Golden q01-q10: 6 of 10 pass. All checks: 8 of 14.**

| id | type | pass | must_cite | key facts | tools | dropped | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | 0 |  |
| q02 | why | PASS | 1/1 | 4/4 | find_entities, trace_decision | 0 |  |
| q03 | why | PASS | 2/2 | 4/4 | find_entities, trace_decision | 0 |  |
| q04 | why | FAIL | 1/1 | 3/4 | find_entities, trace_decision | 0 | missing facts: cache |
| q05 | who | FAIL | 0/2 | 3/3 | find_entities, find_experts | 0 | missing cite 2350 (retrieved, not cited); missing cite 2278 (retrieved, not cited) |
| q06 | who | FAIL | 1/1 | 1/2 | find_entities, find_experts | 0 | missing facts: graph/src/parser |
| q07 | owns | PASS | 2/2 | 3/3 | find_entities, module_owners | 0 |  |
| q08 | owns | PASS | 1/1 | 3/3 | find_entities, module_owners | 0 |  |
| q09 | risk | PASS | 2/2 | 4/4 | find_entities, knowledge_risk | 0 |  |
| q10 | impact | ERROR | | | | | APIStatusError: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` in organizati |
| s01 | why | PASS | 3/3 | 4/4 | find_entities, trace_decision, trace_decision | 0 |  |
| s02 | owns | FAIL | 0/0 | 1/2 | find_entities, module_owners | 0 | missing facts: Priya |
| s03 | risk | FAIL | 0/0 | 1/2 | find_entities, knowledge_risk | 0 | missing facts: Marta |
| n01 | not-found | PASS | 2/2 | 0/0 | find_entities, trace_decision, find_entities, trace_decision | 0 |  |

## Answers

### q01: Why did the Rust engine drop all_nodes_matrix?

**PASS** · intent why · model openai/gpt-oss-120b · tools: find_entities, trace_decision

The architecture decision removed the all_nodes_matrix from the Rust engine graph storage. [1] It was only maintained for a reader that no longer existed, caused write performance to scale linearly with the deleted‑id set due to GraphBLAS structural upkeep, and bare nodes now cost practically nothing. [1][2] The change was proposed by AviAvni, approved by DvirDukhan, and implemented in PR #2678. [3][4][5] The decision also notes that Rust additionally maintained all_nodes_matrix, a GraphBLAS diagonal of every live node, updated on every create and delete and duplicated into every write snapshot. [1]

- [1] `decision:2bf6caaed5caeaca` https://github.com/FalkorDB/FalkorDB/pull/2678
- [2] `issue:FalkorDB/FalkorDB#2677` https://github.com/FalkorDB/FalkorDB/issues/2677
- [3] `person:AviAvni` https://github.com/AviAvni
- [4] `person:DvirDukhan` https://github.com/DvirDukhan
- [5] `pr:FalkorDB/FalkorDB#2678` https://github.com/FalkorDB/FalkorDB/pull/2678

Expected: Writes after a large deletion were slow because every create and delete had to maintain all_nodes_matrix, a GraphBLAS matrix of every live node, and nothing read it any more (the scan already walked ids minus the deleted set, like the C engine). Removing it made node creation flat after mass deletes, level with C, and cut memory for 1M bare nodes from 10.1 MB to 0.1 MB.

### q02: Why does the engine now fold MVCC deltas on every write?

**PASS** · intent why · model gemini-3.8-flash · tools: find_entities, trace_decision

The engine now folds MVCC deltas on every write because deltas were never folded outside GRAPH.BULK, leading to unbounded delta growth and O(|delta|) materialization overhead on reads. [1][2] It implements an adaptive fold policy governed by a measured cost model rather than estimated constants. [1][3] The alternative of keeping an LSM‑style ratio rule (D ≥ base/K) was rejected because every write transaction would still re‑touch the whole delta. [1] The change was proposed by AviAvni and approved by DvirDukhan. [4][5]

- [1] `decision:1017616f47939a04` https://github.com/FalkorDB/FalkorDB/pull/2349
- [2] `issue:FalkorDB/FalkorDB#2388` https://github.com/FalkorDB/FalkorDB/issues/2388
- [3] `pr:FalkorDB/FalkorDB#2349` https://github.com/FalkorDB/FalkorDB/pull/2349
- [4] `person:AviAvni` https://github.com/AviAvni
- [5] `person:DvirDukhan` https://github.com/DvirDukhan

Expected: Outside GRAPH.BULK, deltas were never folded into the base matrix, so a long-lived graph grew its delta layers without limit and every read paid a cost proportional to the delta size. PR #2349 added an adaptive fold policy driven by a measured cost model on every mutation path. An LSM-style ratio rule was rejected because it ignores transaction size.

### q03: Why are there two branches, main and master?

**PASS** · intent why · model gemini-3.8-flash · tools: find_entities, trace_decision

The project migrated the default development branch to the Rust implementation, making `main` the active line for new development. [1][2] The existing C engine is kept on the `master` branch so that its CI and releases continue unchanged. [1][3] This split allows version 6.0 and later to be built on Rust while preserving the C engine lineage. [1] The change was proposed by DvirDukhan and approved by AviAvni. [4][5]

- [1] `decision:10969052dbeec517` https://github.com/FalkorDB/FalkorDB/pull/2279
- [2] `pr:FalkorDB/FalkorDB#2279` https://github.com/FalkorDB/FalkorDB/pull/2279
- [3] `issue:FalkorDB/FalkorDB#2280` https://github.com/FalkorDB/FalkorDB/issues/2280
- [4] `person:DvirDukhan` https://github.com/DvirDukhan
- [5] `person:AviAvni` https://github.com/AviAvni

Expected: On Aug 2, 2026 (PR #2279, tracking issue #2280) main became the development line for the Rust engine, versions 6.0 and later, while the C engine stays on master for 5.x maintenance and releases with its own CI. The Rust history is kept on the main-rs branch, which must be preserved because it is the only ref reaching those commits.

### q04: Why were graphblas.sh and redisearch.sh replaced with a native-deps crate?

**FAIL** · intent why · model openai/gpt-oss-120b · tools: find_entities, trace_decision

The replacement was done to tie builds to reviewable git commits, avoid stale‑ABI archives from compiler bumps, and separate dependency builds from other Docker layers so that changing an unrelated line does not trigger a 12‑minute rebuild. [1][2] The change was proposed by DvirDukhan and approved by AviAvni, and it closes issue #2315 which requested moving Redisearch and GraphBLAS to submodules. [1][3][4][5] An alternative of keeping the original graphblas.sh and redisearch.sh scripts with version strings and bash logic was considered but rejected. [1]

- [1] `decision:8e1b8d4d5cc194f8` https://github.com/FalkorDB/FalkorDB/pull/2695
- [2] `pr:FalkorDB/FalkorDB#2695` https://github.com/FalkorDB/FalkorDB/pull/2695
- [3] `person:DvirDukhan` https://github.com/DvirDukhan
- [4] `person:AviAvni` https://github.com/AviAvni
- [5] `issue:FalkorDB/FalkorDB#2315` https://github.com/FalkorDB/FalkorDB/issues/2315

Expected: GraphBLAS and LAGraph weren't tracked by git: the script cloned them at build time from a version string, so no build was tied to a reviewable commit. PR #2695 made them submodules and added a native-deps crate with a content-addressed artifact cache keyed on everything the artifacts are ABI-tied to, so a compiler bump can't reuse stale archives. The Dockerfile was split into stages so a small change no longer invalidates a ~12 minute GraphBLAS build.

### q05: Who should I ask about indexes in the Rust engine?

**FAIL** · intent who-knows · model openai/gpt-oss-120b · tools: find_entities, find_experts

You should ask Dvir Dukhan (person:DvirDukhan), who has the highest expertise on the Rust engine’s graph/src/index module. [1][2] Avi Avni (person:AviAvni) is also a strong contributor to the index code and can help with related questions. [3][4]

- [1] `person:DvirDukhan` https://github.com/DvirDukhan
- [2] `pr:FalkorDB/FalkorDB#3307` https://github.com/FalkorDB/FalkorDB/pull/3307
- [3] `person:AviAvni` https://github.com/AviAvni
- [4] `pr:FalkorDB/FalkorDB#3285` https://github.com/FalkorDB/FalkorDB/pull/3285

Expected: Dvir Dukhan (DvirDukhan) is the top expert on graph/src/index (decayed score ~40; he built the native numeric index and the CoW B-tree), with Avi Avni (AviAvni) close behind (~27; recent range and vector index fixes).

### q06: Who knows the Cypher parser?

**FAIL** · intent who-knows · model openai/gpt-oss-120b · tools: find_entities, find_experts

Avi Avni (person:AviAvni) is the leading expert on the Cypher parser, with a score of 28.2, 49 commits and 1 review, as shown by his contributions in PR #3335, #3104 and #2910. [1][2][3] Dvir Dukhan (person:DvirDukhan) is also recognized as an expert on the parser, with a score of 4.5 and 10 reviews, evidenced by his review activity on PR #3335, #3104 and #2910. [1][2][3] Guy Korland (person:gkorland) has contributed to the parser module, with a score of 1.3 and 2 commits. [4]

- [1] `pr:FalkorDB/FalkorDB#3335` https://github.com/FalkorDB/FalkorDB/pull/3335
- [2] `pr:FalkorDB/FalkorDB#3104` https://github.com/FalkorDB/FalkorDB/pull/3104
- [3] `pr:FalkorDB/FalkorDB#2910` https://github.com/FalkorDB/FalkorDB/pull/2910
- [4] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser

Expected: Avi Avni (AviAvni), by a wide margin: about 95% of human commits to graph/src/parser since Apr 2025, including recent lexer and syntax fixes.

### q07: Who owns the build folder, and who actually works on it?

**PASS** · intent owns · model openai/gpt-oss-120b · tools: find_entities, module_owners

CODEOWNERS lists FalkorDB/falkordb-core as the owner of the build module. [1][2][3] In practice, DvirDukhan actively works on it with a score of 37.2, evidenced by PR #3181, PR #3179, and PR #2695. [4][5][6][7] AviAvni also contributes significantly with a score of 22.3, supported by work on PR #3163, PR #2873, and PR #2824. [8][9][10][11] Additionally, dudizimber has worked on it with a score of 6.3 across PR #2060, PR #1585, and PR #1576. [12][13][14][15]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `module:FalkorDB:build` https://github.com/FalkorDB/FalkorDB/tree/HEAD/build
- [3] `team:FalkorDB/falkordb-core` https://github.com/orgs/FalkorDB/teams/falkordb-core
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

**PASS** · intent owns · model gemini-3.8-flash · tools: find_entities, module_owners

No owner is listed in CODEOWNERS for the query planner module (graph/src/planner). [1] The active experts who maintain it are AviAvni (score 51.6), DvirDukhan (score 14.6) and gkorland. [2][3][4][5][6][7][8][9]

- [1] `codeowners` https://github.com/FalkorDB/FalkorDB/blob/HEAD/CODEOWNERS
- [2] `person:AviAvni` https://github.com/AviAvni
- [3] `pr:FalkorDB/FalkorDB#3335` https://github.com/FalkorDB/FalkorDB/pull/3335
- [4] `pr:FalkorDB/FalkorDB#3102` https://github.com/FalkorDB/FalkorDB/pull/3102
- [5] `pr:FalkorDB/FalkorDB#2845` https://github.com/FalkorDB/FalkorDB/pull/2845
- [6] `person:DvirDukhan` https://github.com/DvirDukhan
- [7] `pr:FalkorDB/FalkorDB#2390` https://github.com/FalkorDB/FalkorDB/pull/2390
- [8] `pr:FalkorDB/FalkorDB#2570` https://github.com/FalkorDB/FalkorDB/pull/2570
- [9] `person:gkorland` https://github.com/gkorland

Expected: No owner is listed for graph/src/planner in CODEOWNERS. In practice Avi Avni (AviAvni) does most of the work (score ~49), followed by Dvir Dukhan (~11).

### q09: Which parts of the engine depend on a single person?

**PASS** · intent risk · model openai/gpt-oss-120b · tools: find_entities, knowledge_risk

The parser module (graph/src/parser) has a bus factor of 1, with AviAvni as the sole expert. [1][2] The UDF module under the graph directory (graph/src/udf) is also owned exclusively by AviAvni. [3][2] All fuzz‑target code (fuzz/fuzz_targets) relies on a single contributor, AviAvni. [4][2] The memory‑check test suite (tests/memcheck) is maintained solely by DvirDukhan. [5][6] Both the user‑defined‑function source (src/udf) and the result‑set handling code (src/resultset) depend on a single owner, swilly22. [7][8][9]

- [1] `module:FalkorDB:graph/src/parser` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/parser
- [2] `person:AviAvni` https://github.com/AviAvni
- [3] `module:FalkorDB:graph/src/udf` https://github.com/FalkorDB/FalkorDB/tree/HEAD/graph/src/udf
- [4] `module:FalkorDB:fuzz/fuzz_targets` https://github.com/FalkorDB/FalkorDB/tree/HEAD/fuzz/fuzz_targets
- [5] `module:FalkorDB:tests/memcheck` https://github.com/FalkorDB/FalkorDB/tree/HEAD/tests/memcheck
- [6] `person:DvirDukhan` https://github.com/DvirDukhan
- [7] `module:FalkorDB:src/udf` https://github.com/FalkorDB/FalkorDB/tree/HEAD/src/udf
- [8] `module:FalkorDB:src/resultset` https://github.com/FalkorDB/FalkorDB/tree/HEAD/src/resultset
- [9] `person:swilly22` https://github.com/swilly22

Expected: graph/src/parser (~95% Avi Avni), graph/src/udf (100% Avi Avni) and fuzz/ (~97% Avi Avni) each have one active expert. Most other engine modules have only two (Avi Avni and Dvir Dukhan).

### q10: If we change the parser, what else usually has to change?

ERROR: APIStatusError: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` in organization `org_01k91fatb8evysq4zz5z1fceg1` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 8540, please reduce your message size and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

### s01: Why do we cache links in Redis?

**PASS** · intent why · model openai/gpt-oss-120b · tools: find_entities, trace_decision, trace_decision

The team moved the link cache into a shared Redis instance with a 24‑hour TTL to keep the cache warm across deployments and avoid cold‑cache spikes. [1][2][3] A single delete of the Redis key on link edit invalidates the cache for all three API replicas across two regions, eliminating the need for pub/sub invalidation. [4][5] This design simplifies the architecture compared to keeping in‑process LRU caches with pub/sub, reducing moving parts and operational risk. [4][1]

- [1] `decision:07bda31bd72e1a95` https://github.com/im-Amrith/lore-sandbox/blob/main/docs/adr/0001-link-cache.md
- [2] `doc:im-Amrith/lore-sandbox:docs/adr/0001-link-cache.md` https://github.com/im-Amrith/lore-sandbox/blob/main/docs/adr/0001-link-cache.md
- [3] `issue:im-Amrith/lore-sandbox#1` https://github.com/im-Amrith/lore-sandbox/issues/1
- [4] `decision:3dd18586343e603b` https://github.com/im-Amrith/lore-sandbox/pull/11
- [5] `pr:im-Amrith/lore-sandbox#11` https://github.com/im-Amrith/lore-sandbox/pull/11

Expected: PR 1 moved the link cache to a shared Redis instance (24h TTL) because each of 3 replicas had its own cache that went cold on every deploy and served stale links after edits. In-process LRU + pub/sub was rejected as more moving parts across 2 regions. Cites PR 1, issue #1, ADR 0001.

### s02: Who owns analytics?

**FAIL** · intent owns · model openai/gpt-oss-120b · tools: find_entities, module_owners

CODEOWNERS lists im-Angel2305 as the owner of the analytics module. [1][2] The analytics module is defined at path analytics in the lore‑sandbox repository. [3]

- [1] `codeowners` https://github.com/im-Amrith/lore-sandbox/blob/HEAD/CODEOWNERS
- [2] `person:im-Angel2305` https://github.com/im-Angel2305
- [3] `module:lore-sandbox:analytics` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/analytics

Expected: CODEOWNERS lists <reviewer-login>, but all analytics commits are by Priya Raman. Ask Priya.

### s03: Which modules depend on one person?

**FAIL** · intent risk · model openai/gpt-oss-120b · tools: find_entities, knowledge_risk

The modules that depend on a single person are storage, analytics, docs, api, /, cache, and tests. [1][2][3][4][5][6][7] Each of these modules has a bus_factor of 1, indicating they are single‑expert modules. [1][2][3][4][5][6][7]

- [1] `module:lore-sandbox:storage` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/storage
- [2] `module:lore-sandbox:analytics` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/analytics
- [3] `module:lore-sandbox:docs` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/docs
- [4] `module:lore-sandbox:api` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/api
- [5] `module:lore-sandbox:/` https://github.com/im-Amrith/lore-sandbox
- [6] `module:lore-sandbox:cache` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/cache
- [7] `module:lore-sandbox:tests` https://github.com/im-Amrith/lore-sandbox/tree/HEAD/tests

Expected: storage/: every commit is by Marta Silva (the listed owner, <your-login>, has never touched it).

### n01: Why was Bolt support removed?

**PASS** · intent why · model openai/gpt-oss-120b · tools: find_entities, trace_decision, find_entities, trace_decision

Not found: no decision with rationale found. Nearest evidence: PR #2170 removed Bolt support from the codebase. [1] The change was tracked in issue #2169, which opened a request to remove BOLT support. [2]

- [1] `pr:FalkorDB/FalkorDB#2170` https://github.com/FalkorDB/FalkorDB/pull/2170
- [2] `issue:FalkorDB/FalkorDB#2169` https://github.com/FalkorDB/FalkorDB/issues/2169

Expected: Removed in PR #2170 (Jul 2026). Neither page gives a reason, so the right answer is 'no reason recorded' plus the links. Use as a second not-found test.

