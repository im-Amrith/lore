// 01 load: (Commit)-[:PART_OF]->(PullRequest). Only links to PRs in the graph.
UNWIND $rows AS row
MATCH (c:Commit {id: row.commit_id})
MATCH (pr:PullRequest {id: row.pr_id})
MERGE (c)-[r:PART_OF]->(pr)
SET r.at = row.at
