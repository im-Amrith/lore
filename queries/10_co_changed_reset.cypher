// 10 derive: drop every CO_CHANGED edge before recomputing.
MATCH ()-[r:CO_CHANGED]->()
DELETE r
RETURN count(r) AS deleted
