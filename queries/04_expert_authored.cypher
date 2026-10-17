// 04 derive: EXPERT_IN from authored commits, 180-day half-life.
// Each TOUCHES edge adds exp(-ln2 * age / 180 days): a touch today is worth 1.0,
// one 180 days old 0.5. 15552000 = 180 * 86400.
// Skips bot authors (is_bot) and tree-replacing commits (bulk = true, > 500 files,
// e.g. FalkorDB PR #2279), which would otherwise make one person expert in everything.
// t.at <= $now lets the job be rerun "as of" an earlier date.
MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[t:TOUCHES]->(m:Module)
WHERE NOT coalesce(p.is_bot, false) AND NOT coalesce(c.bulk, false) AND t.at <= $now
  AND ($modules IS NULL OR m.id IN $modules)
WITH p, m,
     sum(exp(-0.693 * ($now - t.at) / 15552000.0)) AS s,
     max(t.at) AS last,
     count(DISTINCT c) AS n
MERGE (p)-[e:EXPERT_IN]->(m)
SET e.authored = s, e.last_authored = last, e.commits = n
RETURN count(e) AS edges
