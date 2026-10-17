// 13 F5 triage inbox: triage Tasks with their issue, newest first. $status = '' for all.
// draft / approved_draft are written by Steward (M13) and the approve route.
MATCH (t:Task {type: 'triage'})-[:FOR]->(i:Issue)
WHERE $status = '' OR t.status = $status
RETURN t.id AS task_id, t.status AS status, t.at AS opened_at, t.claimed_by AS claimed_by,
       t.draft AS draft, t.approved_draft AS approved_draft, t.approved_by AS approved_by,
       t.approved_at AS approved_at,
       i.id AS issue_id, i.number AS number, i.title AS title, i.url AS url, i.state AS issue_state,
       left(coalesce(i.body, ''), 600) AS body
ORDER BY t.at DESC, i.number DESC
LIMIT $limit
