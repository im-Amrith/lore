// 90 stats: node count per label.
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
