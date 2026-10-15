// 01 load: Issue nodes and (Person)-[:AUTHORED]->(Issue).
UNWIND $rows AS row
MERGE (i:Issue {id: row.id})
SET i.number = row.number, i.repo = row.repo, i.title = row.title, i.body = row.body,
    i.state = row.state, i.state_reason = row.state_reason, i.labels = row.labels, i.url = row.url,
    i.opened_at = row.opened_at, i.closed_at = row.closed_at
WITH i, row
MATCH (a:Person {id: row.author_id})
MERGE (a)-[r:AUTHORED]->(i)
SET r.at = row.opened_at
