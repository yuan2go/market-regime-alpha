-- Replace the O(children * owner-members) JSON-array trigger scan with an
-- owner-derived, indexed membership projection.  The immutable owner payload
-- remains authoritative; these tables are only database integrity guards.

CREATE TABLE free_data_historical_security_fact_member_guard (
    owner_id text NOT NULL,
    owner_hash text NOT NULL CHECK (
        owner_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    fact_id text NOT NULL,
    fact_hash text NOT NULL CHECK (
        fact_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL,
    PRIMARY KEY (owner_id, fact_id),
    FOREIGN KEY (owner_id, owner_hash)
        REFERENCES free_data_historical_security_fact_set(owner_id, owner_hash)
        ON DELETE RESTRICT,
    CHECK (jsonb_typeof(payload_json) = 'object'),
    CHECK (payload_json->>'fact_id' = fact_id),
    CHECK (payload_json->>'fact_hash' = fact_hash)
);

CREATE TABLE free_data_historical_security_fact_gap_member_guard (
    owner_id text NOT NULL,
    owner_hash text NOT NULL CHECK (
        owner_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    gap_id text NOT NULL,
    gap_hash text NOT NULL CHECK (
        gap_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    payload_json jsonb NOT NULL,
    PRIMARY KEY (owner_id, gap_id),
    FOREIGN KEY (owner_id, owner_hash)
        REFERENCES free_data_historical_security_fact_set(owner_id, owner_hash)
        ON DELETE RESTRICT,
    CHECK (jsonb_typeof(payload_json) = 'object'),
    CHECK (payload_json->>'gap_id' = gap_id),
    CHECK (payload_json->>'gap_hash' = gap_hash)
);

INSERT INTO free_data_historical_security_fact_member_guard(
    owner_id, owner_hash, fact_id, fact_hash, payload_json
)
SELECT owner.owner_id,
       owner.owner_hash,
       member->>'fact_id',
       member->>'fact_hash',
       member
FROM free_data_historical_security_fact_set AS owner
CROSS JOIN LATERAL jsonb_array_elements(owner.payload_json->'facts') AS value(member);

INSERT INTO free_data_historical_security_fact_gap_member_guard(
    owner_id, owner_hash, gap_id, gap_hash, payload_json
)
SELECT owner.owner_id,
       owner.owner_hash,
       member->>'gap_id',
       member->>'gap_hash',
       member
FROM free_data_historical_security_fact_set AS owner
CROSS JOIN LATERAL jsonb_array_elements(
    owner.payload_json->'coverage_gaps'
) AS value(member);

CREATE OR REPLACE FUNCTION project_historical_security_fact_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO free_data_historical_security_fact_member_guard(
        owner_id, owner_hash, fact_id, fact_hash, payload_json
    )
    SELECT NEW.owner_id,
           NEW.owner_hash,
           member->>'fact_id',
           member->>'fact_hash',
           member
    FROM jsonb_array_elements(NEW.payload_json->'facts') AS value(member);

    INSERT INTO free_data_historical_security_fact_gap_member_guard(
        owner_id, owner_hash, gap_id, gap_hash, payload_json
    )
    SELECT NEW.owner_id,
           NEW.owner_hash,
           member->>'gap_id',
           member->>'gap_hash',
           member
    FROM jsonb_array_elements(
        NEW.payload_json->'coverage_gaps'
    ) AS value(member);
    RETURN NEW;
END;
$$;

CREATE TRIGGER free_data_historical_security_fact_membership_projection
AFTER INSERT ON free_data_historical_security_fact_set
FOR EACH ROW EXECUTE FUNCTION project_historical_security_fact_membership();

CREATE OR REPLACE FUNCTION guard_historical_security_fact_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM free_data_historical_security_fact_member_guard AS member
        WHERE member.owner_id = NEW.owner_id
          AND member.owner_hash = NEW.owner_hash
          AND member.fact_id = NEW.fact_id
          AND member.fact_hash = NEW.fact_hash
          AND member.payload_json = NEW.payload_json
    ) THEN
        RAISE EXCEPTION
            'historical security fact is not an exact member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_historical_security_fact_gap_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM free_data_historical_security_fact_gap_member_guard AS member
        WHERE member.owner_id = NEW.owner_id
          AND member.owner_hash = NEW.owner_hash
          AND member.gap_id = NEW.gap_id
          AND member.gap_hash = NEW.gap_hash
          AND member.payload_json = NEW.payload_json
    ) THEN
        RAISE EXCEPTION
            'historical security fact gap is not an exact member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER free_data_historical_security_fact_member_guard_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_security_fact_member_guard
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER free_data_historical_security_fact_gap_member_guard_no_update
BEFORE UPDATE OR DELETE ON free_data_historical_security_fact_gap_member_guard
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE free_data_historical_security_fact_member_guard IS
'Indexed integrity projection derived from the immutable Historical Security Facts owner payload.';

COMMENT ON TABLE free_data_historical_security_fact_gap_member_guard IS
'Indexed integrity projection derived from the immutable Historical Security Facts coverage-gap owner payload.';
