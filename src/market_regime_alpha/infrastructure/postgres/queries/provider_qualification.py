"""Read-only PostgreSQL Provider qualification verifier."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.ports.provider_qualification_queries import (
    ProviderQualificationVerification,
)


class PostgresProviderQualificationQueryPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def verify_protocol(
        self, provider_qualification_protocol_id: UUID
    ) -> ProviderQualificationVerification:
        mismatches: list[str] = []
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT protocol.requirement_count = roster.item_count
                       AND roster.minimum_ordinal = 1
                       AND roster.maximum_ordinal = protocol.requirement_count
                       AND roster.kind_count = protocol.requirement_count,
                       protocol.requirement_roster_sha256 = roster.roster_sha256,
                       NOT roster.child_hash_drift,
                       protocol.content_sha256 = mra.canonical_sha256(
                         mra.canonical_json_text(json_build_object(
                           'capture_window_end', mra.canonical_timestamptz_text(protocol.capture_window_end),
                           'capture_window_start', mra.canonical_timestamptz_text(protocol.capture_window_start),
                           'code_artifact', json_build_object(
                             'artifact_id', protocol.code_artifact_id,
                             'content_sha256', json_build_object('value', protocol.code_content_sha256),
                             'size_bytes', protocol.code_size_bytes),
                           'config_artifact', json_build_object(
                             'artifact_id', protocol.config_artifact_id,
                             'content_sha256', json_build_object('value', protocol.config_content_sha256),
                             'size_bytes', protocol.config_size_bytes),
                           'decision_time_rule', protocol.decision_time_rule,
                           'evidence_class', protocol.evidence_class,
                           'evidence_cutoff', mra.canonical_timestamptz_text(protocol.evidence_cutoff),
                           'exchange_code', protocol.exchange_code,
                           'instrument_scope', protocol.instrument_scope,
                           'market_scope', protocol.market_scope,
                           'outcome_path_sessions', protocol.outcome_path_sessions,
                           'price_basis', protocol.price_basis,
                           'provider_product_id', protocol.provider_product_id,
                           'provenance_sha256', protocol.provenance_sha256,
                           'purpose', protocol.purpose,
                           'requirement_count', protocol.requirement_count,
                           'requirement_roster_sha256', protocol.requirement_roster_sha256,
                           'revision', protocol.revision,
                           'supersedes_protocol_id', protocol.supersedes_protocol_id,
                           'timeframe', protocol.timeframe
                         )::jsonb)),
                       CASE WHEN protocol.revision = 1 THEN protocol.supersedes_protocol_id IS NULL
                            ELSE predecessor.provider_qualification_protocol_id IS NOT NULL
                              AND predecessor.protocol_code = protocol.protocol_code
                              AND predecessor.revision + 1 = protocol.revision
                              AND predecessor.provider_product_id = protocol.provider_product_id
                              AND predecessor.registered_at < protocol.registered_at END,
                       EXISTS (
                         SELECT 1 FROM mra.command_receipt receipt
                         JOIN mra.audit_event audit
                           ON audit.command_receipt_id = receipt.receipt_id
                         WHERE receipt.command_kind = 'REGISTER_PROVIDER_QUALIFICATION_PROTOCOL'
                           AND receipt.scope_id = protocol.protocol_code
                           AND receipt.idempotency_key = protocol.request_identity
                           AND receipt.request_hash = protocol.request_sha256
                           AND receipt.status = 'SUCCEEDED'
                           AND receipt.result_aggregate_kind = 'PROVIDER_QUALIFICATION_PROTOCOL'
                           AND receipt.result_aggregate_id = protocol.provider_qualification_protocol_id::text
                           AND audit.action = 'REGISTER_PROVIDER_QUALIFICATION_PROTOCOL'
                           AND audit.aggregate_id = protocol.provider_qualification_protocol_id::text)
                FROM mra.provider_qualification_protocol AS protocol
                LEFT JOIN mra.provider_qualification_protocol AS predecessor
                  ON predecessor.provider_qualification_protocol_id = protocol.supersedes_protocol_id
                CROSS JOIN LATERAL (
                  SELECT count(*)::integer AS item_count,
                         min(ordinal) AS minimum_ordinal,
                         max(ordinal) AS maximum_ordinal,
                         count(DISTINCT requirement_kind)::integer AS kind_count,
                         mra.canonical_sha256(mra.canonical_json_text(json_agg(
                           json_build_object(
                             'content_sha256', content_sha256,
                             'ordinal', ordinal,
                             'requirement_kind', requirement_kind
                           ) ORDER BY ordinal)::jsonb)) AS roster_sha256,
                         bool_or(content_sha256 <> mra.canonical_sha256(
                           mra.canonical_json_text(json_build_object(
                             'minimum_observation_count', minimum_observation_count,
                             'minimum_ratio', minimum_ratio::text,
                             'ordinal', ordinal,
                             'requirement_kind', requirement_kind
                           )::jsonb))) AS child_hash_drift
                  FROM mra.provider_qualification_requirement
                  WHERE provider_qualification_protocol_id = protocol.provider_qualification_protocol_id
                ) AS roster
                WHERE protocol.provider_qualification_protocol_id = %s
                """,
                (provider_qualification_protocol_id,),
            ).fetchone()
        if row is None:
            mismatches.append("PROTOCOL_MISSING")
        else:
            for valid, code in zip(
                row,
                (
                    "REQUIREMENT_ROSTER_INCOMPLETE",
                    "REQUIREMENT_ROSTER_HASH_MISMATCH",
                    "REQUIREMENT_CONTENT_HASH_MISMATCH",
                    "PROTOCOL_CONTENT_HASH_MISMATCH",
                    "PROTOCOL_SUPERSESSION_INVALID",
                    "PROTOCOL_RECEIPT_AUDIT_MISMATCH",
                ),
                strict=True,
            ):
                if valid is not True:
                    mismatches.append(code)
        return self._result(
            "PROVIDER_QUALIFICATION_PROTOCOL",
            provider_qualification_protocol_id,
            mismatches,
        )

    def verify_decision(
        self, provider_qualification_decision_id: UUID
    ) -> ProviderQualificationVerification:
        mismatches: list[str] = []
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT decision.capture_count = captures.item_count
                         AND captures.minimum_ordinal = 1
                         AND captures.maximum_ordinal = decision.capture_count
                         AND captures.item_count = expected.capture_count,
                       decision.capture_roster_sha256 = captures.roster_sha256,
                       NOT captures.child_hash_drift,
                       decision.requirement_result_count = results.item_count
                         AND results.minimum_ordinal = 1
                         AND results.maximum_ordinal = protocol.requirement_count
                         AND results.kind_count = protocol.requirement_count,
                       decision.requirement_result_roster_sha256 = results.roster_sha256,
                       NOT results.child_hash_drift,
                       decision.decision_status = derived.decision_status
                         AND decision.reason_code = derived.reason_code,
                       decision.content_sha256 = mra.canonical_sha256(
                         mra.canonical_json_text(json_build_object(
                           'capture_count', decision.capture_count,
                           'capture_roster_sha256', decision.capture_roster_sha256,
                           'decision_code', decision.decision_code,
                           'decision_status', decision.decision_status,
                           'evidence_class', decision.evidence_class,
                           'protocol_content_sha256', decision.protocol_content_sha256,
                           'provider_product_id', decision.provider_product_id,
                           'purpose', decision.purpose,
                           'reason_code', decision.reason_code,
                           'requirement_result_count', decision.requirement_result_count,
                           'requirement_result_roster_sha256', decision.requirement_result_roster_sha256
                         )::jsonb)),
                       NOT EXISTS (
                         SELECT 1 FROM mra.provider_qualification_requirement requirement
                         WHERE requirement.provider_qualification_protocol_id = protocol.provider_qualification_protocol_id
                           AND NOT EXISTS (
                             SELECT 1 FROM mra.provider_qualification_requirement_result result
                             WHERE result.provider_qualification_decision_id = decision.provider_qualification_decision_id
                               AND result.provider_qualification_requirement_id = requirement.provider_qualification_requirement_id
                               AND result.requirement_kind = requirement.requirement_kind)),
                       NOT EXISTS (
                         SELECT 1 FROM mra.provider_finality_observation observation
                         LEFT JOIN mra.provider_finality_observation predecessor
                           ON predecessor.provider_finality_observation_id = observation.supersedes_observation_id
                         WHERE observation.capture_id IN (
                           SELECT capture_id FROM mra.provider_qualification_capture_member
                           WHERE provider_qualification_decision_id = decision.provider_qualification_decision_id)
                           AND (observation.content_sha256 <> mra.canonical_sha256(
                             mra.canonical_json_text(json_build_object(
                               'capture_id', observation.capture_id,
                               'code_artifact', json_build_object(
                                 'artifact_id', observation.code_artifact_id,
                                 'content_sha256', json_build_object('value', observation.code_content_sha256),
                                 'size_bytes', observation.code_size_bytes),
                               'config_artifact', json_build_object(
                                 'artifact_id', observation.config_artifact_id,
                                 'content_sha256', json_build_object('value', observation.config_content_sha256),
                                 'size_bytes', observation.config_size_bytes),
                               'finality_status', observation.finality_status,
                               'observation_ordinal', observation.observation_ordinal,
                               'provenance_sha256', observation.provenance_sha256,
                               'publication_observed_at', mra.canonical_timestamptz_text(observation.publication_observed_at),
                               'supersedes_observation_id', observation.supersedes_observation_id
                             )::jsonb))
                             OR (observation.observation_ordinal = 1
                                 AND observation.supersedes_observation_id IS NOT NULL)
                             OR (observation.observation_ordinal > 1 AND (
                                 predecessor.capture_id IS DISTINCT FROM observation.capture_id
                                 OR predecessor.observation_ordinal + 1 <> observation.observation_ordinal
                                 OR predecessor.publication_observed_at >= observation.publication_observed_at)))),
                       EXISTS (
                         SELECT 1 FROM mra.command_receipt receipt
                         JOIN mra.audit_event audit
                           ON audit.command_receipt_id = receipt.receipt_id
                         WHERE receipt.command_kind = 'COMPLETE_PROVIDER_QUALIFICATION'
                           AND receipt.scope_id = decision.provider_qualification_protocol_id::text
                           AND receipt.idempotency_key = decision.request_identity
                           AND receipt.request_hash = decision.request_sha256
                           AND receipt.status = 'SUCCEEDED'
                           AND receipt.result_aggregate_kind = 'PROVIDER_QUALIFICATION_DECISION'
                           AND receipt.result_aggregate_id = decision.provider_qualification_decision_id::text
                           AND audit.action = 'COMPLETE_PROVIDER_QUALIFICATION'
                           AND audit.aggregate_id = decision.provider_qualification_decision_id::text)
                FROM mra.provider_qualification_decision AS decision
                JOIN mra.provider_qualification_protocol AS protocol
                  USING (provider_qualification_protocol_id)
                CROSS JOIN LATERAL (
                  SELECT count(*)::integer AS item_count,
                         min(member_ordinal) AS minimum_ordinal,
                         max(member_ordinal) AS maximum_ordinal,
                         mra.canonical_sha256(mra.canonical_json_text(json_agg(
                           json_build_object('capture_id', capture_id,
                             'content_sha256', content_sha256,
                             'ordinal', member_ordinal)
                           ORDER BY member_ordinal)::jsonb)) AS roster_sha256,
                         bool_or(content_sha256 <> mra.canonical_sha256(
                           mra.canonical_json_text(json_build_object(
                             'artifact_id', artifact_id,
                             'artifact_verified', artifact_verified,
                             'capture_id', capture_id,
                             'capture_status', capture_status,
                             'known_at', mra.canonical_timestamptz_text(known_at),
                             'member_ordinal', member_ordinal,
                             'provider_product_id', provider_product_id,
                             'runtime_capture_lineage', runtime_capture_lineage,
                             'source_availability_status', source_availability_status,
                             'source_available_at', CASE WHEN source_available_at IS NULL
                               THEN NULL ELSE mra.canonical_timestamptz_text(source_available_at) END,
                             'source_gap_count', source_gap_count
                           )::jsonb))) AS child_hash_drift
                  FROM mra.provider_qualification_capture_member
                  WHERE provider_qualification_decision_id = decision.provider_qualification_decision_id
                ) AS captures
                CROSS JOIN LATERAL (
                  SELECT count(*)::integer AS item_count,
                         min(result_ordinal) AS minimum_ordinal,
                         max(result_ordinal) AS maximum_ordinal,
                         count(DISTINCT requirement_kind)::integer AS kind_count,
                         mra.canonical_sha256(mra.canonical_json_text(json_agg(
                           json_build_object('content_sha256', content_sha256,
                             'ordinal', result_ordinal,
                             'requirement_kind', requirement_kind)
                           ORDER BY result_ordinal)::jsonb)) AS roster_sha256,
                         bool_or(content_sha256 <> mra.canonical_sha256(
                           mra.canonical_json_text(json_build_object(
                             'observation_count', observation_count,
                             'observed_ratio', observed_ratio::text,
                             'reason_code', reason_code,
                             'requirement_kind', requirement_kind,
                             'result_ordinal', result_ordinal,
                             'result_status', result_status,
                             'satisfied_count', satisfied_count
                           )::jsonb))) AS child_hash_drift
                  FROM mra.provider_qualification_requirement_result
                  WHERE provider_qualification_decision_id = decision.provider_qualification_decision_id
                ) AS results
                CROSS JOIN LATERAL (
                  SELECT count(*)::integer AS capture_count
                  FROM mra.data_capture capture
                  WHERE capture.provider_product_id = decision.provider_product_id
                    AND capture.capture_started_at >= protocol.capture_window_start
                    AND capture.capture_started_at < protocol.capture_window_end
                    AND capture.known_at <= protocol.evidence_cutoff
                ) AS expected
                CROSS JOIN LATERAL (
                  SELECT CASE
                    WHEN bool_or(result_status = 'REJECTED') THEN 'REJECTED'
                    WHEN decision.evidence_class = 'ENGINEERING_REHEARSAL'
                      OR bool_or(result_status = 'INCONCLUSIVE') THEN 'INCONCLUSIVE'
                    ELSE 'ADMITTED' END AS decision_status,
                    CASE
                    WHEN bool_or(result_status = 'REJECTED') THEN 'PROVIDER_REQUIREMENT_REJECTED'
                    WHEN decision.evidence_class = 'ENGINEERING_REHEARSAL'
                      OR bool_or(result_status = 'INCONCLUSIVE') THEN 'PROVIDER_EVIDENCE_INCONCLUSIVE'
                    ELSE 'ALL_PROVIDER_REQUIREMENTS_SATISFIED' END AS reason_code
                  FROM mra.provider_qualification_requirement_result
                  WHERE provider_qualification_decision_id = decision.provider_qualification_decision_id
                ) AS derived
                WHERE decision.provider_qualification_decision_id = %s
                """,
                (provider_qualification_decision_id,),
            ).fetchone()
            visibility_drift = connection.execute(
                """
                SELECT sum(invalid_count)::integer FROM (
                  SELECT count(*) FILTER (WHERE v.content_sha256 <> mra.canonical_sha256(
                    mra.canonical_json_text(json_build_object(
                      'capture_id', v.capture_id,
                      'provider_qualification_decision_id', v.provider_qualification_decision_id,
                      'qualified_decision_visible_at', mra.canonical_timestamptz_text(v.qualified_decision_visible_at),
                      'source_content_sha256', v.source_content_sha256,
                      'source_identity', v.bar_revision_id,
                      'source_kind', 'MARKET_BAR_REVISION')::jsonb))) AS invalid_count
                  FROM mra.qualified_market_bar_visibility v
                  WHERE v.provider_qualification_decision_id = %s
                  UNION ALL SELECT count(*) FILTER (WHERE v.content_sha256 <> mra.canonical_sha256(
                    mra.canonical_json_text(json_build_object(
                      'capture_id', v.capture_id,
                      'provider_qualification_decision_id', v.provider_qualification_decision_id,
                      'qualified_decision_visible_at', mra.canonical_timestamptz_text(v.qualified_decision_visible_at),
                      'source_content_sha256', v.source_content_sha256,
                      'source_identity', v.fact_revision_id,
                      'source_kind', 'INSTRUMENT_FACT_REVISION')::jsonb)))
                  FROM mra.qualified_instrument_fact_visibility v
                  WHERE v.provider_qualification_decision_id = %s
                  UNION ALL SELECT count(*) FILTER (WHERE v.content_sha256 <> mra.canonical_sha256(
                    mra.canonical_json_text(json_build_object(
                      'capture_id', v.capture_id,
                      'provider_qualification_decision_id', v.provider_qualification_decision_id,
                      'qualified_decision_visible_at', mra.canonical_timestamptz_text(v.qualified_decision_visible_at),
                      'source_content_sha256', v.source_content_sha256,
                      'source_identity', v.membership_revision_id,
                      'source_kind', 'CLASSIFICATION_MEMBERSHIP_REVISION')::jsonb)))
                  FROM mra.qualified_classification_membership_visibility v
                  WHERE v.provider_qualification_decision_id = %s
                  UNION ALL SELECT count(*) FILTER (WHERE v.content_sha256 <> mra.canonical_sha256(
                    mra.canonical_json_text(json_build_object(
                      'capture_id', v.capture_id,
                      'provider_qualification_decision_id', v.provider_qualification_decision_id,
                      'qualified_decision_visible_at', mra.canonical_timestamptz_text(v.qualified_decision_visible_at),
                      'source_content_sha256', v.source_content_sha256,
                      'source_identity', v.session_id,
                      'source_kind', 'TRADING_SESSION')::jsonb)))
                  FROM mra.qualified_trading_session_visibility v
                  WHERE v.provider_qualification_decision_id = %s
                  UNION ALL SELECT count(*) FILTER (WHERE v.content_sha256 <> mra.canonical_sha256(
                    mra.canonical_json_text(json_build_object(
                      'capture_id', v.capture_id,
                      'provider_qualification_decision_id', v.provider_qualification_decision_id,
                      'qualified_decision_visible_at', mra.canonical_timestamptz_text(v.qualified_decision_visible_at),
                      'source_content_sha256', v.source_content_sha256,
                      'source_identity', v.gap_id,
                      'source_kind', 'SOURCE_GAP')::jsonb)))
                  FROM mra.qualified_source_gap_visibility v
                  WHERE v.provider_qualification_decision_id = %s
                ) invalid
                """,
                (provider_qualification_decision_id,) * 5,
            ).fetchone()
        if row is None:
            mismatches.append("DECISION_MISSING")
        else:
            for valid, code in zip(
                row,
                (
                    "CAPTURE_ROSTER_INCOMPLETE",
                    "CAPTURE_ROSTER_HASH_MISMATCH",
                    "CAPTURE_MEMBER_HASH_MISMATCH",
                    "REQUIREMENT_RESULT_ROSTER_INCOMPLETE",
                    "REQUIREMENT_RESULT_ROSTER_HASH_MISMATCH",
                    "REQUIREMENT_RESULT_HASH_MISMATCH",
                    "DECISION_DERIVATION_MISMATCH",
                    "DECISION_CONTENT_HASH_MISMATCH",
                    "REQUIREMENT_RESULT_BINDING_MISMATCH",
                    "FINALITY_CHAIN_MISMATCH",
                    "DECISION_RECEIPT_AUDIT_MISMATCH",
                ),
                strict=True,
            ):
                if valid is not True:
                    mismatches.append(code)
        if visibility_drift is not None and int(visibility_drift[0] or 0):
            mismatches.append("QUALIFIED_VISIBILITY_HASH_MISMATCH")
        return self._result(
            "PROVIDER_QUALIFICATION_DECISION",
            provider_qualification_decision_id,
            mismatches,
        )

    @staticmethod
    def _result(
        aggregate_kind: str,
        aggregate_id: UUID,
        mismatches: list[str],
    ) -> ProviderQualificationVerification:
        return ProviderQualificationVerification(
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            matched=not mismatches,
            mismatch_count=len(mismatches),
            mismatches=tuple(mismatches),
        )


__all__ = ["PostgresProviderQualificationQueryPort"]
