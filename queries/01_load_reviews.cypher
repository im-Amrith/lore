// 01 load: (Person)-[:REVIEWED {id, state, at}]->(PullRequest), one edge per review.
UNWIND $rows AS row
MATCH (a:Person {id: row.person_id})
MATCH (p:PullRequest {id: row.pr_id})
MERGE (a)-[r:REVIEWED {id: row.id}]->(p)
SET r.state = row.state, r.at = row.at
