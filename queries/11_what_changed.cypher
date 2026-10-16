// 11 F6 what changed since I last asked: nodes this user's answers CITED that something newer
// has since SUPERSEDED or REFERENCED (edge at > the answer's at). The plan's query 11, plus
// the $topic filter of 11_recall_questions and the urls an answer needs.
MATCH (:User {id: $user_id})-[:HAD]->(:Session)-[:ASKED]->(q:Question)
      -[:ANSWERED_WITH]->(a:Answer)-[:CITED]->(k)
OPTIONAL MATCH (k)-[:ABOUT]->(t:Topic {name: $topic})
WITH q, a, k, count(t) AS on_topic
WHERE $topic = '' OR toLower(q.text) CONTAINS $topic OR on_topic > 0
MATCH (newer)-[r:SUPERSEDES|REFERENCES]->(k)
WHERE r.at > a.at
RETURN q.text AS question, a.at AS asked_at, k.id AS cited_id,
       newer.id AS newer_id, labels(newer)[0] AS newer_label,
       coalesce(newer.title, newer.statement) AS newer_title,
       coalesce(newer.url, newer.source_url) AS newer_url,
       type(r) AS change, r.at AS changed_at
ORDER BY changed_at DESC
LIMIT $limit
