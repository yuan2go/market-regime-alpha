ALTER TABLE state_research_stage_authority
ADD COLUMN data_eligibility text CHECK (
    data_eligibility IN ('UNQUALIFIED', 'EXPLORATORY', 'REHEARSAL', 'FORMAL_RESEARCH')
);

ALTER TABLE decision_replay_import
DROP CONSTRAINT decision_replay_import_artifact_kind_check;
ALTER TABLE decision_replay_import
ADD CONSTRAINT decision_replay_import_artifact_kind_check CHECK (
    artifact_kind IN (
        'RUNTIME_INPUT', 'MODEL_GOVERNANCE', 'MANUAL_OBSERVATION',
        'FILL_AUTHORITY', 'RECONCILIATION', 'PREVIEW_SUMMARY',
        'PORTFOLIO_PROPOSAL', 'RISK_DECISION', 'TERMINAL_SUMMARY',
        'RUNTIME_RECEIPT', 'RISK_CONFIGURATION',
        'RECONCILIATION_TOLERANCE', 'SETTLEMENT_EVIDENCE'
    )
);

CREATE TABLE model_governance_action (
    governance_revision bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    action_type text NOT NULL CHECK (action_type IN (
        'MODEL_REGISTER', 'MODEL_LIFECYCLE_TRANSITION',
        'MODEL_VERSION_LINEAGE', 'QUALIFICATION_EVIDENCE',
        'GOVERNANCE_POLICY', 'QUALIFICATION_DECISION',
        'RUNTIME_ASSIGNMENT', 'RUNTIME_CHAMPION_REPLACEMENT'
    )),
    aggregate_id text NOT NULL,
    action_hash text NOT NULL CHECK (action_hash ~ '^sha256:[0-9a-f]{64}$'),
    actor text NOT NULL,
    reason text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    created_at timestamptz NOT NULL
);

INSERT INTO model_governance_action(
    idempotency_key, action_type, aggregate_id, action_hash,
    actor, reason, payload_json, created_at
)
SELECT
    idempotency_key,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM model_lifecycle_transitions AS transition
            WHERE transition.idempotency_key = governance_commands.idempotency_key
        ) THEN 'MODEL_LIFECYCLE_TRANSITION'
        ELSE 'MODEL_REGISTER'
    END,
    aggregate_id,
    payload_hash,
    'LEGACY_GOVERNANCE_MIGRATION',
    'Backfilled from PostgreSQL Model Registry command authority',
    jsonb_build_object(
        'schema_version', 'legacy-model-governance-command/v1',
        'aggregate_type', aggregate_type,
        'aggregate_id', aggregate_id,
        'result_version', result_version,
        'payload_hash', payload_hash
    ),
    created_at
FROM governance_commands
WHERE aggregate_type = 'MODEL'
ORDER BY created_at, idempotency_key;

CREATE TABLE model_version_lineage (
    lineage_id text PRIMARY KEY,
    lineage_hash text NOT NULL UNIQUE
        CHECK (lineage_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_id text NOT NULL REFERENCES model_registrations(model_id),
    definition_hash text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    governance_revision bigint NOT NULL UNIQUE
        REFERENCES model_governance_action(governance_revision),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-version-lineage-v1'
    ),
    created_at timestamptz NOT NULL,
    UNIQUE (model_id, definition_hash)
);
CREATE INDEX model_version_lineage_model_idx ON model_version_lineage(model_id);

CREATE TABLE model_qualification_evidence (
    evidence_id text PRIMARY KEY,
    evidence_hash text NOT NULL UNIQUE
        CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_id text NOT NULL REFERENCES model_registrations(model_id),
    lineage_id text NOT NULL REFERENCES model_version_lineage(lineage_id),
    evidence_kind text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('SATISFIED', 'FAILED', 'REVOKED')),
    governance_revision bigint NOT NULL UNIQUE
        REFERENCES model_governance_action(governance_revision),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-qualification-evidence-v1'
    ),
    available_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    CHECK (available_at <= recorded_at)
);
CREATE INDEX model_qualification_evidence_model_idx
ON model_qualification_evidence(model_id);
CREATE INDEX model_qualification_evidence_lineage_idx
ON model_qualification_evidence(lineage_id);

CREATE TABLE model_governance_policy (
    policy_id text PRIMARY KEY,
    policy_hash text NOT NULL UNIQUE
        CHECK (policy_hash ~ '^sha256:[0-9a-f]{64}$'),
    purpose text NOT NULL CHECK (purpose IN (
        'RESEARCH', 'BACKTEST', 'SHADOW', 'PRODUCTION_DECISION'
    )),
    production_authorization boolean NOT NULL,
    governance_revision bigint NOT NULL UNIQUE
        REFERENCES model_governance_action(governance_revision),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-governance-policy-v1'
    ),
    created_at timestamptz NOT NULL,
    CHECK (production_authorization = (purpose = 'PRODUCTION_DECISION'))
);

CREATE TABLE model_qualification_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE
        CHECK (decision_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_id text NOT NULL REFERENCES model_registrations(model_id),
    lineage_id text NOT NULL REFERENCES model_version_lineage(lineage_id),
    policy_id text NOT NULL REFERENCES model_governance_policy(policy_id),
    purpose text NOT NULL CHECK (purpose IN (
        'RESEARCH', 'BACKTEST', 'SHADOW', 'PRODUCTION_DECISION'
    )),
    qualification_status text NOT NULL CHECK (
        qualification_status IN ('QUALIFIED', 'NOT_QUALIFIED')
    ),
    production_authorized boolean NOT NULL,
    registry_version bigint NOT NULL CHECK (registry_version >= 0),
    governance_revision bigint NOT NULL UNIQUE
        REFERENCES model_governance_action(governance_revision),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-qualification-decision-v1'
    ),
    decided_at timestamptz NOT NULL
);
CREATE INDEX model_qualification_decision_model_idx
ON model_qualification_decision(model_id);
CREATE INDEX model_qualification_decision_lineage_idx
ON model_qualification_decision(lineage_id);
CREATE INDEX model_qualification_decision_policy_idx
ON model_qualification_decision(policy_id);
CREATE INDEX model_qualification_lookup_idx
ON model_qualification_decision(model_id, policy_id, governance_revision DESC);

