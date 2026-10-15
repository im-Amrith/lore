// 01 load: (Commit)-[:TOUCHES]->(Module), line counts summed per module.
UNWIND $rows AS row
MATCH (c:Commit {id: row.commit_id})
MATCH (m:Module {id: row.module_id})
MERGE (c)-[t:TOUCHES]->(m)
SET t.additions = row.additions, t.deletions = row.deletions, t.files = row.files, t.at = row.at
