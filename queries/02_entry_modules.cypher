// 02 entry point, names: modules whose last path segment is one of the question's words
// ("parser" -> graph/src/parser). $terms are lowercased words, with a trailing 's' / 'es'
// also tried by the caller ("indexes" -> index). Modules have no text to embed, so this is
// a plain name match, most active module first (see 05_resolve_module); it lets find_entities hand back module ids for find_experts etc.
UNWIND $terms AS t
MATCH (m:Module)
WHERE (toLower(m.path) = t) OR (toLower(m.path) ENDS WITH ('/' + t))  // parentheses: see 05_resolve_module
WITH DISTINCT m, t
OPTIONAL MATCH (:Person)-[e:EXPERT_IN]->(m)
WITH m, t, sum(coalesce(e.score, 0.0)) AS activity
RETURN m.id AS id, m.path AS path, m.repo AS repo, t AS term, activity
ORDER BY activity DESC, size(m.path) ASC
LIMIT $limit
