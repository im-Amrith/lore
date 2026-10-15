// 91 check (M3 Done when): Person -AUTHORED-> PullRequest -CLOSES-> Issue.
MATCH (p:Person)-[:AUTHORED]->(pr:PullRequest)-[:CLOSES]->(i:Issue)
RETURN p.id AS person, pr.number AS pr, pr.title AS pr_title, i.number AS issue, i.title AS issue_title
ORDER BY pr.number
LIMIT $limit
