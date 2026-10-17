// 93 data version: a fingerprint of the knowledge in an org graph, for the Navigator's answer
// cache (an answer is reused only while this is unchanged). It changes when a load or sync adds
// PRs, issues, commits or decisions, when supersession changes a decision's status, and when
// a derive job rebuilds EXPERT_IN / CO_CHANGED (scores move). Memory nodes (User, Session,
// Question, Answer) are left out, so asking a question never invalidates the cache.
// M15: merged PRs (count, latest merge) and SUPERSEDES edges count too, so a sync that merges a PR
// or supersedes a decision always changes the version: no cached answer outlives a reversal.
MATCH (d:Decision)
WITH count(d) AS decisions, sum(CASE WHEN d.status = 'active' THEN 1 ELSE 0 END) AS active_decisions,
     max(d.valid_from) AS last_decision
OPTIONAL MATCH (p:PullRequest)
WITH decisions, active_decisions, last_decision, count(p) AS prs, max(p.created_at) AS last_pr,
     sum(CASE WHEN p.state = 'open' THEN 1 ELSE 0 END) AS open_prs,
     sum(CASE WHEN p.merged_at IS NOT NULL THEN 1 ELSE 0 END) AS merged_prs, max(p.merged_at) AS last_merge
OPTIONAL MATCH ()-[s:SUPERSEDES]->()
WITH decisions, active_decisions, last_decision, prs, last_pr, open_prs, merged_prs, last_merge,
     count(s) AS supersedes
OPTIONAL MATCH (i:Issue)
WITH decisions, active_decisions, last_decision, prs, last_pr, open_prs, merged_prs, last_merge,
     supersedes, count(i) AS issues,
     max(i.opened_at) AS last_issue
OPTIONAL MATCH (c:Commit)
WITH decisions, active_decisions, last_decision, prs, last_pr, open_prs, merged_prs, last_merge,
     supersedes, issues, last_issue,
     count(c) AS commits, max(c.at) AS last_commit
OPTIONAL MATCH ()-[e:EXPERT_IN]->()
WITH decisions, active_decisions, last_decision, prs, last_pr, open_prs, merged_prs, last_merge,
     supersedes, issues, last_issue, commits,
     last_commit, count(e) AS expert_edges, round(sum(e.score)) AS expert_score
OPTIONAL MATCH ()-[x:CO_CHANGED]->()
RETURN decisions, active_decisions, last_decision, prs, last_pr, open_prs, merged_prs, last_merge,
       supersedes, issues, last_issue,
       commits, last_commit, expert_edges, expert_score, count(x) AS co_changed_edges
