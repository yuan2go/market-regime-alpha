-- Phase E3 bounded-memory component aggregation access path.

CREATE INDEX historical_corpus_component_keyset_idx
ON historical_corpus_session_component(
    run_id, component_kind, trading_date, ordinal, component_id
)
INCLUDE (component_hash, materialized_at);

COMMENT ON INDEX historical_corpus_component_keyset_idx IS
'Keyset path for bounded Historical Panel, Outcome, Ablation and Challenger streaming.';
