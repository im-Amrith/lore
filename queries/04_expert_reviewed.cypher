// 04 derive: EXPERT_IN from reviews, half the weight of authoring.
// A reviewer counts once per (PR, module), dated by their latest review on that PR.
// The plan's sketch used WITH DISTINCT p, r, m, which counts every review event,
// so five "commented" replies on one PR scored 5x; collapsing to the PR fixes that.
// Self-reviews (authors replying in review threads) are skipped, as are bots and bulk commits.
MATCH (p:Person)-[r:REVIEWED]->(pr:PullRequest)<-[:PART_OF]-(c:Commit)-[:TOUCHES]->(m:Module)
WHERE NOT coalesce(p.is_bot, false) AND NOT coalesce(c.bulk, false) AND r.at <= $now
  AND NOT (p)-[:AUTHORED]->(pr) AND ($modules IS NULL OR m.id IN $modules)
WITH p, pr, m, max(r.at) AS at
WITH p, m,
     sum(0.5 * exp(-0.693 * ($now - at) / 15552000.0)) AS s,
     max(at) AS last,
     count(pr) AS n
MERGE (p)-[e:EXPERT_IN]->(m)
SET e.reviewed = s, e.last_reviewed = last, e.reviews = n
RETURN count(e) AS edges
