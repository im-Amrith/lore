// 08 F4 bridge people: betweenness centrality on the COLLABORATES graph.
// High score = many shortest author/reviewer paths run through this person, so their
// departure would split the contributor network. samplingSeed is fixed so repeated runs
// (and the demo) give the same ranking; samplingSize caps the source nodes sampled.
CALL algo.betweenness({nodeLabels: ['Person'], relationshipTypes: ['COLLABORATES'],
                       samplingSize: $sampling_size, samplingSeed: $seed})
YIELD node, score
WHERE score > 0
RETURN coalesce(node.login, node.name) AS person, node.id AS id, score
ORDER BY score DESC
LIMIT $limit
