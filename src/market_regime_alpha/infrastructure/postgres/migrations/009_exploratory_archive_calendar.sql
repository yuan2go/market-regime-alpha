-- A canonical Calendar identity can be observed by several sources. Resolve
-- its provenance only within the frozen exploratory Archive and knowledge cut.
-- No business row, hash, formal visibility or historical migration is rewritten.
CREATE FUNCTION mra.exploratory_archive_calendar_capture(
    p_session_id uuid, p_archive_id uuid, p_knowledge_cutoff timestamptz
) RETURNS TABLE(capture_id uuid, decision_visible_at timestamptz, foundation_integrity boolean)
LANGUAGE sql STABLE AS $$
    SELECT capture.capture_id,
           greatest(session.decision_visible_at, capture.decision_visible_at,
                    normalized.recorded_at, observation.known_at),
           mra.market_artifact_is_readable(artifact.integrity_state, artifact.last_verified_at)
    FROM mra.trading_session AS session
    JOIN mra.market_capture_trading_session_normalization AS binding USING(session_id)
    JOIN mra.market_capture_reference_normalization AS normalized USING(capture_id)
    JOIN mra.data_capture AS capture USING(capture_id)
    JOIN mra.market_archive_capture_observation AS observation USING(capture_id)
    JOIN mra.market_archive AS archive USING(market_archive_id)
    JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
    WHERE session.session_id = p_session_id AND archive.market_archive_id = p_archive_id
      AND capture.provider_product_id = archive.provider_product_id
      AND capture.status = 'CAPTURED'
      AND capture.recorded_at <= p_knowledge_cutoff
      AND capture.decision_visible_at <= p_knowledge_cutoff
      AND normalized.recorded_at <= p_knowledge_cutoff
      AND observation.known_at <= p_knowledge_cutoff
      AND session.decision_visible_at <= p_knowledge_cutoff
    ORDER BY (capture.capture_id = session.source_capture_id) DESC,
             normalized.recorded_at, capture.capture_id
    LIMIT 1
$$;

