// 01 load: Team nodes from CODEOWNERS @org/team handles.
UNWIND $rows AS row
MERGE (t:Team {id: row.id})
SET t.name = row.name
