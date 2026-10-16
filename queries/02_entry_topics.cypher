// 02 entry point, names: topics (docs/TOPICS.md ids) whose every hyphen-separated part is one
// of the question's words: "Why do we cache links in Redis?" -> link-cache (words link, cache).
// $terms are lowercased words plus de-pluralised forms (links -> link), from the caller.
MATCH (topic:Topic)
WHERE all(part IN split(topic.name, '-') WHERE part IN $terms)
RETURN topic.name AS name, topic.covers AS covers
ORDER BY size(split(topic.name, '-')) DESC
LIMIT $limit
