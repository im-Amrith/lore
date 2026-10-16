// 21 embed: text to embed per Issue: title + the start of the body (cut in Python).
MATCH (i:Issue)
RETURN i.id AS id, i.title AS title, i.body AS body
