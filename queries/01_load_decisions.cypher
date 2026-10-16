// 01 load: Decision nodes and (Decision)-[:DECIDED_IN]->(PullRequest|Issue|Doc).
// confidence is the value answers filter on (DECISION_MIN_CONFIDENCE): the LLM's own score
// (llm_confidence), capped at 0.5 when the quote couldn't be found in the source text.
// status: 'active' for merged PRs, closed issues and docs; 'proposed' for open or draft PRs,
// which aren't decided yet (sandbox PR #16 until the demo merges it).
// kind: architecture | behavior | process | parity ("test" is dropped before loading);
// weight ranks parity below the rest (DECISION_KIND_WEIGHT).
// The source can have any of three labels; three indexed OPTIONAL MATCHes avoid a label-free scan.
UNWIND $rows AS row
MERGE (d:Decision {id: row.id})
SET d.statement = row.statement, d.kind = row.kind, d.weight = row.weight,
    d.rationale = row.rationale, d.alternatives = row.alternatives,
    d.status = row.status, d.valid_from = row.valid_from, d.valid_to = null,
    d.confidence = row.confidence, d.llm_confidence = row.llm_confidence,
    d.quote = row.quote, d.quote_verified = row.quote_verified,
    d.source_id = row.source_id, d.source_url = row.source_url,
    d.model = row.model, d.extracted_at = row.extracted_at
WITH d, row
OPTIONAL MATCH (pr:PullRequest {id: row.source_id})
OPTIONAL MATCH (i:Issue {id: row.source_id})
OPTIONAL MATCH (doc:Doc {id: row.source_id})
WITH d, row, coalesce(pr, i, doc) AS src
WHERE src IS NOT NULL
MERGE (d)-[r:DECIDED_IN]->(src)
SET r.at = row.valid_from
