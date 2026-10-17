// 10 derive: CO_CHANGED between modules that change in the same commit.
// count = commits touching both; at = the latest such commit.
// Skipped: bulk commits (tree replacements, FalkorDB PR #2279) and commits touching more
// than $max_modules modules: big refactors touch everything and would make every module
// look coupled to every other. One edge per pair (id(a) < id(b)); read it undirected.
// c.at <= $now lets the job be rerun "as of" an earlier date.
MATCH (c:Commit)-[:TOUCHES]->(m:Module)
WHERE NOT coalesce(c.bulk, false) AND c.at <= $now
WITH c, collect(m) AS mods
WHERE size(mods) >= 2 AND size(mods) <= $max_modules
UNWIND mods AS a
UNWIND mods AS b
WITH c, a, b WHERE id(a) < id(b)
  AND ($modules IS NULL OR a.id IN $modules OR b.id IN $modules)  // pairs with a touched module
WITH a, b, count(c) AS n, max(c.at) AS last
WHERE n >= $min_count
MERGE (a)-[r:CO_CHANGED]->(b)
SET r.count = n, r.at = last
RETURN count(r) AS edges
