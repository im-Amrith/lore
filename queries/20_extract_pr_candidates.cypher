// 20 extract: pull requests to send to decision extraction, with the human-written
// context around them. Read-only.
// Candidates: merged PRs with a body over $min_body characters, plus the PRs in $must.
// $all = true takes every PR in the repo, open and draft ones included (sandbox: PR #16).
// Bot text is dropped here: comments by is_bot accounts, and approvals by bots.
// approvers: humans who approved, never the PR author (proposed_by / approved_by choices).
// issues: issues the PR closes or references, so a PR that only says "see #2280" still
// gets the issue's text; bot-authored issues are left out. closes = true for CLOSES edges,
// which extract.py puts first (#2279 references dozens of issues it fixed in passing).
MATCH (pr:PullRequest {repo: $repo})
WHERE $all OR pr.number IN $must
   OR (pr.merged_at IS NOT NULL AND size(coalesce(pr.body, '')) > $min_body)
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(pr)
OPTIONAL MATCH (rv:Person)-[:REVIEWED {state: 'approved'}]->(pr)
WHERE NOT coalesce(rv.is_bot, false) AND (a IS NULL OR rv <> a)
WITH pr, a, collect(DISTINCT rv.login) AS approvers
OPTIONAL MATCH (c:Comment)-[:ON]->(pr)
OPTIONAL MATCH (ca:Person)-[:AUTHORED]->(c)
WITH pr, a, approvers, c, ca ORDER BY c.at
WITH pr, a, approvers,
     collect(CASE WHEN c IS NOT NULL AND NOT coalesce(ca.is_bot, false)
             THEN {author: coalesce(ca.login, ca.name), at: c.at, kind: c.kind, body: c.body} END) AS comments
OPTIONAL MATCH (pr)-[l:CLOSES|REFERENCES]->(i:Issue)
OPTIONAL MATCH (ia:Person)-[:AUTHORED]->(i)
WITH pr, a, approvers, comments,
     collect(DISTINCT CASE WHEN i IS NOT NULL AND NOT coalesce(ia.is_bot, false)
             THEN {id: i.id, number: i.number, title: i.title, body: i.body, closes: type(l) = 'CLOSES'} END) AS issues
// committers: who wrote the PR's commits, most commits first. When the opener wrote none
// of them (sandbox PRs #14, #15 opened for Priya and Marta), extract.py proposes the top one.
OPTIONAL MATCH (cp:Person)-[:AUTHORED]->(cc:Commit)-[:PART_OF]->(pr)
WITH pr, a, approvers, comments, issues, cp, count(cc) AS n ORDER BY n DESC
WITH pr, a, approvers, comments, issues,
     collect(CASE WHEN cp IS NOT NULL
             THEN {id: cp.id, login: cp.login, is_bot: coalesce(cp.is_bot, false), commits: n} END) AS committers
RETURN pr.id AS id, 'pr' AS kind, pr.number AS number, pr.url AS url, pr.title AS title,
       pr.body AS body, pr.state AS state, pr.is_draft AS is_draft,
       pr.created_at AS created_at, pr.merged_at AS merged_at, pr.labels AS labels,
       pr.files AS files, pr.modules AS modules,
       a.id AS author_id, a.login AS author, coalesce(a.is_bot, false) AS author_is_bot,
       approvers, comments, issues, committers
ORDER BY number
