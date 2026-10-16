// 08 derive: drop every COLLABORATES edge before recomputing (same pattern as 04_expert_reset).
MATCH ()-[c:COLLABORATES]->()
DELETE c
RETURN count(c) AS deleted
