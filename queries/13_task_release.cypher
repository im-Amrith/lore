// 13 F5 Steward: give a claimed Task back (the LLM pool was out, a tool failed). It goes back to
// open so the next poll retries it; the error and attempt count stay on the Task for the inbox.
MATCH (t:Task {id: $task_id})
WHERE t.status = 'claimed' AND t.claimed_by = $agent
SET t.status = 'open', t.claimed_by = null, t.error = $error, t.attempts = coalesce(t.attempts, 0) + 1
RETURN t.id AS task_id, t.status AS status
