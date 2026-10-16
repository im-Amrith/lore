// 03 F1 why-trace: the lineage of a decision. $node_id is a Decision id, or the id of the
// PR / issue / doc it was decided in (Decision.source_id), which returns every decision there.
// Per decision:
//   sources    DECIDED_IN targets (PR, issue, doc) with their urls
//   issues     issues those sources CLOSE or REFERENCE (the problem the decision answered)
//   people     PROPOSED (source author) / APPROVED (approving reviewers)
//   modules    AFFECTS targets
//   history    older decisions this one SUPERSEDES (up to 5 hops)
//   newer      decisions that SUPERSEDE this one (if any, this one is no longer current)
//   proposals  status 'proposed' decisions (open or draft PRs) that AFFECT one of the same
//              modules AND are ABOUT one of the same topics: an open PR that would change
//              this decision. Sandbox: draft PR #16 (in-process LRU) vs PR #11 (Redis).
//              If this decision is itself proposed, the same match finds the active ones it
//              would replace.
// Decisions below $min_confidence are left out at every step. Each OPTIONAL MATCH stage is
// collected before the next, so rows don't multiply.
MATCH (d:Decision)
WHERE (d.id = $node_id OR d.source_id = $node_id) AND d.confidence >= $min_confidence
OPTIONAL MATCH (d)-[:DECIDED_IN]->(src)
WITH d, collect(DISTINCT {id: src.id, label: labels(src)[0], number: src.number,
                          title: coalesce(src.title, src.path), url: src.url}) AS sources,
     collect(DISTINCT src) AS src_nodes
UNWIND (CASE WHEN size(src_nodes) = 0 THEN [null] ELSE src_nodes END) AS s
OPTIONAL MATCH (s)-[ir:CLOSES|REFERENCES]->(issue:Issue)
WITH d, sources, collect(DISTINCT {id: issue.id, number: issue.number, title: issue.title,
                                   url: issue.url, via: s.id, rel: type(ir)}) AS issues
OPTIONAL MATCH (p:Person)-[pr:PROPOSED|APPROVED]->(d)
WITH d, sources, issues,
     collect(DISTINCT {id: p.id, login: coalesce(p.login, p.name), role: type(pr)}) AS people
OPTIONAL MATCH (d)-[:AFFECTS]->(m:Module)
WITH d, sources, issues, people, collect(DISTINCT m) AS mods
OPTIONAL MATCH (d)-[:SUPERSEDES*1..5]->(older:Decision)
WHERE older.confidence >= $min_confidence
WITH d, sources, issues, people, mods,
     collect(DISTINCT {id: older.id, statement: older.statement, status: older.status,
                       kind: older.kind, source_id: older.source_id, source_url: older.source_url,
                       valid_to: older.valid_to}) AS history
OPTIONAL MATCH (newer:Decision)-[:SUPERSEDES*1..5]->(d)
WHERE newer.confidence >= $min_confidence
WITH d, sources, issues, people, mods, history,
     collect(DISTINCT {id: newer.id, statement: newer.statement, status: newer.status,
                       source_id: newer.source_id, source_url: newer.source_url}) AS newer
OPTIONAL MATCH (d)-[:ABOUT]->(t:Topic)<-[:ABOUT]-(other:Decision)-[:AFFECTS]->(om:Module)
WHERE other <> d AND om IN mods AND other.confidence >= $min_confidence
  AND (other.status = 'proposed') <> (d.status = 'proposed')
  AND (other.status = 'active' OR other.status = 'proposed')
OPTIONAL MATCH (other)-[:DECIDED_IN]->(osrc)
WITH d, sources, issues, people, mods, history, newer, other, osrc, om, t
WITH d, sources, issues, people, mods, history, newer, other,
     collect(DISTINCT coalesce(osrc.is_draft, false))[0] AS source_draft,
     collect(DISTINCT osrc.state)[0] AS source_state,
     collect(DISTINCT om.id) AS shared_modules, collect(DISTINCT t.name) AS shared_topics
WITH d, sources, issues, people, mods, history, newer,
     collect(CASE WHEN other IS NULL THEN null ELSE {
       id: other.id, statement: other.statement, status: other.status, kind: other.kind,
       source_id: other.source_id, source_url: other.source_url,
       source_draft: source_draft, source_state: source_state, shared_modules: shared_modules, shared_topics: shared_topics} END) AS rivals
RETURN d.id AS id, d.statement AS statement, d.rationale AS rationale,
       d.alternatives AS alternatives, d.quote AS quote, d.status AS status, d.kind AS kind,
       d.confidence AS confidence, d.valid_from AS valid_from, d.valid_to AS valid_to,
       d.source_id AS source_id, d.source_url AS source_url,
       [x IN sources WHERE x.id IS NOT NULL] AS sources,
       [x IN issues WHERE x.id IS NOT NULL] AS issues,
       [x IN people WHERE x.id IS NOT NULL] AS people,
       [m IN mods | m.id] AS modules,
       [x IN history WHERE x.id IS NOT NULL] AS history,
       [x IN newer WHERE x.id IS NOT NULL] AS newer,
       rivals
ORDER BY d.valid_from DESC
