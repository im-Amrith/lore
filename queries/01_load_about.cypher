// 01 load: (Decision|PullRequest|Issue|Doc)-[:ABOUT]->(Topic), from extraction's topic tags.
UNWIND $rows AS row
MATCH (t:Topic {name: row.topic})
OPTIONAL MATCH (d:Decision {id: row.src_id})
OPTIONAL MATCH (pr:PullRequest {id: row.src_id})
OPTIONAL MATCH (i:Issue {id: row.src_id})
OPTIONAL MATCH (doc:Doc {id: row.src_id})
WITH t, row, coalesce(d, pr, i, doc) AS src
WHERE src IS NOT NULL
MERGE (src)-[r:ABOUT]->(t)
SET r.at = row.at
