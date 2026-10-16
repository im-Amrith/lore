// 08 F10 working groups: label propagation (community detection) on COLLABORATES_STRONG
// (repeat collaborators only; see 08_collaborates_strong for why not plain COLLABORATES).
// Each person starts with their own label and repeatedly adopts the most common label among
// their neighbours, so people who review each other end up in one group.
// Groups of one (isolated people, bots) are dropped.
CALL algo.labelPropagation({nodeLabels: ['Person'], relationshipTypes: ['COLLABORATES_STRONG']})
YIELD node, communityId
WITH communityId, collect(coalesce(node.login, node.name)) AS members, collect(node.id) AS member_ids,
     count(*) AS size
WHERE size >= 2
RETURN communityId AS group_id, size, members, member_ids
ORDER BY size DESC
