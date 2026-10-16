// 08 derive: COLLABORATES_STRONG, a copy of COLLABORATES kept only for repeat collaborators
// (weight >= $min_weight), used by label propagation alone.
// Why: on the full graph, synchronous label propagation never settles. Hub reviewers and
// one-off authors swap labels every iteration (FalkorDB, Oct 2026: iteration 10 = 20 = 50,
// 11 = 5), so the groups depend on maxIterations. algo.labelPropagation has no edge-weight
// filter, so the filter lives in a separate relationship type. With weight >= 2 it settles.
// Run after 08_collaborates.
MATCH (a:Person)-[c:COLLABORATES]->(b:Person)
WHERE c.weight >= $min_weight
MERGE (a)-[s:COLLABORATES_STRONG]->(b)
SET s.weight = c.weight, s.at = c.at
RETURN count(s) AS edges
