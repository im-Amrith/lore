// 07 F4 knowledge risk per module: bus factor = number of people who could maintain it.
// Tuned against the golden set (q09, s03); the plan's rule (score >= 1.0, touched in 180 days)
// gave graph/src/parser 3 and graph/src/udf 2, because reviews alone (Dvir's 4.5 on parser)
// and two stray commits (gkorland's 1.3) cleared the bar. A person counts here when:
//   - authored >= $min_score (0.9, about one commit this week): they wrote code there;
//     reviewing alone doesn't make you a maintainer
//   - authored >= $min_share (0.10) of the module's total authored score: a real share,
//     not a drive-by fix
//   - last_authored within $window seconds (180 days)
// Values live in config.py (BUS_FACTOR_*).
// $repo (repo name, or '' for all) limits the list to one repo's modules (Module.repo).
// Modules whose total authored score is 0 (only bots or bulk commits) are left out.
// Order: single points of failure first (1, 2, ...), then dormant modules (bus_factor 0:
// nobody has authored a real share in the window) at the end, so tiny old modules don't
// crowd out the risk list.
MATCH (m:Module)
WHERE $repo = '' OR m.repo = $repo
OPTIONAL MATCH (:Person)-[x:EXPERT_IN]->(m)
WITH m, sum(coalesce(x.authored, 0.0)) AS total
WHERE total > 0
OPTIONAL MATCH (p:Person)-[e:EXPERT_IN]->(m)
WHERE e.authored >= $min_score AND e.authored >= $min_share * total
  AND e.last_authored > $now - $window
WITH m, total, p, e ORDER BY e.authored DESC
WITH m, total,
     collect(coalesce(p.login, p.name)) AS experts, collect(p.id) AS expert_ids,
     collect(round(100.0 * e.authored / total)) AS shares
RETURN m.id AS module_id, m.path AS module, size(experts) AS bus_factor, experts, expert_ids,
       shares AS share_pct, total AS total_score
ORDER BY CASE WHEN bus_factor = 0 THEN 1 ELSE 0 END, bus_factor ASC, total_score DESC
