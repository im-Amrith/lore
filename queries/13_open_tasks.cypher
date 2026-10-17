// 13 F5 work board: open triage Tasks, oldest first (what Steward tries to claim). attempts counts
// drafts that failed and were released; Steward skips a Task after STEWARD_MAX_ATTEMPTS.
MATCH (t:Task {type: 'triage', status: 'open'})-[:FOR]->(i:Issue)
RETURN t.id AS task_id, i.id AS issue_id, t.at AS opened_at, coalesce(t.attempts, 0) AS attempts
ORDER BY t.at ASC, i.number ASC
LIMIT $limit
