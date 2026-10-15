// 01 load: Commit nodes and (Person)-[:AUTHORED]->(Commit).
// bulk = true marks tree-replacing commits (> 500 files), skipped by EXPERT_IN.
UNWIND $rows AS row
MERGE (c:Commit {id: row.id})
SET c.sha = row.sha, c.repo = row.repo, c.message = row.message, c.at = row.at,
    c.authored_at = row.authored_at, c.branches = row.branches, c.files_changed = row.files_changed,
    c.additions = row.additions, c.deletions = row.deletions, c.bulk = row.bulk, c.is_merge = row.is_merge
WITH c, row
MATCH (p:Person {id: row.author_id})
MERGE (p)-[a:AUTHORED]->(c)
SET a.at = row.at
