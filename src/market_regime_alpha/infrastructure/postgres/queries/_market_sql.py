"""Reusable SQL for representative Market exact/as-of queries."""

_EXACT_BAR_SQL = """
    WITH current_bar AS (
        SELECT candidate.*
        FROM mra.market_bar_revision AS candidate
        WHERE candidate.provider_product_id = %s
          AND candidate.instrument_id = %s
          AND candidate.session_id = %s
          AND candidate.timeframe = %s
          AND candidate.price_basis = %s
          AND candidate.event_start = %s
          AND candidate.event_end = %s
          AND candidate.decision_visible_at <= %s
        ORDER BY candidate.decision_visible_at DESC,
                 candidate.revision DESC,
                 candidate.bar_revision_id DESC
        LIMIT 1
    )
    SELECT
        bar.bar_revision_id, bar.provider_product_id, bar.capture_id,
        bar.instrument_id, bar.session_id, bar.timeframe,
        bar.price_basis, bar.event_start, bar.event_end,
        bar.revision, bar.supersedes_revision_id, bar.open_value,
        bar.high_value, bar.low_value, bar.close_value,
        bar.volume_value, bar.turnover_value, instrument.currency,
        mra.market_artifact_is_readable(
            artifact.integrity_state, artifact.last_verified_at
        ),
        mra.market_artifact_is_readable(
            instrument_artifact.integrity_state, instrument_artifact.last_verified_at
        ),
        mra.market_artifact_is_readable(
            session_artifact.integrity_state, session_artifact.last_verified_at
        )
    FROM current_bar AS bar
    JOIN mra.instrument AS instrument ON instrument.instrument_id = bar.instrument_id
    JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
    JOIN mra.trading_session AS session ON session.session_id = bar.session_id
    JOIN mra.data_capture AS session_capture
      ON session_capture.capture_id = session.source_capture_id
    JOIN mra.artifact AS session_artifact
      ON session_artifact.artifact_id = session_capture.artifact_id
    JOIN mra.data_capture AS capture ON capture.capture_id = bar.capture_id
    JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
    WHERE capture.status = 'CAPTURED'
      AND NOT EXISTS (
          SELECT 1
          FROM mra.source_gap AS newer_gap
          WHERE newer_gap.provider_product_id = bar.provider_product_id
            AND newer_gap.instrument_id = bar.instrument_id
            AND newer_gap.session_id = bar.session_id
            AND newer_gap.fact_kind = 'MARKET_BAR'
            AND newer_gap.timeframe = bar.timeframe
            AND newer_gap.price_basis = bar.price_basis
            AND newer_gap.event_start = bar.event_start
            AND newer_gap.event_end = bar.event_end
            AND newer_gap.decision_visible_at <= %s
            AND newer_gap.decision_visible_at >= bar.decision_visible_at
      )
"""

_TRADING_SESSION_SQL = """
    SELECT session.session_id, session.exchange,
           session.session_date, session.timezone_name,
           session.open_at, session.break_start_at,
           session.break_end_at, session.close_at,
           session.decision_reference_at,
           session.source_capture_id,
           mra.market_artifact_is_readable(
               artifact.integrity_state, artifact.last_verified_at
           ),
           session.decision_visible_at
    FROM mra.trading_session AS session
    JOIN mra.data_capture AS capture
      ON capture.capture_id = session.source_capture_id
    LEFT JOIN mra.artifact AS artifact
      ON artifact.artifact_id = capture.artifact_id
    WHERE session.exchange = %s
      AND session.session_date = %s
      AND session.decision_visible_at <= %s
      AND capture.status = 'CAPTURED'
    ORDER BY session.decision_visible_at DESC, session.recorded_at DESC
    LIMIT 1
"""

_IDENTIFIER_SQL = """
    WITH candidate_identifier AS (
        SELECT identifier.*
        FROM mra.instrument_identifier AS identifier
        JOIN mra.data_capture AS capture
          ON capture.capture_id = identifier.source_capture_id
        WHERE identifier.identifier_scheme = %s
          AND identifier.identifier_value = %s
          AND capture.provider_product_id = %s
          AND identifier.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_identifier AS (
        SELECT DISTINCT ON (
            instrument_id, identifier_scheme, identifier_value, effective_from
        ) *
        FROM candidate_identifier
        ORDER BY instrument_id, identifier_scheme, identifier_value,
                 effective_from, decision_visible_at DESC, revision DESC,
                 instrument_identifier_id DESC
    ), selected_identifier AS (
        SELECT identifier.*
        FROM current_identifier AS identifier
        WHERE identifier.effective_from <= %s
        ORDER BY identifier.effective_from DESC,
                 identifier.decision_visible_at DESC,
                 identifier.revision DESC,
                 identifier.instrument_identifier_id DESC
        LIMIT 1
    )
    SELECT identifier.instrument_id,
           mra.market_artifact_is_readable(
               artifact.integrity_state, artifact.last_verified_at
           ),
           identifier.decision_visible_at, identifier.effective_to,
           mra.market_artifact_is_readable(
               instrument_artifact.integrity_state,
               instrument_artifact.last_verified_at
           )
    FROM selected_identifier AS identifier
    JOIN mra.data_capture AS capture
      ON capture.capture_id = identifier.source_capture_id
    JOIN mra.artifact AS artifact
      ON artifact.artifact_id = capture.artifact_id
    JOIN mra.instrument AS instrument
      ON instrument.instrument_id = identifier.instrument_id
    JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
"""

