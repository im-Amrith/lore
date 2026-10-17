// 13 Librarian intake: a new or edited sandbox issue from the poll or the webhook (GitHub REST
// shape, normalised in ingest/live.py). The author is MERGEd too: a first-time reporter has no
// Person yet. ON CREATE only, so a known person's name and activity from the full load stay.
// No emails: REST issue authors carry only a login.
UNWIND $rows AS row
MERGE (a:Person {id: row.author_id})
ON CREATE SET a.login = row.author_login, a.name = row.author_login, a.is_bot = row.author_is_bot,
              a.first_seen = row.opened_at, a.last_active = row.opened_at
MERGE (i:Issue {id: row.id})
SET i.number = row.number, i.repo = row.repo, i.title = row.title, i.body = row.body,
    i.state = row.state, i.state_reason = row.state_reason, i.labels = row.labels, i.url = row.url,
    i.opened_at = row.opened_at, i.closed_at = row.closed_at
MERGE (a)-[r:AUTHORED]->(i)
SET r.at = row.opened_at
RETURN i.id AS id