CREATE TABLE model_runtime_lineage (
    runtime_lineage_id text PRIMARY KEY,
    runtime_lineage_hash text NOT NULL UNIQUE
        CHECK (runtime_lineage_hash ~ '^sha256:[0-9a-f]{64}$'),
    model_id text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'runtime-model-lineage-v1'
    ),
    recorded_at timestamptz NOT NULL
);
CREATE INDEX model_runtime_lineage_model_idx ON model_runtime_lineage(model_id);

CREATE TABLE model_runtime_assignment (
    assignment_id text PRIMARY KEY,
    assignment_hash text NOT NULL UNIQUE
        CHECK (assignment_hash ~ '^sha256:[0-9a-f]{64}$'),
    runtime_scope text NOT NULL,
    model_slot text NOT NULL,
    purpose text NOT NULL CHECK (purpose IN (
        'RESEARCH', 'BACKTEST', 'SHADOW', 'PRODUCTION_DECISION'
    )),
    lane text NOT NULL CHECK (lane IN ('CHAMPION', 'CHALLENGER')),
    assignment_status text NOT NULL CHECK (
        assignment_status IN ('ACTIVE', 'SUSPENDED', 'REPLACED')
    ),
    model_id text NOT NULL REFERENCES model_registrations(model_id),
    policy_id text NOT NULL REFERENCES model_governance_policy(policy_id),
    version bigint NOT NULL CHECK (version >= 0),
    supersedes_assignment_id text REFERENCES model_runtime_assignment(assignment_id),
    governance_revision bigint NOT NULL UNIQUE
        REFERENCES model_governance_action(governance_revision),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-runtime-assignment-v1'
    ),
    effective_at timestamptz NOT NULL,
    UNIQUE (runtime_scope, model_slot, purpose, lane, model_id, version)
);
CREATE INDEX model_runtime_assignment_model_idx ON model_runtime_assignment(model_id);
CREATE INDEX model_runtime_assignment_policy_idx ON model_runtime_assignment(policy_id);
CREATE INDEX model_runtime_assignment_supersedes_idx
ON model_runtime_assignment(supersedes_assignment_id);
CREATE INDEX model_runtime_assignment_lookup_idx
ON model_runtime_assignment(
    runtime_scope, model_slot, purpose, lane, governance_revision DESC
);

CREATE TABLE model_selection_receipt (
    receipt_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE
        CHECK (receipt_hash ~ '^sha256:[0-9a-f]{64}$'),
    request_hash text NOT NULL UNIQUE
        CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    idempotency_key text NOT NULL UNIQUE,
    runtime_scope text NOT NULL,
    model_slot text NOT NULL,
    purpose text NOT NULL CHECK (purpose IN (
        'RESEARCH', 'BACKTEST', 'SHADOW', 'PRODUCTION_DECISION'
    )),
    selection_status text NOT NULL CHECK (
        selection_status IN ('SELECTED', 'REJECTED')
    ),
    governance_revision bigint NOT NULL CHECK (governance_revision >= 0),
    selected_model_id text REFERENCES model_registrations(model_id),
    selected_registry_version bigint CHECK (selected_registry_version >= 0),
    runtime_lineage_id text NOT NULL REFERENCES model_runtime_lineage(runtime_lineage_id),
    request_json jsonb NOT NULL CHECK (
        jsonb_typeof(request_json) = 'object'
        AND request_json->>'schema_version' = 'model-selection-request-v1'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'model-selection-receipt-v1'
    ),
    selected_at timestamptz NOT NULL
);
CREATE INDEX model_selection_receipt_selected_model_idx
ON model_selection_receipt(selected_model_id);
CREATE INDEX model_selection_receipt_runtime_lineage_idx
ON model_selection_receipt(runtime_lineage_id);
CREATE INDEX model_selection_receipt_revision_idx
ON model_selection_receipt(governance_revision);

CREATE TRIGGER model_governance_action_no_update
BEFORE UPDATE ON model_governance_action
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_governance_action_no_delete
BEFORE DELETE ON model_governance_action
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_version_lineage_no_update
BEFORE UPDATE ON model_version_lineage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_version_lineage_no_delete
BEFORE DELETE ON model_version_lineage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_qualification_evidence_no_update
BEFORE UPDATE ON model_qualification_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_qualification_evidence_no_delete
BEFORE DELETE ON model_qualification_evidence
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_governance_policy_no_update
BEFORE UPDATE ON model_governance_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_governance_policy_no_delete
BEFORE DELETE ON model_governance_policy
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_qualification_decision_no_update
BEFORE UPDATE ON model_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_qualification_decision_no_delete
BEFORE DELETE ON model_qualification_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_runtime_lineage_no_update
BEFORE UPDATE ON model_runtime_lineage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_runtime_lineage_no_delete
BEFORE DELETE ON model_runtime_lineage
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_runtime_assignment_no_update
BEFORE UPDATE ON model_runtime_assignment
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_runtime_assignment_no_delete
BEFORE DELETE ON model_runtime_assignment
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_selection_receipt_no_update
BEFORE UPDATE ON model_selection_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER model_selection_receipt_no_delete
BEFORE DELETE ON model_selection_receipt
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
