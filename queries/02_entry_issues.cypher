// 02 entry point, step 4: issues nearest to the question (vector; score is a cosine
// DISTANCE, lower = closer).
CALL db.idx.vector.queryNodes('Issue', 'embedding', $k, vecf32($q_vec)) YIELD node, score
RETURN node.id AS id, node.number AS number, node.title AS title, node.url AS url, score AS distance
ORDER BY distance ASC
LIMIT $limit
