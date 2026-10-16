// 01 load: drop chunks left over when a doc got shorter (n >= its new chunk count).
UNWIND $rows AS row
MATCH (c:DocChunk)-[:PART_OF]->(:Doc {id: row.doc_id})
WHERE c.n >= row.chunks
DETACH DELETE c
