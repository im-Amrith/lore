// 13 F5 work board (Librarian): open a triage Task for each given issue that has none yet.
//   (Task {id: 'task:triage:<issue id>', type: 'triage', status: 'open'})-[:FOR]->(Issue)
// MERGE on the deterministic id, so running it twice (or two workers) never opens two Tasks.
// Steward (M13) claims open Tasks with the atomic claim query in docs/PLAN.md.
UNWIND $issue_ids AS iid
MATCH (i:Issue {id: iid})
MERGE (t:Task {id: 'task:triage:' + iid})
ON CREATE SET t.type = 'triage', t.status = 'open', t.at = $now
MERGE (t)-[:FOR]->(i)
RETURN t.id AS task_id, t.status AS status, i.id AS issue_id
