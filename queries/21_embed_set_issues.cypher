// 21 embed: store Issue embeddings as vecf32 (the type the vector index reads).
UNWIND $rows AS row
MATCH (i:Issue {id: row.id})
SET i.embedding = vecf32(row.vec)
