// 01 load: clear (Commit)-[:PART_OF]->(PullRequest) for the commits being loaded, so a
// reload drops links the loader no longer derives (e.g. a wrong PR-number match).
// Runs right before 01_load_part_of; rows are commit rows (row.id).
UNWIND $rows AS row
MATCH (c:Commit {id: row.id})-[old:PART_OF]->(:PullRequest)
DELETE old
