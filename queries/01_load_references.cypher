// 01 load: (PullRequest|Issue|Comment|Doc)-[:REFERENCES]->(PullRequest|Issue|Commit|Doc),
// from #123, owner/repo#123, GitHub URLs, known commit SHAs and doc paths in text.
// Each end can have several labels; indexed OPTIONAL MATCHes + coalesce pick the one that exists.
UNWIND $rows AS row
OPTIONAL MATCH (s1:PullRequest {id: row.src_id})
OPTIONAL MATCH (s2:Issue {id: row.src_id})
OPTIONAL MATCH (s3:Comment {id: row.src_id})
OPTIONAL MATCH (s4:Doc {id: row.src_id})
WITH row, coalesce(s1, s2, s3, s4) AS src
WHERE src IS NOT NULL
OPTIONAL MATCH (d1:PullRequest {id: row.dst_id})
OPTIONAL MATCH (d2:Issue {id: row.dst_id})
OPTIONAL MATCH (d3:Commit {id: row.dst_id})
OPTIONAL MATCH (d4:Doc {id: row.dst_id})
WITH row, src, coalesce(d1, d2, d3, d4) AS dst
WHERE dst IS NOT NULL
MERGE (src)-[r:REFERENCES]->(dst)
SET r.at = row.at
