// 01 load: Comment nodes, (Comment)-[:ON]->(PullRequest|Issue), (Person)-[:AUTHORED]->(Comment).
// kind: comment, review (a review body) or review_comment (inline, with path).
// The parent can be either label; two indexed OPTIONAL MATCHes avoid a label-free scan.
UNWIND $rows AS row
MERGE (c:Comment {id: row.id})
SET c.body = row.body, c.at = row.at, c.url = row.url, c.kind = row.kind, c.path = row.path, c.repo = row.repo
WITH c, row
OPTIONAL MATCH (pr:PullRequest {id: row.parent_id})
OPTIONAL MATCH (i:Issue {id: row.parent_id})
WITH c, row, coalesce(pr, i) AS parent
WHERE parent IS NOT NULL
MERGE (c)-[o:ON]->(parent)
SET o.at = row.at
WITH c, row
MATCH (a:Person {id: row.author_id})
MERGE (a)-[r:AUTHORED]->(c)
SET r.at = row.at
