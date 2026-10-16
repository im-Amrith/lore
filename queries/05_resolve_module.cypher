// 05 helper: resolve what a user or agent calls a module to Module ids, for the tools that take
// a module (find_experts, module_owners, impact_radius). Matches, best first:
//   rank 0  the exact id               module:FalkorDB:graph/src/index
//   rank 1  the exact path             graph/src/index
//   rank 2  a path ending in /$q       index -> graph/src/index (and proofs/index, if any)
// Ties go to the module with the most current expertise (sum of decayed EXPERT_IN scores):
// on FalkorDB "index" matches both src/index (C engine, dormant) and graph/src/index (Rust).
// $q is lowercased by the caller; ids and paths are compared lowercased. Module is small
// (135 on FalkorDB), so the scan is cheap.
// FalkorDB fix: without the parentheses, `a = $q OR p ENDS WITH '/' + $q` fails with
// "Type mismatch: expected Boolean but was String" (the + binds differently than in Neo4j).
MATCH (m:Module)
WITH m, toLower(m.id) AS mid, toLower(m.path) AS mpath
WHERE (mid = $q) OR (mpath = $q) OR (mpath ENDS WITH ('/' + $q))
WITH m, CASE WHEN mid = $q THEN 0 WHEN mpath = $q THEN 1 ELSE 2 END AS rank
OPTIONAL MATCH (:Person)-[e:EXPERT_IN]->(m)
WITH m, rank, sum(coalesce(e.score, 0.0)) AS activity
RETURN m.id AS id, m.path AS path, m.repo AS repo, rank, activity
ORDER BY rank ASC, activity DESC, size(m.path) ASC
LIMIT $limit
