// 15 supersession: active decisions that a newly active decision might replace: same module
// (AFFECTS) AND same topic (ABOUT), not decided in the same place, not new in this sync themselves.
// The LLM then says which of them it really replaces (agents/... ingest/sync.py).
MATCH (n:Decision {id: $new_id})-[:AFFECTS]->(m:Module)<-[:AFFECTS]-(o:Decision)
WHERE o.status = 'active' AND NOT o.id IN $new_ids AND o.source_id <> n.source_id
  AND o.confidence >= $min_confidence
MATCH (n)-[:ABOUT]->(t:Topic)<-[:ABOUT]-(o)
WITH o, collect(DISTINCT m.id) AS modules, collect(DISTINCT t.name) AS topics
RETURN o.id AS id, o.statement AS statement, o.rationale AS rationale, o.alternatives AS alternatives,
       o.source_id AS source_id, o.valid_from AS valid_from, modules, topics
ORDER BY size(modules) + size(topics) DESC
LIMIT 8
