// 21 embed: store DocChunk embeddings as vecf32 (the type the vector index reads).
UNWIND $rows AS row
MATCH (c:DocChunk {id: row.id})
SET c.embedding = vecf32(row.vec)
