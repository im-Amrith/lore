// 16 demo reset: delete a user's questions (and their answers) except $keep. The User node and
// sessions stay (16_demo_empty_sessions tidies those). Memory nodes aren't in query 93's data
// version, so the answer cache stays valid.
MATCH (:User {id: $user_id})-[:HAD]->(:Session)-[:ASKED]->(q:Question)
WHERE NOT q.id IN $keep
OPTIONAL MATCH (q)-[:ANSWERED_WITH]->(a:Answer)
DETACH DELETE q, a
