CREATE TABLE security_principal (
    principal_id text PRIMARY KEY,
    principal_hash text NOT NULL UNIQUE CHECK (
        principal_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    external_subject text NOT NULL UNIQUE,
    display_name text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'security-principal/v1'
    ),
    created_at timestamptz NOT NULL
);

CREATE TABLE security_principal_status_event (
    event_id text PRIMARY KEY,
    event_hash text NOT NULL UNIQUE CHECK (
        event_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    principal_id text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    sequence integer NOT NULL CHECK (sequence > 0),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    changed_by text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    reason text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    occurred_at timestamptz NOT NULL,
    UNIQUE (principal_id, sequence)
);

CREATE INDEX security_principal_status_changed_by_idx
ON security_principal_status_event(changed_by);

CREATE TABLE security_role_event (
    event_id text PRIMARY KEY,
    event_hash text NOT NULL UNIQUE CHECK (
        event_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    principal_id text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    role text NOT NULL CHECK (role IN (
        'RESEARCHER', 'OPERATOR', 'APPROVER', 'ADMIN'
    )),
    event_kind text NOT NULL CHECK (event_kind IN ('GRANTED', 'REVOKED')),
    sequence integer NOT NULL CHECK (sequence > 0),
    previous_event_id text REFERENCES security_role_event(event_id) ON DELETE RESTRICT,
    changed_by text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    reason text NOT NULL,
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    occurred_at timestamptz NOT NULL,
    UNIQUE (principal_id, role, sequence),
    CHECK (
        (sequence = 1 AND previous_event_id IS NULL)
        OR (sequence > 1 AND previous_event_id IS NOT NULL)
    )
);

CREATE INDEX security_role_event_previous_idx ON security_role_event(previous_event_id);
CREATE INDEX security_role_event_changed_by_idx ON security_role_event(changed_by);

CREATE TABLE security_approval (
    approval_id text PRIMARY KEY,
    approval_hash text NOT NULL UNIQUE CHECK (
        approval_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    action_kind text NOT NULL CHECK (action_kind IN (
        'RESEARCH_CHANGE', 'SHADOW_OPERATION', 'RECOVERY_OPERATION'
    )),
    resource_kind text NOT NULL,
    resource_id text NOT NULL,
    resource_hash text NOT NULL CHECK (
        resource_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    requested_by text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    reason text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'security-approval/v1'
    ),
    requested_at timestamptz NOT NULL
);

CREATE INDEX security_approval_requested_by_idx ON security_approval(requested_by);

CREATE TABLE security_approval_decision (
    decision_id text PRIMARY KEY,
    decision_hash text NOT NULL UNIQUE CHECK (
        decision_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    approval_id text NOT NULL UNIQUE REFERENCES security_approval(approval_id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    decided_by text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    reason text NOT NULL,
    production_authorized boolean NOT NULL DEFAULT false CHECK (NOT production_authorized),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'security-approval-decision/v1'
    ),
    decided_at timestamptz NOT NULL
);

CREATE INDEX security_approval_decision_decided_by_idx
ON security_approval_decision(decided_by);

CREATE TABLE security_audit_event (
    audit_id text PRIMARY KEY,
    audit_hash text NOT NULL UNIQUE CHECK (
        audit_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    event_kind text NOT NULL,
    actor_principal_id text NOT NULL REFERENCES security_principal(principal_id) ON DELETE RESTRICT,
    target_kind text NOT NULL,
    target_id text NOT NULL,
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'security-audit-event/v1'
    ),
    occurred_at timestamptz NOT NULL
);

CREATE INDEX security_audit_actor_idx
ON security_audit_event(actor_principal_id, occurred_at, audit_id);

CREATE TABLE security_governance_command (
    idempotency_key text PRIMARY KEY,
    command_hash text NOT NULL CHECK (
        command_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    result_kind text NOT NULL,
    result_id text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TRIGGER security_principal_no_update
BEFORE UPDATE OR DELETE ON security_principal
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_principal_status_event_no_update
BEFORE UPDATE OR DELETE ON security_principal_status_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_role_event_no_update
BEFORE UPDATE OR DELETE ON security_role_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_approval_no_update
BEFORE UPDATE OR DELETE ON security_approval
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_approval_decision_no_update
BEFORE UPDATE OR DELETE ON security_approval_decision
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_audit_event_no_update
BEFORE UPDATE OR DELETE ON security_audit_event
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER security_governance_command_no_update
BEFORE UPDATE OR DELETE ON security_governance_command
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
