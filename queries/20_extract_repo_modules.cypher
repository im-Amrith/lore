// 20 extract: every module of a repo, for matching folder names mentioned in doc text.
MATCH (m:Module)-[:PART_OF]->(:Repo {id: 'repo:' + $repo})
RETURN m.id AS id, m.path AS path
ORDER BY path
