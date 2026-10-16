// 21 embed: store Decision embeddings as vecf32 (the type the vector index reads).
UNWIND $rows AS row
MATCH (d:Decision {id: row.id})
SET d.embedding = vecf32(row.vec)
