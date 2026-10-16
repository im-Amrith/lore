// 01 load: Topic nodes from the org's fixed topic list (docs/TOPICS.md).
UNWIND $rows AS row
MERGE (t:Topic {name: row.name})
SET t.covers = row.covers
