-- Selection may declare a fixed exploratory roster without inventing Market membership.
-- Historical classifications, captures and member rows retain their original meaning.
ALTER TABLE mra.universe_member DROP CONSTRAINT universe_member_reason_ck;
ALTER TABLE mra.universe_member ADD CONSTRAINT universe_member_reason_ck CHECK (
    reason_code IN ('CLASSIFICATION_MEMBER', 'CLASSIFICATION_NOT_MEMBER',
        'MARKET_EVIDENCE_MISSING', 'MARKET_EVIDENCE_STALE', 'MARKET_EVIDENCE_GAP',
        'MARKET_EVIDENCE_CONFLICT', 'STATIC_RESEARCH_ROSTER')
);
ALTER TABLE mra.universe_member DROP CONSTRAINT universe_member_disposition_ck;
ALTER TABLE mra.universe_member ADD CONSTRAINT universe_member_disposition_ck CHECK (
    (evidence_status = 'AVAILABLE' AND classification_id IS NOT NULL
     AND classification_membership_revision_id IS NOT NULL AND source_gap_id IS NULL
     AND market_capture_id IS NOT NULL AND market_decision_visible_at IS NOT NULL
     AND ((membership_status = 'INCLUDED' AND observed_membership_status = 'MEMBER'
           AND reason_code = 'CLASSIFICATION_MEMBER')
          OR (membership_status = 'EXCLUDED' AND observed_membership_status = 'NOT_MEMBER'
              AND reason_code = 'CLASSIFICATION_NOT_MEMBER')))
    OR (membership_status = 'UNKNOWN' AND evidence_status <> 'AVAILABLE'
        AND reason_code IN ('MARKET_EVIDENCE_MISSING', 'MARKET_EVIDENCE_STALE',
                           'MARKET_EVIDENCE_GAP', 'MARKET_EVIDENCE_CONFLICT'))
    OR (membership_status = 'INCLUDED' AND evidence_status = 'MISSING'
        AND reason_code = 'STATIC_RESEARCH_ROSTER' AND observed_membership_status IS NULL
        AND classification_id IS NULL AND classification_membership_revision_id IS NULL
        AND source_gap_id IS NULL AND market_capture_id IS NULL AND market_decision_visible_at IS NULL)
);

CREATE FUNCTION mra.require_static_research_universe() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reason_code = 'STATIC_RESEARCH_ROSTER' AND NOT EXISTS (
        SELECT 1 FROM mra.universe_revision revision
        JOIN mra.exploratory_retrospective_universe_revision scope USING(universe_revision_id)
        JOIN mra.market_archive archive USING(market_archive_id)
        JOIN mra.market_archive_seal seal USING(market_archive_id,market_archive_seal_id)
        WHERE revision.universe_revision_id=NEW.universe_revision_id
          AND revision.classification_scheme='STATIC_RESEARCH_ROSTER'
          AND revision.classification_code='SURVIVORSHIP_LIMITED_V1'
          AND archive.lane='RETROSPECTIVE_BACKFILL'
          AND archive.evidence_class='EXPLORATORY_RETROSPECTIVE'
          AND scope.knowledge_cutoff=seal.knowledge_cutoff
          AND scope.simulated_event_cutoff=revision.decision_time
          AND EXISTS (
              SELECT 1 FROM mra.market_capture_instrument_normalization binding
              JOIN mra.market_archive_capture_observation observation USING(capture_id)
              JOIN mra.data_capture capture USING(capture_id)
              WHERE binding.instrument_id=NEW.instrument_id
                AND observation.market_archive_id=archive.market_archive_id
                AND observation.known_at<=scope.knowledge_cutoff
                AND capture.provider_product_id=revision.market_provider_product_id
                AND capture.status='CAPTURED'
          )
    ) THEN
        RAISE EXCEPTION 'STATIC_RESEARCH_REQUIRES_EXACT_RETROSPECTIVE_SCOPE' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER static_research_universe_scope
AFTER INSERT OR UPDATE ON mra.universe_member
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mra.require_static_research_universe();

-- An ordinary Eligibility call cannot erase the static roster limitation.
CREATE FUNCTION mra.require_static_research_eligibility() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM mra.universe_revision revision
               WHERE revision.universe_revision_id=NEW.universe_revision_id
                 AND revision.classification_scheme='STATIC_RESEARCH_ROSTER')
       AND NOT EXISTS (
           SELECT 1 FROM mra.exploratory_retrospective_universe_revision universe
           JOIN mra.exploratory_retrospective_eligibility_batch eligibility
             ON eligibility.universe_revision_id=universe.universe_revision_id
            AND eligibility.market_archive_id=universe.market_archive_id
            AND eligibility.market_archive_seal_id=universe.market_archive_seal_id
            AND eligibility.knowledge_cutoff=universe.knowledge_cutoff
            AND eligibility.simulated_event_cutoff=universe.simulated_event_cutoff
            AND eligibility.scope_content_sha256=universe.scope_content_sha256
            AND eligibility.evidence_lane=universe.evidence_lane
           WHERE universe.universe_revision_id=NEW.universe_revision_id
             AND eligibility.eligibility_policy_id=NEW.eligibility_policy_id
             AND eligibility.simulated_event_cutoff=NEW.decision_time
       ) THEN
        RAISE EXCEPTION 'STATIC_RESEARCH_REQUIRES_EXACT_RETROSPECTIVE_ELIGIBILITY' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER static_research_eligibility_scope
AFTER INSERT OR UPDATE ON mra.eligibility_assessment
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION mra.require_static_research_eligibility();
