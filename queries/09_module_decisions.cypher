// 09 F5 triage: decisions that AFFECT any of $modules (the modules where similar issues were
// fixed), with status and kind so the tool can keep proposed and superseded ones apart from
// current ones. Decisions below $min_confidence are left out.
UNWIND $modules AS mid
MATCH (d:Decision)-[:AFFECTS]->(m:Module {id: mid})
WHERE d.confidence >= $min_confidence
WITH d, collect(DISTINCT m.id) AS modules
RETURN d.id AS id, d.statement AS statement, d.status AS status, d.kind AS kind,
       d.confidence AS confidence, d.source_id AS source_id, d.source_url AS source_url, modules
ORDER BY size(modules) DESC, d.valid_from DESC
LIMIT $limit
