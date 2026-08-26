-- Allow immutable correctness re-analysis after a code correction without
-- overwriting or relabelling the predecessor failure index.

ALTER TABLE alpha_correctness_failure_index
DROP CONSTRAINT alpha_correctness_failure_ind_source_run_id_source_evidence_key;

ALTER TABLE alpha_correctness_failure_index
ADD CONSTRAINT alpha_correctness_failure_index_source_revision_key
UNIQUE (
    source_run_id,
    source_evidence_id,
    semantic_revision,
    analysis_code_sha
);

COMMENT ON CONSTRAINT alpha_correctness_failure_index_source_revision_key
ON alpha_correctness_failure_index IS
'One append-only failure index per predecessor Evidence, Target semantic revision and exact analysis code SHA.';
