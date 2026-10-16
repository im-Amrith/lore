// 20 extract: design docs and ADRs (docs/, design/, rfcs/, any adr/ folder). Read-only.
// READMEs outside docs/ are left out: they describe usage, not decisions.
// linked_modules: modules of PRs the doc references or that reference it. extract.py
// combines them with folders the text names (ADR 0002 names no folder, but links PR #12,
// which touched api/), and falls back to the doc's own folder only if both are empty.
// author: the doc's last author (the only one fetched).
MATCH (d:Doc {repo: $repo})
WHERE d.path STARTS WITH 'docs/' OR d.path STARTS WITH 'design/' OR d.path STARTS WITH 'rfcs/'
   OR toLower(d.path) CONTAINS 'adr/'
OPTIONAL MATCH (d)-[:REFERENCES]-(pr:PullRequest)
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(d)
WITH d, a, collect(pr.modules) AS pr_modules
RETURN d.id AS id, 'doc' AS kind, d.path AS path, d.url AS url, d.title AS title,
       d.text AS body, d.updated_at AS updated_at, d.module AS own_module,
       reduce(acc = [], ms IN pr_modules | acc + ms) AS linked_modules,
       a.id AS author_id, a.login AS author, coalesce(a.is_bot, false) AS author_is_bot,
       [] AS approvers, [] AS comments
ORDER BY path
