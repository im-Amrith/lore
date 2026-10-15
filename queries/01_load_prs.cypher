// 01 load: PullRequest nodes and (Person)-[:AUTHORED]->(PullRequest).
// files / modules hold the PR's changed paths, so open and draft PRs (no commits
// on the default branch yet) still say which modules they change.
UNWIND $rows AS row
MERGE (p:PullRequest {id: row.id})
SET p.number = row.number, p.repo = row.repo, p.title = row.title, p.body = row.body,
    p.state = row.state, p.is_draft = row.is_draft, p.url = row.url,
    p.created_at = row.created_at, p.merged_at = row.merged_at, p.closed_at = row.closed_at,
    p.labels = row.labels, p.files = row.files, p.modules = row.modules,
    p.additions = row.additions, p.deletions = row.deletions, p.merged_by = row.merged_by_id
WITH p, row
MATCH (a:Person {id: row.author_id})
MERGE (a)-[r:AUTHORED]->(p)
SET r.at = row.created_at