CREATE OR REPLACE FUNCTION mra.validate_exploratory_retrospective_dataset()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_count integer;
DECLARE expected_roster text;
DECLARE expected_scope text;
DECLARE expected_content text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM mra.dataset AS dataset
        JOIN mra.market_archive AS archive ON archive.market_archive_id = NEW.market_archive_id
        JOIN mra.market_archive_seal AS seal
          ON seal.market_archive_seal_id = NEW.market_archive_seal_id
         AND seal.market_archive_id = archive.market_archive_id
        WHERE dataset.dataset_id = NEW.dataset_id
          AND dataset.decision_time = NEW.simulated_event_cutoff
          AND archive.lane = 'RETROSPECTIVE_BACKFILL'
          AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
          AND seal.knowledge_cutoff = NEW.knowledge_cutoff
    ) OR EXISTS (
        SELECT 1 FROM mra.formal_research_dataset
        WHERE dataset_id = NEW.dataset_id
    ) THEN
        RAISE EXCEPTION 'Exploratory Dataset dual-clock/archive binding is invalid' USING ERRCODE = '55000';
    END IF;
    SELECT count(*),
           mra.canonical_sha256(mra.canonical_json_text(coalesce(jsonb_agg(
               jsonb_build_object(
                   'dataset_source_id', dataset_source_id,
                   'source_identity', coalesce(
                       market_bar_revision_id,
                       market_instrument_fact_revision_id,
                       market_trading_session_id,
                       market_source_gap_id,
                       market_capture_id
                   ),
                   'source_role', source_role
               ) ORDER BY dataset_source_id
           ), '[]'::jsonb)))
      INTO expected_count, expected_roster
    FROM mra.dataset_source
    WHERE dataset_id = NEW.dataset_id
      AND source_role IN (
          'MARKET_BAR_REVISION', 'MARKET_INSTRUMENT_FACT_REVISION',
          'MARKET_TRADING_SESSION', 'MARKET_SOURCE_GAP', 'MARKET_CAPTURE'
      );
    IF NEW.source_count <> expected_count
       OR NEW.source_roster_sha256 <> expected_roster
       OR EXISTS (
           SELECT 1 FROM mra.dataset_source
           WHERE dataset_id = NEW.dataset_id AND source_role = 'MARKET_CAPTURE'
       ) OR EXISTS (
           WITH source_facts AS (
               SELECT source.dataset_source_id, bar.capture_id,
                      bar.event_end AS event_cutoff_at,
                      bar.decision_visible_at, NULL::uuid AS gap_id
               FROM mra.dataset_source AS source
               JOIN mra.market_bar_revision AS bar
                 ON bar.bar_revision_id = source.market_bar_revision_id
               WHERE source.dataset_id = NEW.dataset_id
                 AND source.source_role = 'MARKET_BAR_REVISION'
               UNION ALL
               SELECT source.dataset_source_id, fact.capture_id,
                      fact.event_start, fact.decision_visible_at, NULL::uuid
               FROM mra.dataset_source AS source
               JOIN mra.instrument_fact_revision AS fact
                 ON fact.fact_revision_id = source.market_instrument_fact_revision_id
               WHERE source.dataset_id = NEW.dataset_id
                 AND source.source_role = 'MARKET_INSTRUMENT_FACT_REVISION'
               UNION ALL
               SELECT source.dataset_source_id, binding.capture_id,
                      session.decision_reference_at, binding.decision_visible_at,
                      NULL::uuid
               FROM mra.dataset_source AS source
               JOIN mra.trading_session AS session
                 ON session.session_id = source.market_trading_session_id
               LEFT JOIN LATERAL (
                   SELECT capture_id, decision_visible_at
                   FROM mra.exploratory_archive_calendar_capture(
                       session.session_id, NEW.market_archive_id, NEW.knowledge_cutoff
                   ) WHERE foundation_integrity
               ) AS binding ON true
               WHERE source.dataset_id = NEW.dataset_id
                 AND source.source_role = 'MARKET_TRADING_SESSION'
               UNION ALL
               SELECT source.dataset_source_id, gap.capture_id,
                      coalesce(gap.event_end, gap.effective_from, gap.event_start),
                      gap.decision_visible_at, gap.gap_id
               FROM mra.dataset_source AS source
               JOIN mra.source_gap AS gap ON gap.gap_id = source.market_source_gap_id
               WHERE source.dataset_id = NEW.dataset_id
                 AND source.source_role = 'MARKET_SOURCE_GAP'
           )
           SELECT 1 FROM source_facts AS fact
           WHERE fact.event_cutoff_at IS NULL
              OR fact.event_cutoff_at > NEW.simulated_event_cutoff
              OR fact.decision_visible_at > NEW.knowledge_cutoff
              OR NOT (
                  EXISTS (
                      SELECT 1 FROM mra.market_archive_capture_observation AS observation
                      WHERE observation.market_archive_id = NEW.market_archive_id
                        AND observation.capture_id = fact.capture_id
                  ) OR (
                      fact.gap_id IS NOT NULL AND EXISTS (
                          SELECT 1 FROM mra.market_archive_slice_gap AS gap_binding
                          WHERE gap_binding.market_archive_id = NEW.market_archive_id
                            AND gap_binding.gap_id = fact.gap_id
                      )
                  )
              )
       ) THEN
        RAISE EXCEPTION 'Exploratory Dataset source roster exceeds its archive dual-clock scope' USING ERRCODE = '55000';
    END IF;
    expected_scope := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'evidence_lane', NEW.evidence_lane,
        'knowledge_cutoff',
            mra.canonical_timestamptz_text(NEW.knowledge_cutoff),
        'market_archive_id', NEW.market_archive_id,
        'market_archive_seal_id', NEW.market_archive_seal_id,
        'simulated_event_cutoff',
            mra.canonical_timestamptz_text(NEW.simulated_event_cutoff)
    )));
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'dataset_id', NEW.dataset_id,
        'evidence_lane', NEW.evidence_lane,
        'knowledge_cutoff',
            mra.canonical_timestamptz_text(NEW.knowledge_cutoff),
        'market_archive_id', NEW.market_archive_id,
        'market_archive_seal_id', NEW.market_archive_seal_id,
        'scope_content_sha256', NEW.scope_content_sha256,
        'simulated_event_cutoff',
            mra.canonical_timestamptz_text(NEW.simulated_event_cutoff),
        'source_count', NEW.source_count,
        'source_roster_sha256', NEW.source_roster_sha256
    )));
    IF NEW.scope_content_sha256 <> expected_scope OR NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Exploratory Dataset content hash is invalid' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
