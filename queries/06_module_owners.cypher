// 06 F3 owners of one module: CODEOWNERS owners (people and teams) vs active experts.
// Feeds the module_owners tool. Only the module's own OWNS edges count; owners are NOT
// inherited from parent modules (FalkorDB's root "/" entry is the CODEOWNERS file
// itself, not a catch-all). No OWNS edge -> listed_owner = false, i.e. "no listed owner" (golden q08).
// paper = true for a person owner with no touch in 12 months, or a team none of whose
// known members has touched the module (a team with no known members is never paper).
MATCH (m:Module {id: $module})
OPTIONAL MATCH (o)-[:OWNS]->(m)
OPTIONAL MATCH (o)-[oe:EXPERT_IN]->(m)
OPTIONAL MATCH (member:Person)-[:MEMBER_OF]->(o)
OPTIONAL MATCH (member)-[me:EXPERT_IN]->(m)
WHERE me.last_touch >= $now - 31536000
WITH m, o, oe, count(DISTINCT member) AS n_members, count(DISTINCT me) AS active_members
WITH m, collect(CASE WHEN o IS NULL THEN null ELSE {
       id: o.id, kind: labels(o)[0], name: coalesce(o.login, o.name),
       members: n_members,
       paper: CASE WHEN labels(o)[0] = 'Team' THEN n_members > 0 AND active_members = 0
                   ELSE oe IS NULL OR oe.last_touch < $now - 31536000 END
     } END) AS owners
OPTIONAL MATCH (x:Person)-[xe:EXPERT_IN]->(m)
WHERE xe.score > 0.5
WITH m, owners, x, xe ORDER BY xe.score DESC
WITH m, owners,
     collect({id: x.id, person: coalesce(x.login, x.name), score: xe.score, last_touch: xe.last_touch})[0..3] AS experts
RETURN m.id AS module_id, m.path AS module, size(owners) > 0 AS listed_owner, owners,
       experts AS active_experts
