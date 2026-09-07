-- Explicit post-baseline correction. Never rewrite 001_baseline or prior bundles.
-- Existing observation identities, frozen ordinals and content hashes are retained.
ALTER TABLE mra.prospective_archive_revision_observation
    DROP CONSTRAINT prospective_archive_revision_shape_ck,
    ADD CONSTRAINT prospective_archive_revision_shape_ck CHECK (
        comparison_ordinal > 0
        AND relation IN ('FIRST', 'IDENTICAL', 'CHANGED')
        AND ((predecessor_observation_id IS NULL) = (relation = 'FIRST'))
        AND artifact_sha256 ~ '^[0-9a-f]{64}$'
        AND normalized_revision_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );

CREATE OR REPLACE FUNCTION mra.validate_prospective_archive_revision()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE observation mra.market_archive_capture_observation%ROWTYPE;
DECLARE schedule mra.prospective_archive_slice_schedule%ROWTYPE;
DECLARE prior mra.prospective_archive_revision_observation%ROWTYPE;
DECLARE expected_relation text;
DECLARE expected_content text;
BEGIN
    SELECT * INTO observation FROM mra.market_archive_capture_observation
    WHERE market_archive_capture_observation_id = NEW.market_archive_capture_observation_id
    FOR SHARE;
    SELECT * INTO schedule FROM mra.prospective_archive_slice_schedule
    WHERE market_archive_slice_id = NEW.market_archive_slice_id FOR SHARE;
    SELECT * INTO prior FROM mra.prospective_archive_revision_observation
    WHERE market_archive_id = NEW.market_archive_id
      AND instrument_id = NEW.instrument_id
      AND target_checkpoint_id = NEW.target_checkpoint_id
    ORDER BY comparison_ordinal DESC LIMIT 1 FOR SHARE;
    expected_relation := CASE
        WHEN prior.market_archive_capture_observation_id IS NULL THEN 'FIRST'
        WHEN prior.artifact_sha256 = observation.artifact_sha256
         AND prior.normalized_revision_roster_sha256 = observation.normalized_revision_roster_sha256
            THEN 'IDENTICAL'
        ELSE 'CHANGED' END;
    IF observation.market_archive_id <> NEW.market_archive_id
       OR observation.market_archive_slice_id <> NEW.market_archive_slice_id
       OR schedule.instrument_id <> NEW.instrument_id
       OR schedule.target_checkpoint_id <> NEW.target_checkpoint_id
       OR schedule.comparison_ordinal <> NEW.comparison_ordinal
       OR NEW.artifact_sha256 <> observation.artifact_sha256
       OR NEW.normalized_revision_roster_sha256 <> observation.normalized_revision_roster_sha256
       OR NEW.relation <> expected_relation
       OR (prior.market_archive_capture_observation_id IS NULL AND NEW.predecessor_observation_id IS NOT NULL)
       OR (prior.market_archive_capture_observation_id IS NOT NULL AND (
            NEW.predecessor_observation_id IS DISTINCT FROM prior.market_archive_capture_observation_id
            OR NEW.comparison_ordinal <= prior.comparison_ordinal
       )) THEN
        RAISE EXCEPTION 'Prospective archive revision chain is invalid'
            USING ERRCODE = '55000';
    END IF;
    -- Frozen comparison ordinals count planned windows, including terminal
    -- negative windows. Only actual captures belong to the revision chain.
    IF (SELECT count(*)
        FROM mra.prospective_archive_slice_schedule skipped
        JOIN mra.prospective_archive_slice_terminal terminal
          ON terminal.market_archive_id = skipped.market_archive_id
         AND terminal.market_archive_slice_id = skipped.market_archive_slice_id
        WHERE skipped.market_archive_id = NEW.market_archive_id
          AND skipped.instrument_id = NEW.instrument_id
          AND skipped.target_checkpoint_id = NEW.target_checkpoint_id
          AND skipped.comparison_ordinal > COALESCE(prior.comparison_ordinal, 0)
          AND skipped.comparison_ordinal < NEW.comparison_ordinal
          AND terminal.terminal_state IN ('PROVIDER_GAP', 'RESOURCE_STOP', 'FAILED', 'MISSED')
          AND terminal.terminal_at <= observation.observed_at
       ) <> NEW.comparison_ordinal - COALESCE(prior.comparison_ordinal, 0) - 1 THEN
        RAISE EXCEPTION 'Prospective archive revision skips an unresolved expected window'
            USING ERRCODE = '55000';
    END IF;
    expected_content := mra.canonical_sha256(mra.canonical_json_text(jsonb_build_object(
        'artifact_sha256', NEW.artifact_sha256,
        'comparison_ordinal', NEW.comparison_ordinal,
        'instrument_id', NEW.instrument_id,
        'market_archive_capture_observation_id', NEW.market_archive_capture_observation_id,
        'market_archive_id', NEW.market_archive_id,
        'market_archive_slice_id', NEW.market_archive_slice_id,
        'target_checkpoint_id', NEW.target_checkpoint_id,
        'normalized_revision_roster_sha256', NEW.normalized_revision_roster_sha256,
        'predecessor_observation_id', NEW.predecessor_observation_id,
        'relation', NEW.relation
    )));
    IF NEW.content_sha256 <> expected_content THEN
        RAISE EXCEPTION 'Prospective archive revision hash is invalid'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
