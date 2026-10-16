// 01 load: (Decision)-[:AFFECTS]->(Module).
UNWIND $rows AS row
MATCH (d:Decision {id: row.decision_id})
MATCH (m:Module {id: row.module_id})
MERGE (d)-[r:AFFECTS]->(m)
SET r.at = row.at
