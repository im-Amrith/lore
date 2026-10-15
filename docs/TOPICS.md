# Lore topic list (draft for FalkorDB)

The fixed topic list the extraction step uses (PLAN.md pipeline step 7, milestone M5). The LLM picks 1–3 topics per PR, issue, decision or doc from this list only, so topics stay merged instead of drifting.

Built from the FalkorDB/FalkorDB repo on Oct 10, 2026: its labels, the folders under `graph/src/`, and the conventional-commit scopes in recent history (`fix(planner)`, `feat(index)`, `perf(runtime)`, `ci`, `build`).

Each topic lists the signals that point to it. Signals are hints for the LLM prompt and a cheap rule-based pre-tag, not hard rules.

| # | Topic id | What it covers | Paths | Labels / commit scopes |
| --- | --- | --- | --- | --- |
| 1 | `query-execution` | Running a plan: operators, scans, joins, expand, aggregation | `graph/src/runtime/`, `graph/src/runtime/ops/` | `component:query-engine`, `perf(runtime)`, `fix(runtime)` |
| 2 | `query-planner` | Building and optimizing plans | `graph/src/planner/`, `graph/src/planner/optimizer/` | `fix(planner)` |
| 3 | `cypher-parser` | Lexer, AST, syntax errors, parse limits | `graph/src/parser/` | `cypher` |
| 4 | `cypher-semantics` | Clause behaviour: MERGE, SET, DELETE, CALL {}, CASE, OPTIONAL MATCH, TCK compliance | `tests/tck/` | `cypher`, `c parity` |
| 5 | `cypher-functions` | Built-in functions and procedures | `graph/src/runtime/functions/` | |
| 6 | `data-types` | Values: temporal, point, list, map, vectorf32, null handling | | |
| 7 | `graph-storage` | Nodes, edges, labels, ids, deletion, id reuse | `graph/src/graph/` | `refactor(graph)`, `feat(graph)` |
| 8 | `matrices-graphblas` | Adjacency matrices, GraphBLAS/LAGraph, PreJIT kernels | `graph/src/graph/graphblas/`, `build/graphblas/` | `graphblas`, `fix(matrix)` |
| 9 | `mvcc-concurrency` | MVCC deltas, folds, snapshots, locks, concurrent readers and writers | | `test_mvcc`, `test_concurrency` |
| 10 | `range-index` | Native numeric/range index, CoW B-tree | `graph/src/index/falkordb/` | `feat(index)`, `perf(index)`, `fix(index)` |
| 11 | `fulltext-search` | Full-text indexes, RediSearch integration | `graph/src/index/redisearch/`, `deps/RediSearch` | `RediSearch` |
| 12 | `vector-search` | Vector indexes, KNN queries, embeddings | | |
| 13 | `graph-algorithms` | `algo.*` procedures: PageRank, BFS, WCC, label propagation, paths | | |
| 14 | `udf` | User-defined functions, the JS runtime | `graph/src/udf/` | |
| 15 | `effects-replication` | `GRAPH.EFFECT`, replicas, write propagation | `graph/src/effects/` | |
| 16 | `persistence-rdb` | RDB save/load, serializers, upgrades between versions | `src/serializers/` | `fix(rdb)` |
| 17 | `memory` | Memory use, `GRAPH.MEMORY`, allocator, limits | `src/allocator.rs` | `perf(mem)` |
| 18 | `commands-protocol` | Redis module commands, replies, RESP, Bolt (removed) | `src/commands/`, `src/reply.rs`, `src/dispatch.rs` | `feat(reply)` |
| 19 | `configuration` | Module config options and defaults | `src/config.rs` | |
| 20 | `observability` | Slowlog, telemetry, profiling | `src/slow_log.rs`, `src/telemetry.rs`, `docs/profiling.md` | `component/slowlog`, `component/telemetry` |
| 21 | `security` | CVEs, auth, ACL, write authorization, fork-safe CI secrets | `docs/write-authorization.md`, `CODEOWNERS` | `security`, `cve`, `fix(security)` |
| 22 | `stability-crashes` | Crashes, panics, overflows, fuzz findings | `fuzz/`, `runtime-fuzz-target/` | `critical`, `category: crash`, `bug` |
| 23 | `performance` | Benchmarks, speedups, regressions | `bench/` | `performance`, `x:perf`, `perf`, `action:run-benchmark` |
| 24 | `testing` | Flow tests, unit tests, TCK, memcheck | `tests/` | `component: tests`, `category: testing`, `test(...)` |
| 25 | `ci-cd` | GitHub Actions, merge queue, release pipelines | `.github/` | `component: ci`, `ci`, `github_actions` |
| 26 | `build-system` | Cargo, CMake, native deps, toolchain images | `build/`, `native-deps/`, `.cargo/` | `component: build`, `build`, `submodules` |
| 27 | `docker-releases` | Docker images, tags (`:latest`, `:edge`), versions | `build/runtime/`, Dockerfiles | `docker`, `Release` |
| 28 | `rust-migration` | Moving from the C engine to the Rust engine, C parity | | `rust`, `c parity`, `fixed-rust`, `6.0` |
| 29 | `dependencies` | Dependency bumps | `Cargo.lock`, `tests/requirements.txt` | `dependencies`, `chore(deps)`, `build(deps)` |
| 30 | `documentation` | Docs and READMEs | `docs/`, `*.md` | `documentation`, `docs` |

**Labels to ignore** (they say nothing about the subject): `size:*`, `Review effort *`, `Manual Review Time *`, `priority*`, `p0`–`p2`, `1w`/`2d`/date labels, `lgtm`, `no-*-activity`, `needs-*`, `ai-triage`, `action:ok-to-test`, `verify-artifacts`.

**For the sandbox org**, use its own short list (see `SANDBOX_STORY.md`): `link-cache`, `short-codes`, `redirects`, `analytics`, `storage`, `api-limits`, `docs`.

**Open question for M5:** if a second org is loaded as a tenant, it needs its own list. Build it the same way on Day 1: labels + top-level folders + commit scopes, about 20–30 topics.
