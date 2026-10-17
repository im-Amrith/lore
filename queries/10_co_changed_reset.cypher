// 10 derive: drop every CO_CHANGED edge before recomputing.
// $modules: module ids to recompute (a sync touched them), or null for the whole graph.
MATCH (a:Module)-[r:CO_CHANGED]->(b:Module)
WHERE $modules IS NULL OR a.id IN $modules OR b.id IN $modules
DELETE r
RETURN count(r) AS deleted
