// 13 F5 procedural memory: the triage Playbook and the Feedback that adjusted it, newest first.
// No row = no Playbook yet; Steward then uses the default steps (agents/steward.py).
MATCH (p:Playbook {name: $name})
OPTIONAL MATCH (f:Feedback)-[:ADJUSTS]->(p)
WITH p, f ORDER BY f.at DESC
RETURN p.name AS name, p.steps AS steps, p.version AS version,
       collect(f {.id, .text, .rule, .at, .by, .task_id})[0..10] AS feedback
