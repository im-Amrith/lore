// 06 F3 team owners: modules owned by a CODEOWNERS team, with the team's known members
// and the module's top active experts. Team membership is often not public (FalkorDB's
// falkordb-core has no known members), so the answer is "owned by team X; the people who
// actually work on it are Y" rather than an empty list (golden q07).
MATCH (t:Team)-[:OWNS]->(m:Module)
OPTIONAL MATCH (member:Person)-[:MEMBER_OF]->(t)
WITH t, m, collect(coalesce(member.login, member.name)) AS members
OPTIONAL MATCH (x:Person)-[xe:EXPERT_IN]->(m)
WHERE xe.score > 0.5 AND xe.last_touch > $now - 31536000
WITH t, m, members, x, xe ORDER BY xe.score DESC
WITH t, m, members,
     collect({person: coalesce(x.login, x.name), score: xe.score, last_touch: xe.last_touch})[0..3] AS experts
RETURN m.id AS module_id, m.path AS module, t.name AS team, members, experts AS active_experts
ORDER BY module
