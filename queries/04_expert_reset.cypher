// 04 derive: drop every EXPERT_IN edge before recomputing, so a person whose
// activity aged out (or a newly skipped bulk commit) leaves no stale edge behind.
MATCH ()-[e:EXPERT_IN]->()
DELETE e
RETURN count(e) AS deleted
