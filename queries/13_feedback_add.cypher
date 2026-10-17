// 13 F5 feedback: a human edited Steward's draft before approving it. The edit is stored as
// (Feedback)-[:ADJUSTS]->(Playbook), and the rule learned from it is added to the Playbook's
// steps, so the next draft follows it. The Playbook is created with the default steps on first use.
MERGE (p:Playbook {name: $name})
ON CREATE SET p.steps = $default_steps, p.version = 0, p.at = $now
CREATE (f:Feedback {id: $feedback_id, text: $text, rule: $rule, before: $before, after: $after,
                    task_id: $task_id, by: $user, at: $now})
CREATE (f)-[:ADJUSTS {at: $now}]->(p)
SET p.steps = CASE WHEN $rule = '' OR $rule IN p.steps THEN p.steps ELSE p.steps + [$rule] END,
    p.version = p.version + 1, p.updated_at = $now
RETURN p.name AS name, p.steps AS steps, p.version AS version, f.id AS feedback_id
