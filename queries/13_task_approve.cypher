// 13 F5 approve: record a human's approval of a triage Task's final draft. Only a Task that is
// not yet approved can be approved (the WHERE makes a double click a no-op: 0 rows).
MATCH (t:Task {id: $task_id, type: 'triage'})-[:FOR]->(i:Issue)
WHERE t.status <> 'approved'
SET t.status = 'approved', t.approved_draft = $draft, t.approved_by = $user, t.approved_at = $now
RETURN t.id AS task_id, t.status AS status, i.id AS issue_id
