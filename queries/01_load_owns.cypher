// 01 load: (Person|Team)-[:OWNS {source: 'CODEOWNERS'}]->(Module).
UNWIND $rows AS row
OPTIONAL MATCH (p:Person {id: row.owner_id})
OPTIONAL MATCH (t:Team {id: row.owner_id})
WITH row, coalesce(p, t) AS owner
WHERE owner IS NOT NULL
MATCH (m:Module {id: row.module_id})
MERGE (owner)-[r:OWNS]->(m)
SET r.source = 'CODEOWNERS', r.pattern = row.pattern, r.at = row.at
