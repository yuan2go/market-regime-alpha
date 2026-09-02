"""PostgreSQL owner for Provider qualification protocol and decisions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.market.domain import (
    ProviderFinalityObservation,
    ProviderQualificationProtocol,
    ProviderRequirementKind,
)
from market_regime_alpha.market.ports.provider_qualification import (
    ProviderQualificationCaptureMember,
    ProviderQualificationDecisionRecord,
    ProviderQualificationProtocolRecord,
    QualifiedHistoricalVisibilityRecord,
    ProviderRequirementEvaluation,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresProviderQualificationRepository:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def protocol_request_receipt(
        self, protocol_code: str, request_identity: str
    ) -> ReceiptRecord | None:
        return self._request_receipt(
            command_kind="REGISTER_PROVIDER_QUALIFICATION_PROTOCOL",
            scope_id=protocol_code,
            request_identity=request_identity,
        )

    def finality_request_receipt(
        self, capture_id: UUID, request_identity: str
    ) -> ReceiptRecord | None:
        return self._request_receipt(
            command_kind="RECORD_PROVIDER_FINALITY_OBSERVATION",
            scope_id=str(capture_id),
            request_identity=request_identity,
        )

    def decision_request_receipt(
        self, provider_qualification_protocol_id: UUID, request_identity: str
    ) -> ReceiptRecord | None:
        return self._request_receipt(
            command_kind="COMPLETE_PROVIDER_QUALIFICATION",
            scope_id=str(provider_qualification_protocol_id),
            request_identity=request_identity,
        )

    def visibility_request_receipt(
        self,
        provider_qualification_decision_id: UUID,
        source_kind: str,
        request_identity: str,
    ) -> ReceiptRecord | None:
        if source_kind not in {
            "MARKET_BAR_REVISION",
            "INSTRUMENT_FACT_REVISION",
            "CLASSIFICATION_MEMBERSHIP_REVISION",
            "TRADING_SESSION",
            "SOURCE_GAP",
        }:
            raise ValueError("unsupported qualified visibility source kind")
        return self._request_receipt(
            command_kind=f"ADMIT_QUALIFIED_{source_kind}",
            scope_id=str(provider_qualification_decision_id),
            request_identity=request_identity,
        )

    def _request_receipt(
        self,
        *,
        command_kind: str,
        scope_id: str,
        request_identity: str,
    ) -> ReceiptRecord | None:
        row = self._connection.execute(
            """
            SELECT receipt_id, status, request_hash,
                   result_aggregate_kind, result_aggregate_id,
                   result_aggregate_version, result_hash, error_code
            FROM mra.command_receipt
            WHERE command_kind = %s
              AND scope_id = %s
              AND idempotency_key = %s
            """,
            (command_kind, scope_id, request_identity),
        ).fetchone()
        if row is None:
            return None
        return ReceiptRecord(
            receipt_id=UUID(str(row[0])),
            status=str(row[1]),
            request_hash=str(row[2]),
            result_aggregate_kind=(str(row[3]) if row[3] is not None else None),
            result_aggregate_id=(str(row[4]) if row[4] is not None else None),
            result_aggregate_version=(int(row[5]) if row[5] is not None else None),
            result_hash=(str(row[6]) if row[6] is not None else None),
            error_code=(str(row[7]) if row[7] is not None else None),
            is_new=False,
        )

    def insert_protocol(
        self,
        protocol: ProviderQualificationProtocol,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ProviderQualificationProtocolRecord:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"mra:provider-qualification-protocol:{protocol.protocol_code}",),
        )
        product = self._connection.execute(
            """
            SELECT bar_timeframes, price_bases
            FROM mra.provider_product
            WHERE provider_product_id = %s
            FOR SHARE
            """,
            (protocol.provider_product_id,),
        ).fetchone()
        if product is None:
            raise RuntimeNotFoundError("Provider qualification Product does not exist")
        if protocol.timeframe.value not in product[0] or protocol.price_basis.value not in product[1]:
            raise RuntimeStateConflictError(
                "Provider qualification scope exceeds ProviderProduct capabilities"
            )
        self._require_artifact(protocol.code_artifact)
        self._require_artifact(protocol.config_artifact)
        for requirement in protocol.requirements:
            self._connection.execute(
                """
                INSERT INTO mra.provider_qualification_requirement (
                    provider_qualification_requirement_id,
                    provider_qualification_protocol_id, ordinal,
                    requirement_kind, minimum_observation_count,
                    minimum_ratio, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    requirement.provider_qualification_requirement_id,
                    protocol.provider_qualification_protocol_id,
                    requirement.ordinal,
                    requirement.requirement_kind.value,
                    requirement.minimum_observation_count,
                    requirement.minimum_ratio,
                    str(requirement.content_sha256),
                ),
            )
        self._connection.execute(
            """
            INSERT INTO mra.provider_qualification_protocol (
                provider_qualification_protocol_id, protocol_code, revision,
                supersedes_protocol_id, provider_product_id, purpose,
                evidence_class, market_scope, instrument_scope, exchange_code,
                timeframe, price_basis, decision_time_rule,
                capture_window_start, capture_window_end, evidence_cutoff,
                outcome_path_sessions, requirement_count,
                requirement_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                protocol.provider_qualification_protocol_id,
                protocol.protocol_code,
                protocol.revision,
                protocol.supersedes_protocol_id,
                protocol.provider_product_id,
                protocol.purpose.value,
                protocol.evidence_class.value,
                protocol.market_scope,
                protocol.instrument_scope,
                protocol.exchange_code,
                protocol.timeframe.value,
                protocol.price_basis.value,
                protocol.decision_time_rule,
                protocol.capture_window_start,
                protocol.capture_window_end,
                protocol.evidence_cutoff,
                protocol.outcome_path_sessions,
                protocol.requirement_count,
                str(protocol.requirement_roster_sha256),
                protocol.code_artifact.artifact_id,
                str(protocol.code_artifact.content_sha256),
                protocol.code_artifact.size_bytes,
                protocol.config_artifact.artifact_id,
                str(protocol.config_artifact.content_sha256),
                protocol.config_artifact.size_bytes,
                str(protocol.provenance_sha256),
                str(protocol.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        return self.protocol_record(
            protocol.provider_qualification_protocol_id,
            lock=False,
        )

    def protocol_record(
        self, provider_qualification_protocol_id: UUID, *, lock: bool
    ) -> ProviderQualificationProtocolRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT provider_qualification_protocol_id, protocol_code,
                   revision, provider_product_id, purpose, evidence_class,
                   requirement_count, requirement_roster_sha256,
                   content_sha256, registered_at
            FROM mra.provider_qualification_protocol
            WHERE provider_qualification_protocol_id = %s
            """
            + suffix,
            (provider_qualification_protocol_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Provider qualification Protocol does not exist")
        return ProviderQualificationProtocolRecord(
            provider_qualification_protocol_id=UUID(str(row[0])),
            protocol_code=str(row[1]),
            revision=int(row[2]),
            provider_product_id=UUID(str(row[3])),
            purpose=str(row[4]),
            evidence_class=str(row[5]),
            requirement_count=int(row[6]),
            requirement_roster_sha256=str(row[7]),
            content_sha256=str(row[8]),
            registered_at=row[9],
        )

    def insert_finality_observation(
        self, observation: ProviderFinalityObservation
    ) -> int:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"mra:provider-finality:{observation.capture_id}",),
        )
        self._require_artifact(observation.code_artifact)
        self._require_artifact(observation.config_artifact)
        if observation.observation_ordinal > 1:
            predecessor = self._connection.execute(
                """
                SELECT capture_id, observation_ordinal, recorded_at
                FROM mra.provider_finality_observation
                WHERE provider_finality_observation_id = %s
                FOR SHARE
                """,
                (observation.supersedes_observation_id,),
            ).fetchone()
            if (
                predecessor is None
                or UUID(str(predecessor[0])) != observation.capture_id
                or int(predecessor[1]) + 1 != observation.observation_ordinal
                or predecessor[2] >= observation.publication_observed_at
            ):
                raise RuntimeStateConflictError(
                    "Provider finality observation supersession is invalid"
                )
        row = self._connection.execute(
            """
            INSERT INTO mra.provider_finality_observation (
                provider_finality_observation_id, capture_id,
                observation_ordinal, supersedes_observation_id,
                finality_status, publication_observed_at,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING observation_ordinal
            """,
            (
                observation.provider_finality_observation_id,
                observation.capture_id,
                observation.observation_ordinal,
                observation.supersedes_observation_id,
                observation.finality_status.value,
                observation.publication_observed_at,
                observation.code_artifact.artifact_id,
                str(observation.code_artifact.content_sha256),
                observation.code_artifact.size_bytes,
                observation.config_artifact.artifact_id,
                str(observation.config_artifact.content_sha256),
                observation.config_artifact.size_bytes,
                str(observation.provenance_sha256),
                str(observation.content_sha256),
            ),
        ).fetchone()
        if row is None:
            raise AssertionError("Provider finality observation insert returned no row")
        return int(row[0])

    def complete(
        self,
        *,
        provider_qualification_decision_id: UUID,
        decision_code: str,
        provider_qualification_protocol_id: UUID,
        request_identity: str,
        request_sha256: str,
    ) -> ProviderQualificationDecisionRecord:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"mra:provider-qualification-decision:{provider_qualification_protocol_id}",),
        )
        protocol = self._protocol_details(provider_qualification_protocol_id)
        captures = self._capture_roster(protocol)
        if not captures:
            raise RuntimeStateConflictError(
                "Provider qualification capture roster cannot be empty"
            )
        evaluations = self._evaluate_requirements(protocol, captures)
        if any(item.result_status == "REJECTED" for item in evaluations):
            status = "REJECTED"
            reason = "PROVIDER_REQUIREMENT_REJECTED"
        elif protocol["evidence_class"] == "ENGINEERING_REHEARSAL" or any(
            item.result_status == "INCONCLUSIVE" for item in evaluations
        ):
            status = "INCONCLUSIVE"
            reason = "PROVIDER_EVIDENCE_INCONCLUSIVE"
        else:
            status = "ADMITTED"
            reason = "ALL_PROVIDER_REQUIREMENTS_SATISFIED"
        capture_hash = canonical_json_sha256(
            [
                {
                    "capture_id": item.capture_id,
                    "content_sha256": item.content_sha256,
                    "ordinal": item.member_ordinal,
                }
                for item in captures
            ]
        )
        result_hash = canonical_json_sha256(
            [
                {
                    "content_sha256": item.content_sha256,
                    "ordinal": item.result_ordinal,
                    "requirement_kind": item.requirement_kind,
                }
                for item in evaluations
            ]
        )
        content_hash = canonical_json_sha256(
            {
                "capture_count": len(captures),
                "capture_roster_sha256": capture_hash,
                "decision_code": decision_code,
                "decision_status": status,
                "evidence_class": protocol["evidence_class"],
                "protocol_content_sha256": protocol["content_sha256"],
                "provider_product_id": protocol["provider_product_id"],
                "purpose": protocol["purpose"],
                "reason_code": reason,
                "requirement_result_count": len(evaluations),
                "requirement_result_roster_sha256": result_hash,
            }
        )
        for capture_member in captures:
            self._insert_capture_member(
                provider_qualification_decision_id,
                capture_member,
            )
        for evaluation in evaluations:
            self._insert_requirement_result(
                provider_qualification_decision_id,
                provider_qualification_protocol_id,
                evaluation,
            )
        self._connection.execute(
            """
            INSERT INTO mra.provider_qualification_decision (
                provider_qualification_decision_id, decision_code,
                provider_qualification_protocol_id, provider_product_id,
                purpose, evidence_class, protocol_content_sha256,
                decision_status, capture_count, capture_roster_sha256,
                requirement_result_count, requirement_result_roster_sha256,
                reason_code, content_sha256, request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                provider_qualification_decision_id,
                decision_code,
                provider_qualification_protocol_id,
                protocol["provider_product_id"],
                protocol["purpose"],
                protocol["evidence_class"],
                protocol["content_sha256"],
                status,
                len(captures),
                capture_hash,
                len(evaluations),
                result_hash,
                reason,
                content_hash,
                request_identity,
                request_sha256,
            ),
        )
        return self.decision_record(provider_qualification_decision_id, lock=False)

    def decision_record(
        self, provider_qualification_decision_id: UUID, *, lock: bool
    ) -> ProviderQualificationDecisionRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT provider_qualification_decision_id, decision_code,
                   provider_qualification_protocol_id, provider_product_id,
                   purpose, evidence_class, decision_status, capture_count,
                   capture_roster_sha256, requirement_result_count,
                   requirement_result_roster_sha256, reason_code,
                   content_sha256, decided_at
            FROM mra.provider_qualification_decision
            WHERE provider_qualification_decision_id = %s
            """
            + suffix,
            (provider_qualification_decision_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Provider qualification Decision does not exist")
        return ProviderQualificationDecisionRecord(
            provider_qualification_decision_id=UUID(str(row[0])),
            decision_code=str(row[1]),
            provider_qualification_protocol_id=UUID(str(row[2])),
            provider_product_id=UUID(str(row[3])),
            purpose=str(row[4]),
            evidence_class=str(row[5]),
            decision_status=str(row[6]),
            capture_count=int(row[7]),
            capture_roster_sha256=str(row[8]),
            requirement_result_count=int(row[9]),
            requirement_result_roster_sha256=str(row[10]),
            reason_code=str(row[11]),
            content_sha256=str(row[12]),
            decided_at=row[13],
        )

    def reconcile_protocol(self, provider_qualification_protocol_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT protocol.requirement_count = count(requirement.*)
               AND min(requirement.ordinal) = 1
               AND max(requirement.ordinal) = protocol.requirement_count
               AND count(DISTINCT requirement.requirement_kind) = 10
            FROM mra.provider_qualification_protocol protocol
            JOIN mra.provider_qualification_requirement requirement
              USING (provider_qualification_protocol_id)
            WHERE protocol.provider_qualification_protocol_id = %s
            GROUP BY protocol.requirement_count
            """,
            (provider_qualification_protocol_id,),
        ).fetchone()
        return row is not None and row[0] is True

    def reconcile_decision(self, provider_qualification_decision_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT decision.capture_count = count(DISTINCT member.provider_qualification_capture_member_id)
               AND decision.requirement_result_count = count(DISTINCT result.provider_qualification_requirement_result_id)
               AND decision.requirement_result_count = protocol.requirement_count
            FROM mra.provider_qualification_decision decision
            JOIN mra.provider_qualification_protocol protocol USING (provider_qualification_protocol_id)
            JOIN mra.provider_qualification_capture_member member USING (provider_qualification_decision_id)
            JOIN mra.provider_qualification_requirement_result result USING (provider_qualification_decision_id)
            WHERE decision.provider_qualification_decision_id = %s
            GROUP BY decision.capture_count, decision.requirement_result_count,
                     protocol.requirement_count
            """,
            (provider_qualification_decision_id,),
        ).fetchone()
        return row is not None and row[0] is True

    def _require_artifact(self, binding: Any) -> None:
        row = self._connection.execute(
            """
            SELECT content_sha256, size_bytes,
                   mra.artifact_has_verified_integrity(
                       integrity_state, last_verified_at
                   )
            FROM mra.artifact WHERE artifact_id = %s FOR SHARE
            """,
            (binding.artifact_id,),
        ).fetchone()
        if row != (
            str(binding.content_sha256),
            binding.size_bytes,
            True,
        ):
            raise ArtifactIntegrityError(
                "Provider qualification Artifact lacks exact verified identity"
            )

    def _protocol_details(self, protocol_id: UUID) -> dict[str, Any]:
        row = self._connection.execute(
            """
            SELECT provider_product_id, purpose, evidence_class,
                   exchange_code, timeframe, price_basis,
                   capture_window_start, capture_window_end, evidence_cutoff,
                   outcome_path_sessions, requirement_count, content_sha256
            FROM mra.provider_qualification_protocol
            WHERE provider_qualification_protocol_id = %s
            FOR SHARE
            """,
            (protocol_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Provider qualification Protocol does not exist")
        return {
            "provider_qualification_protocol_id": protocol_id,
            "provider_product_id": UUID(str(row[0])),
            "purpose": str(row[1]),
            "evidence_class": str(row[2]),
            "exchange_code": str(row[3]),
            "timeframe": str(row[4]),
            "price_basis": str(row[5]),
            "capture_window_start": row[6],
            "capture_window_end": row[7],
            "evidence_cutoff": row[8],
            "outcome_path_sessions": int(row[9]),
            "requirement_count": int(row[10]),
            "content_sha256": str(row[11]),
        }

    def _capture_roster(
        self, protocol: dict[str, Any]
    ) -> tuple[ProviderQualificationCaptureMember, ...]:
        rows = self._connection.execute(
            """
            SELECT capture.capture_id, capture.provider_product_id,
                   capture.status, capture.artifact_id,
                   capture.source_availability_status,
                   capture.source_available_at, capture.known_at,
                   EXISTS (
                     SELECT 1 FROM mra.command_receipt receipt
                     JOIN mra.runtime_step step ON step.step_id = receipt.runtime_step_id
                     JOIN mra.runtime_run run ON run.run_id = step.run_id
                     WHERE receipt.command_kind = 'CAPTURE_MARKET_DATA'
                       AND receipt.status = 'SUCCEEDED'
                       AND receipt.result_aggregate_kind = 'DATA_CAPTURE'
                       AND receipt.result_aggregate_id = capture.capture_id::text
                       AND step.step_kind = 'CAPTURE'
                       AND run.runtime_mode IN ('OPERATIONAL', 'SHADOW', 'PROSPECTIVE')
                   ) AS runtime_lineage,
                   CASE WHEN capture.status = 'PROVIDER_FAILURE' THEN true
                     ELSE artifact.integrity_state = 'AVAILABLE'
                       AND EXISTS (
                         SELECT 1 FROM mra.command_receipt receipt
                         JOIN mra.artifact_verification verification
                           ON verification.command_receipt_id = receipt.receipt_id
                         WHERE receipt.result_aggregate_kind = 'DATA_CAPTURE'
                           AND receipt.result_aggregate_id = capture.capture_id::text
                           AND verification.artifact_id = capture.artifact_id
                           AND verification.result = 'VERIFIED'
                       ) END AS artifact_verified,
                   (SELECT count(*) FROM mra.source_gap gap
                    WHERE gap.capture_id = capture.capture_id) AS gap_count
            FROM mra.data_capture capture
            LEFT JOIN mra.artifact artifact ON artifact.artifact_id = capture.artifact_id
            WHERE capture.provider_product_id = %(provider_product_id)s
              AND capture.capture_started_at >= %(capture_window_start)s
              AND capture.capture_started_at < %(capture_window_end)s
              AND capture.known_at <= %(evidence_cutoff)s
            ORDER BY capture.capture_started_at, capture.capture_id
            FOR SHARE OF capture
            """,
            protocol,
        ).fetchall()
        members = []
        for ordinal, row in enumerate(rows, start=1):
            payload = {
                "artifact_id": UUID(str(row[3])) if row[3] is not None else None,
                "artifact_verified": row[8] is True,
                "capture_id": UUID(str(row[0])),
                "capture_status": str(row[2]),
                "known_at": row[6],
                "member_ordinal": ordinal,
                "provider_product_id": UUID(str(row[1])),
                "runtime_capture_lineage": row[7] is True,
                "source_availability_status": str(row[4]),
                "source_available_at": row[5],
                "source_gap_count": int(row[9]),
            }
            members.append(
                ProviderQualificationCaptureMember(
                    provider_qualification_capture_member_id=self._id_factory(),
                    content_sha256=canonical_json_sha256(payload),
                    **payload,
                )
            )
        return tuple(members)

    def _evaluate_requirements(
        self,
        protocol: dict[str, Any],
        captures: tuple[ProviderQualificationCaptureMember, ...],
    ) -> tuple[ProviderRequirementEvaluation, ...]:
        requirements = self._connection.execute(
            """
            SELECT provider_qualification_requirement_id, ordinal,
                   requirement_kind, minimum_observation_count, minimum_ratio
            FROM mra.provider_qualification_requirement
            WHERE provider_qualification_protocol_id = %s
            ORDER BY ordinal
            FOR SHARE
            """,
            (protocol["provider_qualification_protocol_id"],),
        ).fetchall()
        captured = tuple(item for item in captures if item.capture_status == "CAPTURED")
        counts = self._fact_counts(protocol)
        evaluations: list[ProviderRequirementEvaluation] = []
        for requirement_id, ordinal, kind_raw, minimum_count, minimum_ratio in requirements:
            kind = ProviderRequirementKind(str(kind_raw))
            observation_count, satisfied_count, missing_is_inconclusive = self._measure(
                kind,
                captures=captures,
                captured=captured,
                counts=counts,
                protocol=protocol,
            )
            ratio = (
                Decimal(satisfied_count) / Decimal(observation_count)
                if observation_count
                else Decimal(0)
            ).quantize(Decimal("0.0000000001"))
            if observation_count < int(minimum_count):
                status = "INCONCLUSIVE" if missing_is_inconclusive else "REJECTED"
                reason = "INSUFFICIENT_PROVIDER_OBSERVATIONS"
            elif ratio < Decimal(minimum_ratio):
                status = "REJECTED"
                reason = "PROVIDER_REQUIREMENT_THRESHOLD_FAILED"
            else:
                status = "SATISFIED"
                reason = "PROVIDER_REQUIREMENT_SATISFIED"
            payload = {
                "observation_count": observation_count,
                "observed_ratio": ratio,
                "reason_code": reason,
                "requirement_kind": kind.value,
                "result_ordinal": int(ordinal),
                "result_status": status,
                "satisfied_count": satisfied_count,
            }
            evaluations.append(
                ProviderRequirementEvaluation(
                    provider_qualification_requirement_result_id=self._id_factory(),
                    provider_qualification_requirement_id=UUID(str(requirement_id)),
                    content_sha256=canonical_json_sha256(payload),
                    result_ordinal=int(ordinal),
                    requirement_kind=kind.value,
                    result_status=status,
                    observation_count=observation_count,
                    satisfied_count=satisfied_count,
                    observed_ratio=ratio,
                    reason_code=reason,
                )
            )
        return tuple(evaluations)

    def _fact_counts(self, protocol: dict[str, Any]) -> dict[str, int]:
        row = self._connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.trading_session session
               JOIN mra.data_capture capture ON capture.capture_id = session.source_capture_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND session.exchange = %(exchange_code)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s),
              (SELECT count(*) FROM mra.classification_membership_revision membership
               JOIN mra.data_capture capture ON capture.capture_id = membership.source_capture_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s),
              (SELECT count(*) FROM mra.market_bar_revision bar
               JOIN mra.data_capture capture ON capture.capture_id = bar.capture_id
               JOIN mra.trading_session session ON session.session_id = bar.session_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND session.exchange = %(exchange_code)s
                 AND bar.timeframe = %(timeframe)s
                 AND bar.price_basis = %(price_basis)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s),
              (SELECT count(DISTINCT bar.session_id) FROM mra.market_bar_revision bar
               JOIN mra.data_capture capture ON capture.capture_id = bar.capture_id
               JOIN mra.trading_session session ON session.session_id = bar.session_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND session.exchange = %(exchange_code)s
                 AND bar.timeframe = %(timeframe)s
                 AND bar.price_basis = %(price_basis)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s),
              (SELECT count(*) FROM mra.source_gap gap
               JOIN mra.data_capture capture ON capture.capture_id = gap.capture_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s),
              (SELECT count(*) FROM mra.provider_finality_observation observation
               JOIN mra.data_capture capture ON capture.capture_id = observation.capture_id
               WHERE capture.provider_product_id = %(provider_product_id)s
                 AND capture.capture_started_at >= %(capture_window_start)s
                 AND capture.capture_started_at < %(capture_window_end)s
                 AND observation.publication_observed_at <= %(evidence_cutoff)s
                 AND observation.finality_status = 'FINAL'
                 AND NOT EXISTS (
                   SELECT 1 FROM mra.provider_finality_observation newer
                   WHERE newer.capture_id = observation.capture_id
                     AND newer.observation_ordinal > observation.observation_ordinal
                     AND newer.publication_observed_at <= %(evidence_cutoff)s
                 ))
            """,
            protocol,
        ).fetchone()
        if row is None:
            raise AssertionError("Provider qualification fact counts returned no row")
        return {
            "sessions": int(row[0]),
            "memberships": int(row[1]),
            "bars": int(row[2]),
            "bar_sessions": int(row[3]),
            "gaps": int(row[4]),
            "final_captures": int(row[5]),
        }

    def _measure(
        self,
        kind: ProviderRequirementKind,
        *,
        captures: tuple[ProviderQualificationCaptureMember, ...],
        captured: tuple[ProviderQualificationCaptureMember, ...],
        counts: dict[str, int],
        protocol: dict[str, Any],
    ) -> tuple[int, int, bool]:
        if kind is ProviderRequirementKind.COVERAGE:
            return len(captures), len(captured), False
        if kind is ProviderRequirementKind.RAW_SOURCE_LINEAGE:
            return len(captures), sum(
                item.runtime_capture_lineage and item.artifact_verified
                for item in captures
            ), False
        if kind is ProviderRequirementKind.HISTORICAL_AVAILABILITY:
            return len(captured), sum(
                item.source_availability_status == "PROVIDER_REPORTED"
                and item.source_available_at is not None
                for item in captured
            ), True
        if kind is ProviderRequirementKind.KNOWN_TIME:
            return len(captures), len(captures), False
        if kind is ProviderRequirementKind.REVISION_FINALITY:
            return len(captured), counts["final_captures"], True
        if kind is ProviderRequirementKind.PRICE_BASIS:
            return 1, 1, False
        if kind is ProviderRequirementKind.TRADING_CALENDAR:
            return counts["sessions"], counts["sessions"], True
        if kind is ProviderRequirementKind.MEMBERSHIP_STATUS:
            return counts["memberships"], counts["memberships"], True
        if kind is ProviderRequirementKind.DECISION_REFERENCE:
            return counts["bars"], counts["bars"], True
        if kind is ProviderRequirementKind.OUTCOME_PATH:
            required = int(protocol["outcome_path_sessions"])
            return required, min(counts["bar_sessions"], required), True
        raise AssertionError("unknown Provider requirement")

    def _insert_capture_member(
        self,
        decision_id: UUID,
        member: ProviderQualificationCaptureMember,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.provider_qualification_capture_member (
                provider_qualification_capture_member_id,
                provider_qualification_decision_id, member_ordinal,
                capture_id, provider_product_id, capture_status, artifact_id,
                source_availability_status, source_available_at, known_at,
                runtime_capture_lineage, artifact_verified, source_gap_count,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                member.provider_qualification_capture_member_id,
                decision_id,
                member.member_ordinal,
                member.capture_id,
                member.provider_product_id,
                member.capture_status,
                member.artifact_id,
                member.source_availability_status,
                member.source_available_at,
                member.known_at,
                member.runtime_capture_lineage,
                member.artifact_verified,
                member.source_gap_count,
                member.content_sha256,
            ),
        )

    def admit_market_bar_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        bar_revision_id: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        return self._admit_visibility(
            qualified_visibility_id,
            provider_decision_id,
            source_kind="MARKET_BAR_REVISION",
            source_identity=bar_revision_id,
        )

    def admit_instrument_fact_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        fact_revision_id: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        return self._admit_visibility(
            qualified_visibility_id,
            provider_decision_id,
            source_kind="INSTRUMENT_FACT_REVISION",
            source_identity=fact_revision_id,
        )

    def admit_classification_membership_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        membership_revision_id: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        return self._admit_visibility(
            qualified_visibility_id,
            provider_decision_id,
            source_kind="CLASSIFICATION_MEMBERSHIP_REVISION",
            source_identity=membership_revision_id,
        )

    def admit_trading_session_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        session_id: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        return self._admit_visibility(
            qualified_visibility_id,
            provider_decision_id,
            source_kind="TRADING_SESSION",
            source_identity=session_id,
        )

    def admit_source_gap_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        gap_id: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        return self._admit_visibility(
            qualified_visibility_id,
            provider_decision_id,
            source_kind="SOURCE_GAP",
            source_identity=gap_id,
        )

    def _admit_visibility(
        self,
        qualified_visibility_id: UUID,
        provider_decision_id: UUID,
        *,
        source_kind: str,
        source_identity: UUID,
    ) -> QualifiedHistoricalVisibilityRecord:
        mapping = {
            "MARKET_BAR_REVISION": (
                "qualified_market_bar_visibility",
                "qualified_market_bar_visibility_id",
                "market_bar_revision",
                "bar_revision_id",
                "capture_id",
            ),
            "INSTRUMENT_FACT_REVISION": (
                "qualified_instrument_fact_visibility",
                "qualified_instrument_fact_visibility_id",
                "instrument_fact_revision",
                "fact_revision_id",
                "capture_id",
            ),
            "CLASSIFICATION_MEMBERSHIP_REVISION": (
                "qualified_classification_membership_visibility",
                "qualified_classification_membership_visibility_id",
                "classification_membership_revision",
                "membership_revision_id",
                "source_capture_id",
            ),
            "TRADING_SESSION": (
                "qualified_trading_session_visibility",
                "qualified_trading_session_visibility_id",
                "trading_session",
                "session_id",
                "source_capture_id",
            ),
            "SOURCE_GAP": (
                "qualified_source_gap_visibility",
                "qualified_source_gap_visibility_id",
                "source_gap",
                "gap_id",
                "capture_id",
            ),
        }
        target = mapping.get(source_kind)
        if target is None:
            raise AssertionError("unknown qualified visibility kind")
        table, visibility_column, source_table, source_column, capture_column = target
        source = self._connection.execute(
            f"""
            SELECT source.{capture_column},
                   mra.canonical_sha256(
                       mra.canonical_json_text(to_jsonb(source))),
                   member.source_available_at
            FROM mra.{source_table} AS source
            JOIN mra.provider_qualification_capture_member AS member
              ON member.capture_id = source.{capture_column}
             AND member.provider_qualification_decision_id = %s
            WHERE source.{source_column} = %s
            FOR SHARE OF source, member
            """,  # noqa: S608 -- closed source-specific mapping above
            (provider_decision_id, source_identity),
        ).fetchone()
        if source is None or source[2] is None:
            raise RuntimeStateConflictError(
                "source is absent from the qualified complete Capture roster"
            )
        capture_id = UUID(str(source[0]))
        source_hash = str(source[1])
        available_at = source[2]
        content = canonical_json_sha256(
            {
                "capture_id": capture_id,
                "provider_qualification_decision_id": provider_decision_id,
                "qualified_decision_visible_at": available_at,
                "source_content_sha256": source_hash,
                "source_identity": source_identity,
                "source_kind": source_kind,
            }
        )
        self._connection.execute(
            f"""
            INSERT INTO mra.{table} (
                {visibility_column}, provider_qualification_decision_id,
                {source_column}, capture_id, source_content_sha256,
                source_available_at, qualified_decision_visible_at,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,  # noqa: S608 -- closed source-specific mapping above
            (
                qualified_visibility_id,
                provider_decision_id,
                source_identity,
                capture_id,
                source_hash,
                available_at,
                available_at,
                content,
            ),
        )
        return self.visibility_record(
            qualified_visibility_id, source_kind=source_kind
        )

    def visibility_record(
        self, qualified_visibility_id: UUID, *, source_kind: str
    ) -> QualifiedHistoricalVisibilityRecord:
        mapping = {
            "MARKET_BAR_REVISION": (
                "qualified_market_bar_visibility",
                "qualified_market_bar_visibility_id",
                "bar_revision_id",
            ),
            "INSTRUMENT_FACT_REVISION": (
                "qualified_instrument_fact_visibility",
                "qualified_instrument_fact_visibility_id",
                "fact_revision_id",
            ),
            "CLASSIFICATION_MEMBERSHIP_REVISION": (
                "qualified_classification_membership_visibility",
                "qualified_classification_membership_visibility_id",
                "membership_revision_id",
            ),
            "TRADING_SESSION": (
                "qualified_trading_session_visibility",
                "qualified_trading_session_visibility_id",
                "session_id",
            ),
            "SOURCE_GAP": (
                "qualified_source_gap_visibility",
                "qualified_source_gap_visibility_id",
                "gap_id",
            ),
        }
        target = mapping.get(source_kind)
        if target is None:
            raise AssertionError("unknown qualified visibility kind")
        table, visibility_column, source_column = target
        row = self._connection.execute(
            f"""
            SELECT {visibility_column}, provider_qualification_decision_id,
                   {source_column}, capture_id, source_content_sha256,
                   qualified_decision_visible_at, content_sha256, admitted_at
            FROM mra.{table} WHERE {visibility_column} = %s
            """,  # noqa: S608 -- closed source-specific mapping above
            (qualified_visibility_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("qualified historical visibility does not exist")
        return QualifiedHistoricalVisibilityRecord(
            qualified_visibility_id=UUID(str(row[0])),
            provider_qualification_decision_id=UUID(str(row[1])),
            source_kind=source_kind,
            source_identity=UUID(str(row[2])),
            capture_id=UUID(str(row[3])),
            source_content_sha256=str(row[4]),
            qualified_decision_visible_at=row[5],
            content_sha256=str(row[6]),
            admitted_at=row[7],
        )

    def _insert_requirement_result(
        self,
        decision_id: UUID,
        protocol_id: UUID,
        result: ProviderRequirementEvaluation,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO mra.provider_qualification_requirement_result (
                provider_qualification_requirement_result_id,
                provider_qualification_decision_id,
                provider_qualification_protocol_id,
                provider_qualification_requirement_id, result_ordinal,
                requirement_kind, result_status, observation_count,
                satisfied_count, observed_ratio, reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.provider_qualification_requirement_result_id,
                decision_id,
                protocol_id,
                result.provider_qualification_requirement_id,
                result.result_ordinal,
                result.requirement_kind,
                result.result_status,
                result.observation_count,
                result.satisfied_count,
                result.observed_ratio,
                result.reason_code,
                result.content_sha256,
            ),
        )


__all__ = ["PostgresProviderQualificationRepository"]
