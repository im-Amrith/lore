# API examples

One real response per endpoint, captured on 2026-10-17 from the local graphs (`lore_falkordb`,
`lore_im-amrith`) through the app itself (FastAPI TestClient), for building the frontend against.
Each file is `{request, status, response}`. Shapes are documented in the OpenAPI schema at `/docs`.

| File | Request | Screen |
| --- | --- | --- |
| `ask.json` | `POST /ask` FalkorDB, "Why did the Rust engine drop all_nodes_matrix?" | Ask: answer with `[n]` markers, `citations` (n, id, url), `path` (the edges to light up), `subgraph`, `cypher` ("show query") |
| `module.json` | `GET /module/graph/src/parser?org=FalkorDB` | Module page: no listed owner, experts, decisions by status, co-changed modules |
| `risk.json` | `GET /risk?org=FalkorDB` | Knowledge-risk map: modules with `bus_factor` (1 = red), `bridge_people`, `working_groups` |
| `triage.json` | `GET /triage` | Triage inbox: Tasks (one approved) with issue, draft and `related` preview |
| `memory.json` | `GET /memory/amrith` | My memory: questions per org, `changes` (empty until a decision is superseded) |
| `users.json` | `GET /users` | Username picker |

These contain test data (users `amrith`, `dvir-fan`, `eval`; approved Task #8) that the M16 reset
script clears before the demo. Regenerate after that if the frontend needs clean examples.
