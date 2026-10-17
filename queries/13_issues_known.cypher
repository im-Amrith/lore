// 13 Librarian intake: which of these issue ids are already in the graph (with an embedding).
UNWIND $ids AS iid
MATCH (i:Issue {id: iid})
RETURN i.id AS id, i.embedding IS NOT NULL AS embedded