_CLASSIFICATION_MEMBERS_SQL = """
    WITH candidate_classification AS (
        SELECT classification.*
        FROM mra.classification AS classification
        JOIN mra.data_capture AS capture
          ON capture.capture_id = classification.source_capture_id
        WHERE classification.classification_scheme = %s
          AND classification.classification_code = %s
          AND classification.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_classification AS (
        SELECT DISTINCT ON (classification.effective_from) classification.*
        FROM candidate_classification AS classification
        ORDER BY classification.effective_from,
                 classification.decision_visible_at DESC,
                 classification.revision DESC,
                 classification.classification_id DESC
    ), selected_classification AS (
        SELECT classification.*
        FROM current_classification AS classification
        WHERE classification.effective_from <= %s
        ORDER BY classification.effective_from DESC,
                 classification.decision_visible_at DESC,
                 classification.revision DESC,
                 classification.classification_id DESC
        LIMIT 1
    ), classification_evidence AS (
        SELECT classification.classification_scheme,
               classification.classification_code,
               mra.market_artifact_is_readable(
                   artifact.integrity_state, artifact.last_verified_at
               )
                 AS classification_artifact_readable,
               classification.decision_visible_at AS classification_decision_visible_at,
               classification.effective_to AS classification_effective_to,
               capture.provider_product_id AS classification_provider_product_id
        FROM selected_classification AS classification
        JOIN mra.data_capture AS capture
          ON capture.capture_id = classification.source_capture_id
        JOIN mra.artifact AS artifact
          ON artifact.artifact_id = capture.artifact_id
    ), candidate_membership AS (
        SELECT membership.*
        FROM mra.classification_membership_revision AS membership
        JOIN mra.classification AS membership_classification
          ON membership_classification.classification_id = membership.classification_id
        JOIN classification_evidence AS classification
          ON classification.classification_scheme =
             membership_classification.classification_scheme
         AND classification.classification_code =
             membership_classification.classification_code
        JOIN mra.data_capture AS capture
          ON capture.capture_id = membership.source_capture_id
        WHERE capture.provider_product_id = %s
          AND membership.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_membership AS (
        SELECT DISTINCT ON (instrument_id, effective_from)
               membership_revision_id, source_capture_id, instrument_id,
               membership_status, effective_from, effective_to,
               decision_visible_at, revision
        FROM candidate_membership
        ORDER BY instrument_id, effective_from,
                 decision_visible_at DESC, revision DESC,
                 membership_revision_id DESC
    ), selected_membership AS (
        SELECT DISTINCT ON (membership.instrument_id)
               membership.*
        FROM current_membership AS membership
        WHERE membership.effective_from <= %s
        ORDER BY membership.instrument_id, membership.effective_from DESC,
                 membership.decision_visible_at DESC,
                 membership.revision DESC,
                 membership.membership_revision_id DESC
    )
    SELECT classification.classification_artifact_readable,
           classification.classification_decision_visible_at,
           classification.classification_effective_to,
           membership.instrument_id, membership.membership_status,
           mra.market_artifact_is_readable(
               membership_artifact.integrity_state,
               membership_artifact.last_verified_at
           ),
           membership.decision_visible_at, membership.effective_to,
           mra.market_artifact_is_readable(
               instrument_artifact.integrity_state,
               instrument_artifact.last_verified_at
           ),
           classification.classification_provider_product_id
    FROM classification_evidence AS classification
    LEFT JOIN selected_membership AS membership ON true
    LEFT JOIN mra.data_capture AS membership_capture
      ON membership_capture.capture_id = membership.source_capture_id
    LEFT JOIN mra.artifact AS membership_artifact
      ON membership_artifact.artifact_id = membership_capture.artifact_id
    LEFT JOIN mra.instrument AS instrument
      ON instrument.instrument_id = membership.instrument_id
    LEFT JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    LEFT JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
    ORDER BY membership.instrument_id
"""
