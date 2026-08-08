CREATE TABLE pit_authority_action (
    authority_revision bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_type text NOT NULL CHECK (action_type IN (
        'SOURCE_QUALIFICATION', 'RECORD_FACT', 'VALIDATE_PIT'
    )),
    aggregate_id text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    command_hash text NOT NULL CHECK (command_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload_json jsonb NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    created_at timestamptz NOT NULL
);

CREATE TABLE pit_source_qualification (
    qualification_id text PRIMARY KEY,
    qualification_hash text NOT NULL UNIQUE
        CHECK (qualification_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_manifest_id text NOT NULL,
    source_manifest_hash text NOT NULL
        CHECK (source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'),
    provider_id text NOT NULL,
    provider_contract text NOT NULL,
    status text NOT NULL CHECK (status IN ('QUALIFIED', 'SUSPENDED')),
    source_revision integer NOT NULL CHECK (source_revision > 0),
    supersedes_qualification_id text REFERENCES pit_source_qualification(qualification_id),
    authority_revision bigint NOT NULL UNIQUE
        REFERENCES pit_authority_action(authority_revision),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    payload_json jsonb NOT NULL
        CHECK (payload_json->>'schema_version' = 'pit-source-qualification-v1'),
    UNIQUE (
        source_manifest_id, source_manifest_hash, provider_id,
        provider_contract, source_revision
    ),
    CHECK ((source_revision = 1) = (supersedes_qualification_id IS NULL)),
    CHECK (recorded_at >= effective_at)
);
CREATE UNIQUE INDEX pit_source_qualification_one_superseder_idx
    ON pit_source_qualification(supersedes_qualification_id)
    WHERE supersedes_qualification_id IS NOT NULL;
CREATE INDEX pit_source_qualification_lookup_idx
    ON pit_source_qualification(
        source_manifest_id, source_manifest_hash, provider_id,
        provider_contract, source_revision DESC
    );

CREATE TABLE pit_fact_revision (
    fact_id text PRIMARY KEY,
    content_hash text NOT NULL UNIQUE CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    scope_id text NOT NULL,
    logical_key text NOT NULL,
    fact_kind text NOT NULL CHECK (fact_kind IN (
        'MARKET_DATA', 'TRADING_CALENDAR', 'UNIVERSE_MEMBERSHIP',
        'TRADING_STATUS', 'ST_STATUS', 'LISTING_STATUS',
        'TRADING_ELIGIBILITY', 'ADJUSTMENT_FACTOR',
        'FEATURE_MATERIALIZATION', 'FUNDAMENTAL', 'INDEX_MEMBERSHIP',
        'INDUSTRY_MEMBERSHIP', 'THEME_MEMBERSHIP', 'ETF_MEMBERSHIP'
    )),
    subject text NOT NULL,
    fact_revision integer NOT NULL CHECK (fact_revision > 0),
    supersedes_fact_id text REFERENCES pit_fact_revision(fact_id),
    authority_revision bigint NOT NULL UNIQUE REFERENCES pit_authority_action(authority_revision),
    event_time timestamptz NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    available_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT date_trunc('second', statement_timestamp()),
    artifact_id text NOT NULL,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_manifest_id text NOT NULL,
    source_manifest_hash text NOT NULL CHECK (source_manifest_hash ~ '^sha256:[0-9a-f]{64}$'),
    provider_id text NOT NULL,
    provider_contract text NOT NULL,
    data_eligibility text NOT NULL CHECK (data_eligibility IN (
        'UNQUALIFIED', 'EXPLORATORY', 'REHEARSAL', 'FORMAL_RESEARCH'
    )),
    value_json jsonb NOT NULL,
    payload_json jsonb NOT NULL
        CHECK (payload_json->>'schema_version' = 'pit-fact-revision-v1'),
    UNIQUE (scope_id, logical_key, fact_revision),
    CHECK ((fact_revision = 1) = (supersedes_fact_id IS NULL)),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (available_at >= event_time),
    CHECK (recorded_at >= available_at),
    CHECK (ingested_at >= recorded_at)
);

CREATE UNIQUE INDEX pit_fact_revision_one_superseder_idx
    ON pit_fact_revision(supersedes_fact_id)
    WHERE supersedes_fact_id IS NOT NULL;
CREATE INDEX pit_fact_revision_as_of_idx
    ON pit_fact_revision(scope_id, logical_key, authority_revision DESC, fact_revision DESC);
CREATE INDEX pit_fact_revision_temporal_idx
    ON pit_fact_revision(
        scope_id, event_time, available_at, recorded_at, ingested_at
    );
CREATE INDEX pit_fact_revision_authority_idx ON pit_fact_revision(authority_revision);

CREATE TABLE pit_as_of_snapshot (
    snapshot_id text PRIMARY KEY,
    snapshot_hash text NOT NULL UNIQUE CHECK (snapshot_hash ~ '^sha256:[0-9a-f]{64}$'),
    query_hash text NOT NULL CHECK (query_hash ~ '^sha256:[0-9a-f]{64}$'),
    scope_id text NOT NULL,
    decision_time timestamptz NOT NULL,
    authority_revision bigint NOT NULL,
    action_revision bigint NOT NULL UNIQUE REFERENCES pit_authority_action(authority_revision),
    outcome text NOT NULL CHECK (outcome IN ('SATISFIED', 'REJECTED')),
    payload_json jsonb NOT NULL
        CHECK (payload_json->>'schema_version' = 'pit-as-of-snapshot-v1')
);
CREATE INDEX pit_as_of_snapshot_authority_idx ON pit_as_of_snapshot(authority_revision);

CREATE TABLE formal_pit_validation_evidence (
    evidence_id text PRIMARY KEY,
    evidence_hash text NOT NULL UNIQUE CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    request_hash text NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    snapshot_id text NOT NULL UNIQUE REFERENCES pit_as_of_snapshot(snapshot_id),
    authority_revision bigint NOT NULL,
    action_revision bigint NOT NULL UNIQUE REFERENCES pit_authority_action(authority_revision),
    model_id text NOT NULL,
    definition_hash text NOT NULL,
    model_lineage_id text NOT NULL,
    model_lineage_hash text NOT NULL CHECK (model_lineage_hash ~ '^sha256:[0-9a-f]{64}$'),
    outcome text NOT NULL CHECK (outcome IN ('SATISFIED', 'REJECTED')),
    request_json jsonb NOT NULL
        CHECK (request_json->>'schema_version' = 'formal-pit-validation-request-v1'),
    payload_json jsonb NOT NULL
        CHECK (payload_json->>'schema_version' = 'formal-pit-evidence-v1'),
    available_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    CHECK (recorded_at >= available_at)
);
CREATE INDEX formal_pit_evidence_model_idx
    ON formal_pit_validation_evidence(model_id, model_lineage_id, outcome);
CREATE INDEX formal_pit_evidence_authority_idx
    ON formal_pit_validation_evidence(authority_revision);

CREATE TRIGGER pit_authority_action_no_update
    BEFORE UPDATE ON pit_authority_action
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_authority_action_no_delete
    BEFORE DELETE ON pit_authority_action
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_source_qualification_no_update
    BEFORE UPDATE ON pit_source_qualification
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_source_qualification_no_delete
    BEFORE DELETE ON pit_source_qualification
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_fact_revision_no_update
    BEFORE UPDATE ON pit_fact_revision
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_fact_revision_no_delete
    BEFORE DELETE ON pit_fact_revision
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_as_of_snapshot_no_update
    BEFORE UPDATE ON pit_as_of_snapshot
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER pit_as_of_snapshot_no_delete
    BEFORE DELETE ON pit_as_of_snapshot
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_pit_validation_evidence_no_update
    BEFORE UPDATE ON formal_pit_validation_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER formal_pit_validation_evidence_no_delete
    BEFORE DELETE ON formal_pit_validation_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
