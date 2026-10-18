// 16 demo reset: delete a test user with everything they asked (Session, Question, Answer).
// Only the user's own memory nodes are touched; CITED edges go with the Answers.
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[:HAD]->(s:Session)
OPTIONAL MATCH (s)-[:ASKED]->(q:Question)
OPTIONAL MATCH (q)-[:ANSWERED_WITH]->(a:Answer)
DETACH DELETE a, q, s, u
