// 02 entry point: find starting Decision nodes by full-text (statement, rationale).
// Answers only ever start from decisions at confidence >= $min_confidence
// (DECISION_MIN_CONFIDENCE = 0.6): below that the LLM was inferring, or the quote
// wasn't found in the source. Ranked by text score times kind weight, so "match C"
// parity decisions sit below decisions made on the project's own merits.
CALL db.idx.fulltext.queryNodes('Decision', $q_text) YIELD node, score
WHERE node.confidence >= $min_confidence
RETURN node.id AS id, node.statement AS statement, node.kind AS kind, node.status AS status,
       node.confidence AS confidence, node.source_url AS source_url,
       score * coalesce(node.weight, 1.0) AS rank
ORDER BY rank DESC
LIMIT $limit
