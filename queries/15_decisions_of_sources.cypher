// 15 sync: the active decisions decided in some sources (the newly extracted ones), with their modules.
UNWIND $ids AS sid
MATCH (d:Decision {source_id: sid})
WHERE d.status = 'active'
OPTIONAL MATCH (d)-[:AFFECTS]->(m:Module)
RETURN d.id AS id, d.statement AS statement, collect(m.id) AS modules
