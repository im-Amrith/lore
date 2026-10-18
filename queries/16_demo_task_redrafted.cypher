// 16 demo reset: put triage Tasks back to 'drafted' so the approve step can be shown again.
// The draft is kept (or restored from the approved text when the Task only has that); approval
// and posting fields are cleared. A Task with no text at all is left alone (Steward drafts it).
MATCH (t:Task {type: 'triage'})
WHERE t.id IN $task_ids AND coalesce(t.draft, t.approved_draft) IS NOT NULL
SET t.status = 'drafted', t.draft = coalesce(t.draft, t.approved_draft), t.claimed_by = null, t.error = null,
    t.approved_draft = null, t.approved_by = null, t.approved_at = null,
    t.posted = null, t.dry_run = null, t.comment_url = null
RETURN t.id AS task_id, t.status AS status
