// 16 demo reset: delete a user's sessions that no longer hold a question.
MATCH (:User {id: $user_id})-[:HAD]->(s:Session)
WHERE NOT (s)-[:ASKED]->(:Question)
DETACH DELETE s
