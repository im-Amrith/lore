// 08 most relied-on reviewers: PageRank over COLLABORATES (author -> reviewer).
// FalkorDB's algo.pageRank is unweighted, so one review counts like twenty; the weight
// is returned beside the score so the two can be compared.
// People with no COLLABORATES edge (bots, drive-by authors) only get the base score; they
// are filtered out so the list is about the review network.
CALL algo.pageRank('Person', 'COLLABORATES')
YIELD node, score
WHERE (node)-[:COLLABORATES]-()
OPTIONAL MATCH (:Person)-[in:COLLABORATES]->(node)
WITH node, score, count(in) AS authors, sum(coalesce(in.weight, 0)) AS reviews
RETURN coalesce(node.login, node.name) AS person, node.id AS id, score,
       authors AS authors_reviewed, reviews AS prs_reviewed
ORDER BY score DESC
LIMIT $limit
