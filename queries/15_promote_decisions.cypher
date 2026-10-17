// 15 sync: a merged PR's decisions stop being proposals. Decisions extracted while the PR was open
// have status 'proposed'; on merge they become 'active' from the merge time. The decision node is
// kept (same id, same edges), so memory that cited the proposal still points at it.
UNWIND $pr_ids AS pid
MATCH (d:Decision)-[:DECIDED_IN]->(pr:PullRequest {id: pid})
WHERE pr.merged_at IS NOT NULL AND d.status = 'proposed'
SET d.status = 'active', d.valid_from = pr.merged_at, d.promoted_at = $now
RETURN d.id AS id, d.statement AS statement, pr.id AS source_id
