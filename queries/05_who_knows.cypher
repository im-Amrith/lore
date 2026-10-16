// 05 F2 who-knows: top experts on a module, with evidence links.
// Changed from the plan: evidence is the PRs that CONTAIN the person's commits on the
// module, not PRs they authored. Commit-only authors (sandbox Marta, Priya) and people
// whose commits went in under someone else's PR otherwise show no evidence.
// Reviewed PRs on the module are returned too (evidence_reviews), so someone whose score
// comes only from reviews still has a link to show. They're collected in a separate
// WITH stage to avoid multiplying the commit rows.
// $since (epoch seconds, 0 for all time) keeps only people whose last touch is that recent.
// FalkorDB keeps the input order inside collect(), so ORDER BY before collecting
// puts the most recent PRs and commits first.
MATCH (p:Person)-[e:EXPERT_IN]->(m:Module {id: $module})
WHERE e.score > 0.5 AND coalesce(e.last_touch, 0) >= $since
OPTIONAL MATCH (p)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(m)
WHERE NOT coalesce(c.bulk, false)
OPTIONAL MATCH (c)-[:PART_OF]->(pr:PullRequest)
WITH p, e, m, c, pr ORDER BY c.at DESC
WITH p, e, m, collect(DISTINCT pr.url) AS prs, collect(DISTINCT c.id) AS commits
OPTIONAL MATCH (p)-[r:REVIEWED]->(rpr:PullRequest)<-[:PART_OF]-(rc:Commit)-[:TOUCHES]->(m)
WHERE NOT coalesce(rc.bulk, false) AND NOT (p)-[:AUTHORED]->(rpr)
WITH p, e, prs, commits, rpr ORDER BY rpr.merged_at DESC
WITH p, e, prs, commits, collect(DISTINCT rpr.url) AS reviewed_prs
RETURN p.id AS person_id, coalesce(p.login, p.name) AS person, p.name AS name,
       e.score AS score, e.authored AS authored, e.reviewed AS reviewed,
       e.commits AS commits, e.reviews AS reviews, e.last_touch AS last_touch,
       prs[0..3] AS evidence, commits[0..3] AS evidence_commits,
       reviewed_prs[0..3] AS evidence_reviews
ORDER BY score DESC LIMIT 5
