// 02 entry point, step 3: pull requests by full-text on title and body (TF-IDF score,
// higher = better). Used after decisions, when no decision answers the question.
CALL db.idx.fulltext.queryNodes('PullRequest', $q_text) YIELD node, score
RETURN node.id AS id, node.number AS number, node.title AS title, node.url AS url, score
ORDER BY score DESC
LIMIT $limit
