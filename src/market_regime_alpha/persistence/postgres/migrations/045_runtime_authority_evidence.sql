CREATE TABLE continuous_runtime_authority_evidence (
    evidence_id text PRIMARY KEY,
    evidence_hash text NOT NULL UNIQUE CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    run_id text NOT NULL,
    tick_id text NOT NULL,
    clock_mode text NOT NULL CHECK (clock_mode IN ('LIVE_TRUSTED', 'SIMULATED', 'UNKNOWN')),
    runtime_origin text NOT NULL CHECK (runtime_origin IN ('LIVE_ACQUISITION', 'REPLAY', 'FIXTURE', 'UNKNOWN')),
    clock_source text NOT NULL,
    origin_source text NOT NULL,
    observed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    code_revision text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'runtime-authority-evidence/v1'
    ),
    UNIQUE (run_id, tick_id),
    FOREIGN KEY (run_id, tick_id)
        REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    CHECK (recorded_at >= observed_at)
);

ALTER TABLE prospective_evidence_attestation
    ADD COLUMN runtime_authority_evidence_id text
        REFERENCES continuous_runtime_authority_evidence(evidence_id) ON DELETE RESTRICT;

CREATE INDEX continuous_runtime_authority_evidence_tick_idx
ON continuous_runtime_authority_evidence(run_id, tick_id);
CREATE INDEX prospective_attestation_runtime_authority_idx
ON prospective_evidence_attestation(runtime_authority_evidence_id);

CREATE TRIGGER continuous_runtime_authority_evidence_no_update
BEFORE UPDATE ON continuous_runtime_authority_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER continuous_runtime_authority_evidence_no_delete
BEFORE DELETE ON continuous_runtime_authority_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
