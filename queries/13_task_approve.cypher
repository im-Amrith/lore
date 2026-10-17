// 13 F5 approve: record a human's approval of a triage Task's final draft and what posting did
// (posted for real, or a dry run). Only a Task that is not yet approved can be approved (the
// WHERE makes a double click a no-op: 0 rows).
MATCH (t:Task {id: $task_id, type: 'triage'})-[:FOR]->(i:Issue)
WHERE t.status <> 'approved'
SET t.status = 'approved', t.approved_draft = $draft, t.approved_by = $user, t.approved_at = $now,
    t.posted = $posted, t.dry_run = $dry_run, t.comment_url = $comment_url
RETURN t.id AS task_id, t.status AS status, i.id AS issue_id, t.posted AS posted, t.dry_run AS dry_run,
       t.comment_url AS comment_url
