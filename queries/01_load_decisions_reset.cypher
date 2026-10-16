// 01 load: before reloading a source's decisions, remove the ones a re-extraction no
// longer produced (row.keep = the new decision ids for row.source_id), and the source's
// old ABOUT edges. Only extraction output is touched; the source node itself stays.
UNWIND $rows AS row
OPTIONAL MATCH (pr:PullRequest {id: row.source_id})
OPTIONAL MATCH (i:Issue {id: row.source_id})
OPTIONAL MATCH (doc:Doc {id: row.source_id})
WITH row, coalesce(pr, i, doc) AS src
WHERE src IS NOT NULL
OPTIONAL MATCH (src)-[about:ABOUT]->(:Topic)
DELETE about
WITH DISTINCT row, src
OPTIONAL MATCH (old:Decision)-[:DECIDED_IN]->(src)
WHERE NOT old.id IN row.keep
DETACH DELETE old
