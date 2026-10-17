// 15 sync: the graph's view of some PRs (is the merge already loaded?). $ids = PR ids.
UNWIND $ids AS pid
OPTIONAL MATCH (p:PullRequest {id: pid})
RETURN pid AS id, p.state AS state, p.merged_at AS merged_at
