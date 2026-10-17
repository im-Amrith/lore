// 21 embed: text to embed per DocChunk, with its doc's title or path as context.
// $doc_ids: only the chunks of these docs (a sync's changed docs), or null for all.
MATCH (c:DocChunk)-[:PART_OF]->(d:Doc)
WHERE $doc_ids IS NULL OR d.id IN $doc_ids
RETURN c.id AS id, c.text AS text, coalesce(d.title, d.path) AS doc
