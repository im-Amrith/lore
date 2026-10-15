// 00 healthcheck: create (or refresh) a single test node and return it.
// Runs against the separate lore_healthcheck graph, never an org graph.
MERGE (h:Healthcheck {id: 'healthcheck'})
SET h.at = $now
RETURN h.id AS id, h.at AS at
