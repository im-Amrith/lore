// 20 extract: closed issues with a long human discussion ($min_comments+ comments by
// non-bot accounts), with that discussion. Read-only.
// modules: modules of the PRs that close the issue (an issue touches no files itself).
// Bot-authored issues come back with author_is_bot = true and are skipped in Python.
MATCH (i:Issue {repo: $repo})
WHERE i.state = 'closed'
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(i)
OPTIONAL MATCH (c:Comment)-[:ON]->(i)
OPTIONAL MATCH (ca:Person)-[:AUTHORED]->(c)
WITH i, a, c, ca ORDER BY c.at
WITH i, a,
     collect(CASE WHEN c IS NOT NULL AND NOT coalesce(ca.is_bot, false)
             THEN {author: coalesce(ca.login, ca.name), at: c.at, kind: c.kind, body: c.body} END) AS comments
WHERE size(comments) >= $min_comments
OPTIONAL MATCH (pr:PullRequest)-[:CLOSES]->(i)
WITH i, a, comments, collect(pr.modules) AS pr_modules
RETURN i.id AS id, 'issue' AS kind, i.number AS number, i.url AS url, i.title AS title,
       i.body AS body, i.state AS state, i.opened_at AS created_at, i.closed_at AS closed_at,
       i.labels AS labels,
       reduce(acc = [], ms IN pr_modules | acc + ms) AS modules,
       a.id AS author_id, a.login AS author, coalesce(a.is_bot, false) AS author_is_bot,
       [] AS approvers, comments
ORDER BY number
