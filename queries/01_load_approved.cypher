// 01 load: (Person)-[:APPROVED]->(Decision). Only the PR's approving human reviewers.
UNWIND $rows AS row
MATCH (d:Decision {id: row.decision_id})
MATCH (p:Person {id: row.person_id})
MERGE (p)-[r:APPROVED]->(d)
SET r.at = row.at
