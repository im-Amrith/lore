// 02 entry point, step 2: doc chunks nearest to the question (vector only; score is a
// cosine DISTANCE, lower = closer). Returns the doc so an answer can cite the page.
CALL db.idx.vector.queryNodes('DocChunk', 'embedding', $k, vecf32($q_vec)) YIELD node, score
MATCH (node)-[:PART_OF]->(doc:Doc)
RETURN node.id AS id, doc.id AS doc_id, doc.path AS path, doc.url AS url,
       left(node.text, 200) AS snippet, score AS distance
ORDER BY distance ASC
LIMIT $limit
