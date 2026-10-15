// 01 load: Module nodes, each PART_OF its Repo.
UNWIND $rows AS row
MERGE (m:Module {id: row.id})
SET m.path = row.path, m.repo = row.repo
WITH m, row
MATCH (r:Repo {id: row.repo_id})
MERGE (m)-[:PART_OF]->(r)
