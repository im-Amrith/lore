// 14 username picker: create a user (no password; the name is User.id). With a GitHub login
// that is a Person in this graph, link (User)-[:IS]->(Person) (semantic memory in docs/PLAN.md).
MERGE (u:User {id: $id})
ON CREATE SET u.created_at = $now
SET u.github_login = coalesce($github_login, u.github_login)
WITH u
OPTIONAL MATCH (p:Person {login: $github_login})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (u)-[:IS]->(p))
RETURN u.id AS id, u.github_login AS github_login, p.id AS person_id
