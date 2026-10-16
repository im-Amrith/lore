// 02 entry point, step 1: the starting Decision for a "why" question, vector + full-text.
// Decisions are searched before docs, PRs and issues (02_entry_docs/prs/issues).
//
// Scores: the vector score is a cosine DISTANCE (1 - cosine similarity, 0..2, lower = closer;
// checked on FalkorDB with identical, orthogonal and opposite vectors -> 0, 1, 2), and rows
// come back nearest first. Full-text is a TF-IDF score, higher = better, sorted DESC here.
// The scales differ, so ranks are fused, not scores: weighted reciprocal rank fusion (RRF)
//   rank = (1/($rrf_k + vector_rank) + $text_weight/($rrf_k + text_rank)) * kind weight
// over the vector top $k (20) and the full-text top $text_k (3), $text_weight 0.5, $rrf_k 60.
// A list the node is missing from adds 0. Kind weight: parity = 0.5 (config). Decisions
// below $min_confidence (0.6) are never a starting node.
//
// $q_text holds only the question's specific terms (identifiers like graphblas.sh or
// all_nodes_matrix, acronyms like MVCC; see search.fulltext_query), or a token that
// matches nothing, in which case the vector ranks alone decide. Measured on q01-q04 + s01:
// an OR of all words, text top 20 -> ranks 2,6,6,1,1 (noise sitting in both lists beats the
// vector's clear first hit); same, text top 3 -> 2,2,2,1,1; specific terms, text top 3
// -> 1,1,2,1,1 (+ ADR 0001 rank 2 for s01).
//
// The full-text list is collected first with no grouping key, so it is one row even when
// it matched nothing; the vector query always returns rows once embeddings exist.
CALL db.idx.fulltext.queryNodes('Decision', $q_text) YIELD node, score
WITH node, score ORDER BY score DESC LIMIT $text_k
WITH collect({n: node, s: score}) AS text_hits
CALL db.idx.vector.queryNodes('Decision', 'embedding', $k, vecf32($q_vec)) YIELD node, score
WITH text_hits, node, score ORDER BY score ASC
WITH text_hits, collect({n: node, s: score}) AS vec_hits
UNWIND [h IN vec_hits | h.n] + [h IN text_hits | h.n] AS d
WITH DISTINCT d, vec_hits, text_hits
WHERE d.confidence >= $min_confidence
WITH d,
     [i IN range(0, size(vec_hits) - 1) WHERE vec_hits[i].n = d | i + 1][0] AS vec_rank,
     [i IN range(0, size(text_hits) - 1) WHERE text_hits[i].n = d | i + 1][0] AS text_rank,
     [h IN vec_hits WHERE h.n = d | h.s][0] AS distance
WITH d, vec_rank, text_rank, distance,
     (CASE WHEN vec_rank IS NULL THEN 0.0 ELSE 1.0 / ($rrf_k + vec_rank) END +
      CASE WHEN text_rank IS NULL THEN 0.0 ELSE $text_weight / ($rrf_k + text_rank) END)
       * coalesce(d.weight, 1.0) AS rank
OPTIONAL MATCH (d)-[:DECIDED_IN]->(src)
RETURN d.id AS id, d.statement AS statement, d.kind AS kind, d.status AS status,
       d.confidence AS confidence, collect(src.id) AS sources,
       vec_rank, text_rank, distance, rank
ORDER BY rank DESC
LIMIT $limit
