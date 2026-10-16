// 05 F2 who-knows for a topic instead of a module: people who authored or reviewed PRs
// ABOUT the topic (Topic edges come from extraction, M5). Score = authored PRs + 0.5 per
// reviewed PR, the same half weight query 4 gives reviews, time-decayed with the same 180-day
// half-life (15552000 s) from the PR's merge (or creation) time. Bots are left out.
// $since (epoch seconds, or 0) drops older PRs.
MATCH (t:Topic {name: $topic})<-[:ABOUT]-(pr:PullRequest)
WITH pr, coalesce(pr.merged_at, pr.created_at, 0) AS at
WHERE at >= $since
MATCH (p:Person)-[r:AUTHORED|REVIEWED]->(pr)
WHERE NOT coalesce(p.is_bot, false)
WITH p, pr, at, max(CASE WHEN type(r) = 'AUTHORED' THEN 1.0 ELSE 0.5 END) AS w
WITH p, pr, at, w * exp(-0.693 * ($now - at) / 15552000.0) AS s
ORDER BY at DESC
WITH p, sum(s) AS score, max(at) AS last_touch, count(pr) AS prs, collect(pr.url) AS urls
WHERE score > 0.5
RETURN p.id AS person_id, coalesce(p.login, p.name) AS person, p.name AS name,
       score, last_touch, prs, urls[0..3] AS evidence
ORDER BY score DESC LIMIT 5
