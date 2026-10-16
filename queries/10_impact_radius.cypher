// 10 F8 impact radius: what usually changes together with $module, the active decisions
// that affect those modules, and who knows them best (top EXPERT_IN).
// share = count / commits that touched $module under the same filter as the derive job
// (not bulk, <= $max_modules modules), e.g. "half of parser commits also touch planner".
MATCH (m:Module {id: $module})<-[:TOUCHES]-(c:Commit)-[:TOUCHES]->(x:Module)
WHERE NOT coalesce(c.bulk, false)
WITH m, c, count(x) AS k
WITH m, sum(CASE WHEN k <= $max_modules THEN 1 ELSE 0 END) AS base
MATCH (m)-[r:CO_CHANGED]-(n:Module)
WHERE r.count >= $min_count
OPTIONAL MATCH (d:Decision {status: 'active'})-[:AFFECTS]->(n)
WITH m, base, n, r, collect(DISTINCT {id: d.id, statement: d.statement}) AS decisions
OPTIONAL MATCH (p:Person)-[e:EXPERT_IN]->(n)
WITH base, n, r, decisions, p, e ORDER BY e.score DESC
WITH base, n, r, decisions,
     [x IN collect({person: coalesce(p.login, p.name), score: e.score}) WHERE x.person IS NOT NULL][0..3] AS experts
RETURN n.id AS module_id, n.path AS module, r.count AS count,
       CASE WHEN base > 0 THEN round(100.0 * r.count / base) ELSE 0 END AS share_pct,
       base AS module_commits,
       [x IN decisions WHERE x.id IS NOT NULL] AS decisions, experts
ORDER BY count DESC
LIMIT $limit
