// 01 load: (PullRequest)-[:CLOSES]->(Issue) from GitHub's closing references.
UNWIND $rows AS row
MATCH (p:PullRequest {id: row.pr_id})
MATCH (i:Issue {id: row.issue_id})
MERGE (p)-[r:CLOSES]->(i)
SET r.at = row.at
