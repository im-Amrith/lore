// 04 derive: combine the two parts into score, and last_touch = latest authored or reviewed touch.
// evidence = commits + reviewed PRs behind the score; at = when this was derived.
// $modules: module ids to recompute (a sync touched them), or null for the whole graph.
MATCH ()-[e:EXPERT_IN]->(m:Module)
WHERE $modules IS NULL OR m.id IN $modules
WITH e, coalesce(e.last_authored, 0) AS la, coalesce(e.last_reviewed, 0) AS lr
SET e.score = coalesce(e.authored, 0.0) + coalesce(e.reviewed, 0.0),
    e.last_touch = CASE WHEN la >= lr THEN la ELSE lr END,
    e.evidence = coalesce(e.commits, 0) + coalesce(e.reviews, 0),
    e.at = $now
RETURN count(e) AS edges
