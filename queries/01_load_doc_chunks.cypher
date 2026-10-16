// 01 load: DocChunk nodes, cut from Doc.text by ingest/embed.py (~800 chars, overlapping),
// linked (DocChunk)-[:PART_OF]->(Doc). Embeddings are set afterwards by 21_embed_set_chunks.
UNWIND $rows AS row
MATCH (d:Doc {id: row.doc_id})
MERGE (c:DocChunk {id: row.id})
SET c.text = row.text, c.n = row.n, c.doc_id = row.doc_id, c.url = d.url
MERGE (c)-[:PART_OF]->(d)
