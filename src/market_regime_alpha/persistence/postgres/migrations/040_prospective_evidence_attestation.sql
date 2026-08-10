CREATE TABLE prospective_evidence_attestation (
    attestation_id text PRIMARY KEY,
    attestation_hash text NOT NULL UNIQUE CHECK (attestation_hash ~ '^sha256:[0-9a-f]{64}$'),
    shadow_decision_id text NOT NULL REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    outcome_settlement_id text NOT NULL REFERENCES prospective_outcome_settlement(settlement_id) ON DELETE RESTRICT,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('ENGINEERING_ATTESTABLE', 'INELIGIBLE')),
    clock_mode text NOT NULL CHECK (clock_mode IN ('LIVE_TRUSTED', 'SIMULATED', 'UNKNOWN')),
    runtime_origin text NOT NULL CHECK (runtime_origin IN ('LIVE_ACQUISITION', 'REPLAY', 'FIXTURE', 'UNKNOWN')),
    prospective_proven boolean NOT NULL DEFAULT false CHECK (NOT prospective_proven),
    decision_frozen_at timestamptz NOT NULL,
    outcome_available_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->'authority'->>'prospective_proven' = 'false'
    ),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT,
    UNIQUE (shadow_decision_id, outcome_settlement_id, clock_mode, runtime_origin)
);

CREATE INDEX prospective_attestation_decision_idx
ON prospective_evidence_attestation(shadow_decision_id, status);
CREATE INDEX prospective_attestation_outcome_idx
ON prospective_evidence_attestation(outcome_settlement_id);
CREATE INDEX prospective_attestation_tick_idx
ON prospective_evidence_attestation(run_id, tick_id);

CREATE TRIGGER prospective_evidence_attestation_no_update
BEFORE UPDATE ON prospective_evidence_attestation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER prospective_evidence_attestation_no_delete
BEFORE DELETE ON prospective_evidence_attestation
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
