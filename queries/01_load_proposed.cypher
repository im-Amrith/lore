// 01 load: (Person)-[:PROPOSED]->(Decision). Only the source's author can propose.
UNWIND $rows AS row
MATCH (d:Decision {id: row.decision_id})
MATCH (p:Person {id: row.person_id})
MERGE (p)-[r:PROPOSED]->(d)
SET r.at = row.at
