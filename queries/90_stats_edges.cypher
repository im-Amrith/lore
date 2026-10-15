// 90 stats: relationship count per type.
MATCH ()-[r]->()
RETURN type(r) AS type, count(r) AS count
ORDER BY count DESC
