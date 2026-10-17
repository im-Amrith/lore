// 13 F5 Steward: store the draft triage comment on the Task it holds. Only the claimer can write
// it (claimed_by = $agent), so a worker that lost its claim can't overwrite another's draft.
// $facts is the JSON the draft was written from (related issues, owner, reviewer, links) for the UI.
MATCH (t:Task {id: $task_id})
WHERE t.status = 'claimed' AND t.claimed_by = $agent
SET t.status = 'drafted', t.draft = $draft, t.facts = $facts, t.playbook_version = $playbook_version,
    t.drafted_by = $agent, t.drafted_at = $now, t.model = $model, t.error = null
RETURN t.id AS task_id, t.status AS status
