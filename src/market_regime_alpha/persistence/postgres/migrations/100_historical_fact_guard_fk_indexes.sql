-- Support the owner hash foreign keys used by the immutable membership guards.
-- The primary keys begin with owner_id but do not cover owner_hash.

CREATE INDEX free_data_historical_security_fact_member_guard_owner_idx
    ON free_data_historical_security_fact_member_guard(owner_id, owner_hash);

CREATE INDEX free_data_historical_security_fact_gap_member_guard_owner_idx
    ON free_data_historical_security_fact_gap_member_guard(owner_id, owner_hash);
