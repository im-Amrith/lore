// 09 F5 triage: past issues most similar to a new one, and where they were fixed.
// $issue_vec embeds the new issue (title + start of body, as stored on Issue.embedding).
// score is a cosine DISTANCE (1 - cosine similarity, 0..2): lower = more similar, so rows
// are ordered ascending and $max_distance drops weak matches. $issue_id (or null) excludes
// the issue itself when it is already in the graph.
// The modules come from the closing PR's commits and feed queries 5 and 6 (owner, reviewer).
CALL db.idx.vector.queryNodes('Issue', 'embedding', $k, vecf32($issue_vec)) YIELD node, score
WITH node AS similar, score AS distance
WHERE similar.id <> coalesce($issue_id, '') AND distance <= $max_distance
OPTIONAL MATCH (similar)<-[:CLOSES]-(pr:PullRequest)
OPTIONAL MATCH (pr)<-[:PART_OF]-(:Commit)-[:TOUCHES]->(m:Module)
RETURN similar.id AS id, similar.number AS number, similar.title AS title, similar.state AS state,
       similar.url AS url, distance,
       collect(DISTINCT pr.url) AS fixes, collect(DISTINCT m.id) AS modules
ORDER BY distance ASC
LIMIT $limit
