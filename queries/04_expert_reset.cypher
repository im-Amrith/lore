// 04 derive: drop every EXPERT_IN edge before recomputing, so a person whose
// activity aged out (or a newly skipped bulk commit) leaves no stale edge behind.
// $modules: module ids to recompute (a sync touched them), or null for the whole graph.
MATCH ()-[e:EXPERT_IN]->(m:Module)
WHERE $modules IS NULL OR m.id IN $modules
DELETE e
RETURN count(e) AS deleted
