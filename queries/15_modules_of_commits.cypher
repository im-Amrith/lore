// 15 sync: the modules some commits touch (what the derive jobs recompute).
UNWIND $ids AS cid
MATCH (:Commit {id: cid})-[:TOUCHES]->(m:Module)
RETURN DISTINCT m.id AS id
