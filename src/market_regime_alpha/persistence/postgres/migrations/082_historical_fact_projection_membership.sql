-- Prevent child projections from admitting records outside the immutable owner payload.

CREATE OR REPLACE FUNCTION guard_historical_security_fact_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    owner_payload jsonb;
BEGIN
    SELECT payload_json INTO owner_payload
    FROM free_data_historical_security_fact_set
    WHERE owner_id = NEW.owner_id AND owner_hash = NEW.owner_hash;

    IF owner_payload IS NULL
       OR NOT (owner_payload->'facts' @> jsonb_build_array(NEW.payload_json)) THEN
        RAISE EXCEPTION 'historical security fact is not a member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_historical_security_fact_gap_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    owner_payload jsonb;
BEGIN
    SELECT payload_json INTO owner_payload
    FROM free_data_historical_security_fact_set
    WHERE owner_id = NEW.owner_id AND owner_hash = NEW.owner_hash;

    IF owner_payload IS NULL
       OR NOT (
           owner_payload->'coverage_gaps'
           @> jsonb_build_array(NEW.payload_json)
       ) THEN
        RAISE EXCEPTION 'historical security fact gap is not a member of its owner';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER free_data_historical_security_fact_membership
BEFORE INSERT ON free_data_historical_security_fact
FOR EACH ROW EXECUTE FUNCTION guard_historical_security_fact_membership();

CREATE TRIGGER free_data_historical_security_fact_gap_membership
BEFORE INSERT ON free_data_historical_security_fact_coverage_gap
FOR EACH ROW EXECUTE FUNCTION guard_historical_security_fact_gap_membership();

COMMENT ON FUNCTION guard_historical_security_fact_membership() IS
'Migration 082 binds every queryable fact child to the immutable fact array carried by its owner.';

COMMENT ON FUNCTION guard_historical_security_fact_gap_membership() IS
'Migration 082 binds every queryable coverage-gap child to the immutable gap array carried by its owner.';
