// 15 supersession: a newly active decision, as the LLM judge sees it.
MATCH (d:Decision {id: $id})
RETURN d.id AS id, d.statement AS statement, d.rationale AS rationale, d.alternatives AS alternatives,
       d.source_id AS source_id, d.valid_from AS valid_from
