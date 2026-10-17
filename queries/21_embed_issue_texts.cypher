// 21 embed: text to embed per Issue: title + the start of the body (cut in Python).
// $missing = true: only issues with no embedding yet; false: all.
MATCH (i:Issue)
WHERE NOT $missing OR i.embedding IS NULL
RETURN i.id AS id, i.title AS title, i.body AS body
