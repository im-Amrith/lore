// 09 helper: the title and body of an issue already in the graph, so related_work can embed
// it the same way stored issues are embedded, and post_triage can check the issue exists.
MATCH (i:Issue {id: $issue_id})
RETURN i.id AS id, i.number AS number, i.repo AS repo, i.title AS title, i.body AS body,
       i.state AS state, i.url AS url
