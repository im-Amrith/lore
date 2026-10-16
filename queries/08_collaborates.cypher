// 08 derive: COLLABORATES, author -> reviewer.
// weight = distinct PRs where a authored and b reviewed; at = b's latest review among them.
// Direction matters for PageRank: score flows to the people authors rely on for review.
// Skips bots on either side and self-reviews (authors replying in their own review threads).
// r.at <= $now lets the job be rerun "as of" an earlier date.
MATCH (a:Person)-[:AUTHORED]->(pr:PullRequest)<-[r:REVIEWED]-(b:Person)
WHERE a <> b AND NOT coalesce(a.is_bot, false) AND NOT coalesce(b.is_bot, false)
  AND r.at <= $now
WITH a, b, pr, max(r.at) AS at
WITH a, b, count(pr) AS w, max(at) AS last
MERGE (a)-[c:COLLABORATES]->(b)
SET c.weight = w, c.at = last
RETURN count(c) AS edges, sum(w) AS total_weight
