// 21 embed: text to embed per Decision: statement + rationale + quote, so "why" questions
// match the reasoning and the source's own words, not only the one-line claim.
// $missing = true: only decisions with no embedding yet (a sync's new ones); false: all.
MATCH (d:Decision)
WHERE NOT $missing OR d.embedding IS NULL
RETURN d.id AS id, d.statement AS statement, d.rationale AS rationale, d.quote AS quote
