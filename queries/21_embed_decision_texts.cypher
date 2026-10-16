// 21 embed: text to embed per Decision: statement + rationale + quote, so "why" questions
// match the reasoning and the source's own words, not only the one-line claim.
MATCH (d:Decision)
RETURN d.id AS id, d.statement AS statement, d.rationale AS rationale, d.quote AS quote
