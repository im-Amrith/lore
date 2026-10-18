// 16 demo reset: the triage Tasks for these sandbox issue numbers, with what a reset would need
// (a draft, or an approved draft to restore it from).
MATCH (t:Task {type: 'triage'})-[:FOR]->(i:Issue)
WHERE t.id IN $task_ids
RETURN i.number AS number, t.id AS task_id, t.status AS status,
       t.draft IS NOT NULL AS has_draft, t.approved_draft IS NOT NULL AS has_approved_draft,
       t.approved_by AS approved_by
ORDER BY number
