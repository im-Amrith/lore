// 01 load: Doc nodes (full text kept until M6 chunks it), (Person)-[:AUTHORED]->(Doc)
// for the last author. module is a property only: the plan has no Doc->Module edge.
UNWIND $rows AS row
MERGE (d:Doc {id: row.id})
SET d.path = row.path, d.repo = row.repo, d.title = row.title, d.text = row.text,
    d.updated_at = row.updated_at, d.url = row.url, d.module = row.module_id
WITH d, row
MATCH (a:Person {id: row.author_id})
MERGE (a)-[r:AUTHORED]->(d)
SET r.at = row.updated_at
