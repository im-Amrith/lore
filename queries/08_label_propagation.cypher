// 08 F10 working groups: label propagation (community detection) on COLLABORATES.
// Each person starts with their own label and repeatedly adopts the most common label among
// their neighbours, so people who review each other end up in one group.
// Groups of one (isolated people, bots) are dropped.
CALL algo.labelPropagation({nodeLabels: ['Person'], relationshipTypes: ['COLLABORATES']})
YIELD node, communityId
WITH communityId, collect(coalesce(node.login, node.name)) AS members, count(*) AS size
WHERE size >= 2
RETURN communityId AS group_id, size, members
ORDER BY size DESC
