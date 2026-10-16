// 11 F6 memory write (the remember tool): one question and its answer, scoped by user.
//   (User)-[:HAD]->(Session)-[:ASKED]->(Question)-[:ANSWERED_WITH]->(Answer)-[:CITED]->(k)
// User and Session are MERGEd (a session spans several questions); Question and Answer are
// new nodes each time. CITED targets are looked up per label by id (indexed lookups instead
// of a label-free scan); ids that match nothing are skipped and the count says how many hit.
// CITED.at = the answer time, so query 11 can ask what changed after it.
MERGE (u:User {id: $user_id})
MERGE (s:Session {id: $session_id})
ON CREATE SET s.started_at = $now
MERGE (u)-[:HAD]->(s)
CREATE (q:Question {id: $question_id, text: $question, intent: $intent, at: $now})
CREATE (a:Answer {id: $answer_id, text: $answer, cypher: $cypher, at: $now})
CREATE (s)-[:ASKED {at: $now}]->(q)
CREATE (q)-[:ANSWERED_WITH {at: $now}]->(a)
WITH a
UNWIND $cited AS cid
OPTIONAL MATCH (n1:Decision {id: cid})
OPTIONAL MATCH (n2:PullRequest {id: cid})
OPTIONAL MATCH (n3:Issue {id: cid})
OPTIONAL MATCH (n4:Person {id: cid})
OPTIONAL MATCH (n5:Module {id: cid})
OPTIONAL MATCH (n6:Doc {id: cid})
OPTIONAL MATCH (n7:Commit {id: cid})
OPTIONAL MATCH (n8:Team {id: cid})
OPTIONAL MATCH (n9:DocChunk {id: cid})
WITH a, coalesce(n1, n2, n3, n4, n5, n6, n7, n8, n9) AS k
WHERE k IS NOT NULL
MERGE (a)-[c:CITED]->(k)
SET c.at = a.at
RETURN a.id AS answer_id, count(k) AS cited
