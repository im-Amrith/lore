// 11 F6 memory read (the recall tool, part 1): this user's past questions, newest first,
// with the nodes each answer cited. Every memory query starts from (:User {id: $user_id}),
// so users never see each other's history. $topic ('' for all) keeps questions whose text
// contains it (lowercased), or whose answer cited a node ABOUT a topic of that name.
// FalkorDB fix: `any(k IN cited WHERE (k)-[:ABOUT]->(:Topic ...))` fails with "Type mismatch:
// expected Null but was Pointer"; an OPTIONAL MATCH + count does the same.
MATCH (:User {id: $user_id})-[:HAD]->(s:Session)-[:ASKED]->(q:Question)-[:ANSWERED_WITH]->(a:Answer)
OPTIONAL MATCH (a)-[:CITED]->(k)
OPTIONAL MATCH (k)-[:ABOUT]->(t:Topic {name: $topic})
WITH s, q, a, collect(DISTINCT k) AS cited, count(t) AS on_topic
WHERE $topic = '' OR toLower(q.text) CONTAINS $topic OR on_topic > 0
RETURN q.id AS question_id, q.text AS question, q.intent AS intent, q.at AS at,
       s.id AS session_id, a.id AS answer_id, left(a.text, 300) AS answer,
       [k IN cited | k.id] AS cited
ORDER BY at DESC
LIMIT $limit
