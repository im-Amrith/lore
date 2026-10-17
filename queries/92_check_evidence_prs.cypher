// 92 eval check (golden q06 must_cite_evidence): which of the cited PR urls are evidence of
// $person's work on $module: the PR contains a commit by them touching the module (the same
// evidence rule as query 05), or they authored the PR and one of its commits touches it.
// Bulk tree-replacing commits (#2279) never count.
MATCH (p:Person {id: $person}), (m:Module {id: $module})
MATCH (pr:PullRequest)<-[:PART_OF]-(c:Commit)-[:TOUCHES]->(m)
WHERE pr.url IN $urls AND NOT coalesce(c.bulk, false)
  AND ((p)-[:AUTHORED]->(c) OR (p)-[:AUTHORED]->(pr))
RETURN collect(DISTINCT pr.url) AS urls
