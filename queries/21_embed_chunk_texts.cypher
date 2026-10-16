// 21 embed: text to embed per DocChunk, with its doc's title or path as context.
MATCH (c:DocChunk)-[:PART_OF]->(d:Doc)
RETURN c.id AS id, c.text AS text, coalesce(d.title, d.path) AS doc
