// 13 F5: open issues of one repo that have no triage Task yet (what the Librarian opens Tasks for).
MATCH (i:Issue {repo: $repo})
WHERE i.state = 'open' AND NOT (:Task {type: 'triage'})-[:FOR]->(i)
RETURN i.id AS issue_id, i.title AS title
ORDER BY i.number
