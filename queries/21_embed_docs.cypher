// 21 embed: docs to chunk (ingest/embed.py cuts Doc.text into DocChunk nodes).
MATCH (d:Doc)
WHERE d.text IS NOT NULL AND ($repo IS NULL OR d.repo = $repo)
RETURN d.id AS id, d.path AS path, d.title AS title, d.text AS text
