// 13 F5 work board: Steward claims one open triage Task (the atomic claim in docs/PLAN.md).
// FalkorDB runs each write query alone on its graph, so the WHERE + SET is one step: two workers
// claiming the same Task get one row and zero rows. Zero rows = someone else has it (or it's done).
MATCH (t:Task {id: $task_id})
WHERE t.status = 'open'
SET t.status = 'claimed', t.claimed_by = $agent, t.claimed_at = $now
WITH t
MATCH (t)-[:FOR]->(i:Issue)
RETURN t.id AS task_id, t.status AS status, t.claimed_by AS claimed_by, i.id AS issue_id
