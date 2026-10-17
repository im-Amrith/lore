// 15 supersession: record that a newer decision replaces older ones (docs/PLAN.md "Keeping knowledge
// current" step 4): (new)-[:SUPERSEDES {at, reason}]->(old), the old one's status = 'superseded'
// and valid_to = when the new one took effect (the merge). Answers then show the old one as history.
// at = when the sync learned it: "what changed since I last asked" (query 11) compares it with the
// time of the user's answer, and an ADR's own commit date can be days before the merge.
UNWIND $rows AS row
MATCH (n:Decision {id: row.new_id}), (o:Decision {id: row.old_id})
MERGE (n)-[s:SUPERSEDES]->(o)
SET s.at = row.at, s.reason = row.reason, s.source = 'sync'
SET o.status = 'superseded', o.valid_to = row.valid_to, o.superseded_by = n.id
RETURN n.id AS new_id, o.id AS old_id
