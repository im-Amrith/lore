// 15 sync: which of these PRs / docs have no decision extracted yet (only those are sent to the LLM;
// re-extracting a source would replace its decisions and their history with new ids).
UNWIND $ids AS sid
OPTIONAL MATCH (pr:PullRequest {id: sid})
OPTIONAL MATCH (doc:Doc {id: sid})
WITH sid, coalesce(pr, doc) AS src
WHERE src IS NOT NULL
OPTIONAL MATCH (d:Decision)-[:DECIDED_IN]->(src)
WITH sid, count(d) AS n
WHERE n = 0
RETURN sid AS id
