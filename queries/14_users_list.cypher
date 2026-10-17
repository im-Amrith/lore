// 14 username picker: users of one org graph, with how many questions each asked and when last.
MATCH (u:User)
OPTIONAL MATCH (u)-[:HAD]->(:Session)-[:ASKED]->(q:Question)
OPTIONAL MATCH (u)-[:IS]->(p:Person)
RETURN u.id AS id, u.github_login AS github_login, p.id AS person_id,
       count(DISTINCT q) AS questions, max(q.at) AS last_asked
ORDER BY last_asked DESC, id
