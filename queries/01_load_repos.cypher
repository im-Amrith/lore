// 01 load: Repo nodes.
UNWIND $rows AS row
MERGE (r:Repo {id: row.id})
SET r.name = row.name, r.full_name = row.full_name, r.description = row.description, r.url = row.url
