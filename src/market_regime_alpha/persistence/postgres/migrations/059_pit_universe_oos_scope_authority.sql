CREATE TABLE pit_universe_membership_projection (
    projection_id text PRIMARY KEY,
    projection_hash text NOT NULL UNIQUE CHECK (
        projection_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    artifact_resolution_id text NOT NULL UNIQUE,
    artifact_resolution_hash text NOT NULL CHECK (
        artifact_resolution_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    universe_id text NOT NULL,
    universe_hash text NOT NULL CHECK (
        universe_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    decision_date date NOT NULL,
    effective_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL CHECK (available_at >= effective_at),
    member_count integer NOT NULL CHECK (member_count > 0),
    included_member_count integer NOT NULL CHECK (
        included_member_count >= 0 AND included_member_count <= member_count
    ),
    members_hash text NOT NULL CHECK (
        members_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'pit-universe-membership-authority-projection-v1'
    ),
    resolved_at timestamptz NOT NULL,
    UNIQUE (projection_id, projection_hash),
    FOREIGN KEY (artifact_resolution_id, artifact_resolution_hash)
        REFERENCES pit_artifact_authority_resolution(
            resolution_id, resolution_hash
        ) ON DELETE RESTRICT
);

CREATE TABLE pit_universe_membership_projection_member (
    projection_id text NOT NULL
        REFERENCES pit_universe_membership_projection(projection_id)
        ON DELETE RESTRICT,
    symbol text NOT NULL CHECK (btrim(symbol) <> ''),
    included boolean NOT NULL,
    record_hash text NOT NULL CHECK (record_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (projection_id, symbol)
);

CREATE INDEX pit_universe_membership_resolution_idx
ON pit_universe_membership_projection(
    artifact_resolution_id, artifact_resolution_hash
);

CREATE INDEX pit_universe_membership_included_idx
ON pit_universe_membership_projection_member(projection_id, included, symbol);

CREATE TABLE formal_locked_oos_roster_universe_binding (
    roster_id text PRIMARY KEY
        REFERENCES formal_locked_oos_roster(roster_id) ON DELETE RESTRICT,
    projection_id text NOT NULL,
    projection_hash text NOT NULL CHECK (
        projection_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    universe_id text NOT NULL,
    universe_hash text NOT NULL CHECK (
        universe_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    members_hash text NOT NULL CHECK (members_hash ~ '^sha256:[0-9a-f]{64}$'),
    included_member_count integer NOT NULL CHECK (included_member_count > 0),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' =
            'formal-locked-oos-roster-universe-binding-v1'
    ),
    bound_at timestamptz NOT NULL,
    FOREIGN KEY (projection_id, projection_hash)
        REFERENCES pit_universe_membership_projection(
            projection_id, projection_hash
        ) ON DELETE RESTRICT
);

CREATE INDEX formal_locked_oos_roster_universe_projection_idx
ON formal_locked_oos_roster_universe_binding(projection_id, projection_hash);

CREATE TRIGGER pit_universe_membership_projection_no_update
BEFORE UPDATE OR DELETE ON pit_universe_membership_projection
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER pit_universe_membership_projection_member_no_update
BEFORE UPDATE OR DELETE ON pit_universe_membership_projection_member
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER formal_locked_oos_roster_universe_binding_no_update
BEFORE UPDATE OR DELETE ON formal_locked_oos_roster_universe_binding
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE pit_universe_membership_projection IS
'Strict Operational Universe Reader projection; its complete record and included-member sets are immutable and content-addressed.';

COMMENT ON TABLE formal_locked_oos_roster_universe_binding IS
'Binds each new Locked OOS roster to the frozen Protocol Universe complete included-member set before Target outcome values are read.';
