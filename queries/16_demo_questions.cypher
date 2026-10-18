// 16 demo reset (scripts/demo_reset.py): a user's questions, oldest first, so the script can pick
// which to keep (the pre-merge "why Redis" question) before 16_demo_forget deletes the rest.
MATCH (:User {id: $user_id})-[:HAD]->(:Session)-[:ASKED]->(q:Question)
RETURN q.id AS question_id, q.text AS question, q.at AS at
ORDER BY at ASC
