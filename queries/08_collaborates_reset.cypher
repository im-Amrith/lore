// 08 derive: drop every COLLABORATES and COLLABORATES_STRONG edge before recomputing
// (same pattern as 04_expert_reset).
MATCH ()-[c:COLLABORATES|COLLABORATES_STRONG]->()
DELETE c
RETURN count(c) AS deleted
