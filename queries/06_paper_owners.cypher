// 06 F3 paper owners: listed in CODEOWNERS (directly, or as a member of an owning team)
// but no authored or reviewed touch on the module in 12 months (31536000 s).
// Also returns the module's real top experts, so the answer is "listed: X, works on it: Y".
// The plan's team expansion (t)-[:OWNS]->(m), (o)-[:MEMBER_OF]->(t) is folded in: a team
// owner is replaced by each of its known members. Teams with no known members drop out
// here and are covered by 06_team_owners.
// FalkorDB fix: the first version used CALL { ... UNION ... } for person and team owners.
// FalkorDB returned the right rows when RETURN followed the CALL directly, but 0 rows
// once any OPTIONAL MATCH / WITH came after it. One OWNS match + CASE avoids the UNION.
MATCH (owner)-[:OWNS]->(m:Module)
OPTIONAL MATCH (member:Person)-[:MEMBER_OF]->(owner:Team)
WITH m, CASE WHEN owner:Team THEN member ELSE owner END AS o,
        CASE WHEN owner:Team THEN owner.name ELSE null END AS via_team
WHERE o IS NOT NULL
OPTIONAL MATCH (o)-[e:EXPERT_IN]->(m)
WITH o, m, via_team, e
WHERE e IS NULL OR e.last_touch < $now - 31536000
OPTIONAL MATCH (x:Person)-[xe:EXPERT_IN]->(m)
WHERE xe.score > 0.5
WITH o, m, via_team, e, x, xe ORDER BY xe.score DESC
WITH o, m, via_team, e, collect(coalesce(x.login, x.name))[0..3] AS experts
RETURN m.id AS module_id, m.path AS module, o.id AS owner_id,
       coalesce(o.login, o.name) AS paper_owner, via_team,
       e.last_touch AS owner_last_touch, experts AS active_experts
ORDER BY module
