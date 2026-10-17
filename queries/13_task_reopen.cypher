// 13 F5 redraft: put a drafted Task back on the board so Steward drafts it again (e.g. after the
// Playbook learned a rule). Approved Tasks are final and are never reopened.
MATCH (t:Task {id: $task_id, type: 'triage'})
WHERE t.status IN ['drafted', 'open']
SET t.status = 'open', t.claimed_by = null, t.error = null
RETURN t.id AS task_id, t.status AS status
