CREATE TABLE research_evaluation_panel_v2 (
    panel_id text PRIMARY KEY,
    panel_hash text NOT NULL UNIQUE CHECK (panel_hash ~ '^sha256:[0-9a-f]{64}$'),
    target_protocol_id text NOT NULL REFERENCES outcome_target_protocol(protocol_id) ON DELETE RESTRICT,
    target_protocol_hash text NOT NULL CHECK (target_protocol_hash ~ '^sha256:[0-9a-f]{64}$'),
    slice_count bigint NOT NULL CHECK (slice_count >= 1),
    row_count bigint NOT NULL CHECK (row_count >= 1),
    payload_json jsonb NOT NULL CHECK (
        jsonb_typeof(payload_json) = 'object'
        AND payload_json->>'schema_version' = 'frozen-research-panel/v2'
    ),
    artifact_locator text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE research_evaluation_panel_slice_v2 (
    panel_id text NOT NULL REFERENCES research_evaluation_panel_v2(panel_id) ON DELETE RESTRICT,
    slice_id text NOT NULL,
    slice_hash text NOT NULL CHECK (slice_hash ~ '^sha256:[0-9a-f]{64}$'),
    shadow_decision_id text NOT NULL REFERENCES shadow_research_decision(decision_id) ON DELETE RESTRICT,
    targeted_outcome_id text NOT NULL REFERENCES targeted_shadow_outcome(settlement_id) ON DELETE RESTRICT,
    run_id text NOT NULL,
    tick_id text NOT NULL,
    trading_date date NOT NULL,
    row_count bigint NOT NULL CHECK (row_count >= 1),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (panel_id, slice_id),
    UNIQUE (panel_id, shadow_decision_id),
    FOREIGN KEY (run_id, tick_id) REFERENCES continuous_runtime_tick(run_id, tick_id) ON DELETE RESTRICT
);

CREATE TABLE research_evaluation_panel_row_v2 (
    panel_id text NOT NULL,
    slice_id text NOT NULL,
    row_id text NOT NULL,
    row_hash text NOT NULL CHECK (row_hash ~ '^sha256:[0-9a-f]{64}$'),
    symbol text NOT NULL,
    universe_eligible boolean NOT NULL,
    pool_included boolean,
    candidate_status text,
    candidate_rank bigint CHECK (candidate_rank IS NULL OR candidate_rank >= 1),
    target_label_count bigint NOT NULL CHECK (target_label_count >= 0),
    payload_json jsonb NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    PRIMARY KEY (panel_id, slice_id, row_id),
    UNIQUE (panel_id, slice_id, symbol),
    FOREIGN KEY (panel_id, slice_id)
        REFERENCES research_evaluation_panel_slice_v2(panel_id, slice_id) ON DELETE RESTRICT
);

CREATE INDEX research_evaluation_panel_date_idx
ON research_evaluation_panel_slice_v2(trading_date, panel_id);
CREATE INDEX research_evaluation_panel_protocol_idx
ON research_evaluation_panel_v2(target_protocol_id);
CREATE INDEX research_evaluation_panel_decision_idx
ON research_evaluation_panel_slice_v2(shadow_decision_id);
CREATE INDEX research_evaluation_panel_outcome_idx
ON research_evaluation_panel_slice_v2(targeted_outcome_id);
CREATE INDEX research_evaluation_panel_tick_idx
ON research_evaluation_panel_slice_v2(run_id, tick_id);
CREATE INDEX research_evaluation_panel_symbol_idx
ON research_evaluation_panel_row_v2(symbol, panel_id, slice_id);

CREATE TRIGGER research_evaluation_panel_v2_no_update BEFORE UPDATE ON research_evaluation_panel_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_evaluation_panel_v2_no_delete BEFORE DELETE ON research_evaluation_panel_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_evaluation_panel_slice_v2_no_update BEFORE UPDATE ON research_evaluation_panel_slice_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_evaluation_panel_slice_v2_no_delete BEFORE DELETE ON research_evaluation_panel_slice_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_evaluation_panel_row_v2_no_update BEFORE UPDATE ON research_evaluation_panel_row_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER research_evaluation_panel_row_v2_no_delete BEFORE DELETE ON research_evaluation_panel_row_v2
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
