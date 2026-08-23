"""PostgreSQL owner for target-bound C5 Calibration qualification."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.targets import (
    TargetDefinition,
)

from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    CalibrationPartition,
    CalibrationProtocol,
    fit_calibration,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationDecision,
    CalibrationQualificationPolicy,
    FormalCalibrationObservationBinding,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    load_formal_protocol_owner,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalOOSQualificationDecision,
    QualificationOutcome,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)


class CalibrationQualificationConflict(ValueError):
    """The Calibration owner could not reproduce exact frozen evidence."""


class PostgresCalibrationQualificationAuthority:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_policy(
        self, policy: CalibrationQualificationPolicy
    ) -> CalibrationQualificationPolicy:
        def operation(connection: Any) -> None:
            _verify_policy_owners(connection, policy)
            now = _postgres_now(connection)
            connection.execute(
                """
                INSERT INTO calibration_qualification_policy(
                    policy_id, policy_hash, target_protocol_id, target_id,
                    calibration_protocol_id, payload_json, locked_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (policy_id) DO NOTHING
                """,
                (
                    str(policy.policy_id),
                    policy.policy_hash,
                    str(policy.target_protocol_reference.artifact_id),
                    str(policy.target_reference.artifact_id),
                    str(policy.calibration_protocol_reference.artifact_id),
                    Jsonb(policy.to_canonical_dict()),
                    policy.locked_at,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT policy_hash, payload_json
                FROM calibration_qualification_policy
                WHERE policy_id = %s
                """,
                (str(policy.policy_id),),
            ).fetchone()
            if row is None or str(row[0]) != policy.policy_hash or row[1] != (
                policy.to_canonical_dict()
            ):
                raise CalibrationQualificationConflict(
                    "Calibration Policy identity conflict"
                )

        self._factory.run_transaction(operation)
        return policy

    def bind_formal_observations(
        self,
        *,
        policy: CalibrationQualificationPolicy,
        formal_protocol_id: ArtifactId,
        calibration_artifact_id: ArtifactId,
        bindings: tuple[FormalCalibrationObservationBinding, ...],
    ) -> None:
        if not bindings or tuple(item.observation_id for item in bindings) != tuple(
            sorted({item.observation_id for item in bindings})
        ):
            raise CalibrationQualificationConflict(
                "Formal Calibration bindings must be non-empty, unique and sorted"
            )

        def operation(connection: Any) -> None:
            acquire_scope_lock(
                connection,
                namespace="formal-calibration-observations",
                identity=str(calibration_artifact_id),
            )
            _require_recorded_policy(connection, policy)
            protocol = _load_formal_protocol(connection, formal_protocol_id)
            _verify_protocol_policy(protocol, policy)
            expected_partitions = _load_engineering_partitions(
                connection, calibration_artifact_id
            )
            if tuple(
                (item.observation_id, item.partition) for item in bindings
            ) != expected_partitions:
                raise CalibrationQualificationConflict(
                    "Formal bindings do not equal Calibration Artifact partitions"
                )
            now = _postgres_now(connection)
            for binding in bindings:
                resolved = _resolve_binding(
                    connection,
                    policy=policy,
                    formal_protocol=protocol,
                    binding=binding,
                )
                connection.execute(
                    """
                    INSERT INTO formal_calibration_observation_binding(
                        calibration_artifact_id, observation_id, policy_id,
                        forecast_id, target_settlement_id, label_id,
                        target_id, barrier_id, partition_name, score,
                        binary_outcome, forecast_hash, label_hash,
                        payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (calibration_artifact_id, observation_id)
                    DO NOTHING
                    """,
                    (
                        str(calibration_artifact_id),
                        binding.observation_id,
                        str(policy.policy_id),
                        str(binding.forecast_reference.artifact_id),
                        resolved["settlement_id"],
                        str(binding.label_reference.artifact_id),
                        str(policy.target_reference.artifact_id),
                        policy.barrier_id,
                        binding.partition,
                        resolved["score"],
                        resolved["outcome"],
                        binding.forecast_reference.content_hash,
                        binding.label_reference.content_hash,
                        Jsonb(
                            {
                                **binding.to_canonical_dict(),
                                "target_reference": (
                                    policy.target_reference.to_canonical_dict()
                                ),
                                "barrier_id": policy.barrier_id,
                                "score": str(resolved["score"]),
                                "binary_outcome": resolved["outcome"],
                            }
                        ),
                        now,
                    ),
                )
            _replay_calibration_owner(
                connection,
                policy=policy,
                calibration_artifact_id=calibration_artifact_id,
            )

        self._factory.run_transaction(operation)

    def qualify(
        self,
        *,
        policy: CalibrationQualificationPolicy,
        formal_protocol_id: ArtifactId,
        calibration_artifact_id: ArtifactId | None,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> CalibrationQualificationDecision:
        command = {
            "action": "QUALIFY_CALIBRATION",
            "policy_id": str(policy.policy_id),
            "formal_protocol_id": str(formal_protocol_id),
            "calibration_artifact_id": (
                None
                if calibration_artifact_id is None
                else str(calibration_artifact_id)
            ),
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="calibration-qualification",
                identity=f"{formal_protocol_id}:{policy.policy_id}",
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, decision_id
                FROM calibration_qualification_command
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if str(duplicate[0]) != command_hash:
                    raise CalibrationQualificationConflict(
                        "Calibration qualification idempotency conflict"
                    )
                return ArtifactId(str(duplicate[1]))
            _record_policy_in_transaction(connection, policy)
            protocol = _load_formal_protocol(connection, formal_protocol_id)
            outcome, reasons, formal_oos, artifact_reference = _assess(
                connection,
                policy=policy,
                protocol=protocol,
                calibration_artifact_id=calibration_artifact_id,
            )
            now = _postgres_now(connection)
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM calibration_qualification_decision
                WHERE formal_protocol_id = %s AND policy_id = %s
                ORDER BY revision DESC LIMIT 1
                """,
                (str(formal_protocol_id), str(policy.policy_id)),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else ArtifactId(str(latest[0]))
            decision = CalibrationQualificationDecision.create(
                policy_reference=ValidationArtifactReference(
                    "CALIBRATION_POLICY", policy.policy_id, policy.policy_hash
                ),
                formal_protocol_reference=ValidationArtifactReference(
                    "FORMAL_RESEARCH_PROTOCOL",
                    protocol.protocol_id,
                    protocol.protocol_hash,
                ),
                formal_oos_reference=formal_oos,
                calibration_artifact_reference=artifact_reference,
                outcome=outcome,
                calibrated=outcome is QualificationOutcome.SATISFIED,
                revision=revision,
                supersedes_decision_id=supersedes,
                evaluated_at=now,
                actor=actor,
                reason=reason,
                reason_codes=reasons,
            )
            connection.execute(
                """
                INSERT INTO calibration_qualification_decision(
                    decision_id, decision_hash, policy_id,
                    formal_protocol_id, formal_oos_decision_id,
                    calibration_artifact_id, outcome, calibrated,
                    revision, supersedes_decision_id, payload_json, evaluated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(policy.policy_id),
                    str(protocol.protocol_id),
                    (
                        None
                        if formal_oos is None
                        else str(formal_oos.artifact_id)
                    ),
                    (
                        None
                        if artifact_reference is None
                        else str(artifact_reference.artifact_id)
                    ),
                    outcome.value,
                    decision.calibrated,
                    revision,
                    None if supersedes is None else str(supersedes),
                    Jsonb(decision.to_canonical_dict()),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO calibration_qualification_command(
                    idempotency_key, command_hash, decision_id, created_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    idempotency_key,
                    command_hash,
                    str(decision.decision_id),
                    now,
                ),
            )
            return decision.decision_id

        return self.get(self._factory.run_transaction(operation))

    def get(self, decision_id: ArtifactId) -> CalibrationQualificationDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash
                FROM calibration_qualification_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        decision = CalibrationQualificationDecision.from_canonical_dict(
            _mapping(row[0])
        )
        if decision.decision_hash != str(row[1]):
            raise CalibrationQualificationConflict(
                "Calibration Qualification storage hash mismatch"
            )
        return decision


def _assess(
    connection: Any,
    *,
    policy: CalibrationQualificationPolicy,
    protocol: FormalResearchProtocol,
    calibration_artifact_id: ArtifactId | None,
) -> tuple[
    QualificationOutcome,
    tuple[str, ...],
    ValidationArtifactReference | None,
    ValidationArtifactReference | None,
]:
    if protocol.calibration_policy_reference != ValidationArtifactReference(
        "CALIBRATION_POLICY", policy.policy_id, policy.policy_hash
    ):
        return (
            QualificationOutcome.REJECTED,
            ("CALIBRATION_POLICY_NOT_FROZEN_IN_FORMAL_PROTOCOL",),
            None,
            None,
        )
    oos_row = connection.execute(
        """
        SELECT decision_id, decision_hash, outcome, payload_json
        FROM formal_oos_qualification_decision
        WHERE formal_protocol_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (str(protocol.protocol_id),),
    ).fetchone()
    if oos_row is None:
        return (
            QualificationOutcome.BLOCKED,
            ("FORMAL_OOS_QUALIFICATION_MISSING",),
            None,
            None,
        )
    oos = FormalOOSQualificationDecision.from_canonical_dict(_mapping(oos_row[3]))
    if oos.decision_hash != str(oos_row[1]):
        raise CalibrationQualificationConflict("Formal OOS owner hash mismatch")
    oos_reference = ValidationArtifactReference(
        "FORMAL_OOS_QUALIFICATION_DECISION", oos.decision_id, oos.decision_hash
    )
    if oos.outcome is not QualificationOutcome.SATISFIED:
        return (
            oos.outcome,
            (f"FORMAL_OOS_{oos.outcome.value}",),
            oos_reference,
            None,
        )
    if calibration_artifact_id is None:
        return (
            QualificationOutcome.BLOCKED,
            ("TARGET_BOUND_CALIBRATION_ARTIFACT_MISSING",),
            oos_reference,
            None,
        )
    artifact_row = _load_artifact(connection, calibration_artifact_id)
    artifact_reference = ValidationArtifactReference(
        "CALIBRATION_ARTIFACT",
        calibration_artifact_id,
        str(artifact_row[0]),
    )
    try:
        replayed = _replay_calibration_owner(
            connection,
            policy=policy,
            calibration_artifact_id=calibration_artifact_id,
        )
    except _FormalObservationBindingsMissing:
        return (
            QualificationOutcome.BLOCKED,
            ("OWNER_RESOLVED_CALIBRATION_OBSERVATIONS_MISSING",),
            oos_reference,
            artifact_reference,
        )
    oos_evaluations = tuple(
        item
        for item in replayed.evaluations
        if item.partition is CalibrationPartition.OOS
    )
    if len(oos_evaluations) != 1:
        return (
            QualificationOutcome.NOT_ESTIMABLE,
            ("EXACTLY_ONE_CALIBRATION_OOS_EVALUATION_REQUIRED",),
            oos_reference,
            artifact_reference,
        )
    evaluation = oos_evaluations[0]
    if len(evaluation.observation_ids) < policy.minimum_oos_samples:
        return (
            QualificationOutcome.NOT_ESTIMABLE,
            ("CALIBRATION_OOS_SAMPLE_FLOOR_NOT_MET",),
            oos_reference,
            artifact_reference,
        )
    rejected: set[str] = set()
    if evaluation.brier > policy.maximum_brier:
        rejected.add("CALIBRATION_BRIER_FLOOR_NOT_MET")
    if evaluation.log_loss > policy.maximum_log_loss:
        rejected.add("CALIBRATION_LOG_LOSS_FLOOR_NOT_MET")
    if evaluation.ece > policy.maximum_ece:
        rejected.add("CALIBRATION_ECE_FLOOR_NOT_MET")
    if evaluation.coverage < policy.minimum_coverage:
        rejected.add("CALIBRATION_COVERAGE_FLOOR_NOT_MET")
    if rejected:
        return (
            QualificationOutcome.REJECTED,
            tuple(sorted(rejected)),
            oos_reference,
            artifact_reference,
        )
    return (
        QualificationOutcome.SATISFIED,
        (),
        oos_reference,
        artifact_reference,
    )


class _FormalObservationBindingsMissing(Exception):
    pass


def _replay_calibration_owner(
    connection: Any,
    *,
    policy: CalibrationQualificationPolicy,
    calibration_artifact_id: ArtifactId,
) -> Any:
    artifact_row = _load_artifact(connection, calibration_artifact_id)
    protocol = _load_calibration_protocol(
        connection, policy.calibration_protocol_reference.artifact_id
    )
    rows = connection.execute(
        """
        SELECT observation_id, partition_name, score, binary_outcome
        FROM formal_calibration_observation_binding
        WHERE calibration_artifact_id = %s AND policy_id = %s
        ORDER BY observation_id
        """,
        (str(calibration_artifact_id), str(policy.policy_id)),
    ).fetchall()
    expected = _load_engineering_partitions(connection, calibration_artifact_id)
    if not rows:
        raise _FormalObservationBindingsMissing
    actual = tuple((str(item[0]), str(item[1])) for item in rows)
    if actual != expected:
        raise CalibrationQualificationConflict(
            "Formal Calibration observation set diverges from Artifact partitions"
        )
    observations = tuple(
        CalibrationObservation(
            observation_id=str(item[0]),
            score=Decimal(str(item[2])),
            outcome=int(item[3]),
            partition=CalibrationPartition(str(item[1])),
        )
        for item in rows
    )
    replayed = fit_calibration(
        protocol=protocol,
        observations=observations,
        created_at=artifact_row[2],
    )
    if (
        replayed.artifact_id != calibration_artifact_id
        or replayed.artifact_hash != str(artifact_row[0])
        or replayed.identity_payload() != artifact_row[1]
    ):
        raise CalibrationQualificationConflict(
            "Calibration Artifact diverges from owner-resolved observation replay"
        )
    return replayed


def _resolve_binding(
    connection: Any,
    *,
    policy: CalibrationQualificationPolicy,
    formal_protocol: FormalResearchProtocol,
    binding: FormalCalibrationObservationBinding,
) -> dict[str, Any]:
    forecast = connection.execute(
        """
        SELECT f.forecast_hash, f.symbol, f.decision_time,
               f.target_protocol_id, f.payload_json, e.target_hash,
               e.status, e.payload_json
        FROM outcome_target_bound_forecast f
        JOIN outcome_target_bound_forecast_estimate e
          ON e.forecast_id = f.forecast_id
        WHERE f.forecast_id = %s AND e.target_id = %s
        """,
        (
            str(binding.forecast_reference.artifact_id),
            str(policy.target_reference.artifact_id),
        ),
    ).fetchone()
    if forecast is None or (
        str(forecast[0]) != binding.forecast_reference.content_hash
        or str(forecast[5]) != policy.target_reference.content_hash
        or str(forecast[6]) != "AVAILABLE_FOR_RESEARCH"
        or str(forecast[3]) != str(policy.target_protocol_reference.artifact_id)
    ):
        raise CalibrationQualificationConflict("Forecast/Target owner mismatch")
    label_rows = connection.execute(
        """
        SELECT l.settlement_id, l.label_hash, l.target_protocol_id,
               l.target_id, l.symbol, l.label_interval_start,
               l.label_interval_end, l.availability_status, l.label_json,
               o.shadow_decision_id, d.decision_hash
        FROM targeted_shadow_outcome_label l
        JOIN targeted_shadow_outcome o ON o.settlement_id = l.settlement_id
        JOIN shadow_research_decision d ON d.decision_id = o.shadow_decision_id
        WHERE l.label_id = %s
        """,
        (str(binding.label_reference.artifact_id),),
    ).fetchall()
    exact_labels = tuple(
        label
        for label in label_rows
        if str(label[1]) == binding.label_reference.content_hash
        and str(label[3]) == str(policy.target_reference.artifact_id)
        and str(label[4]) == str(forecast[1])
        and str(label[7]) == "COMPLETE"
        and str(label[2]) == str(forecast[3])
        and str(label[2]) == str(policy.target_protocol_reference.artifact_id)
    )
    if len(exact_labels) != 1:
        raise CalibrationQualificationConflict("Target Outcome Label owner mismatch")
    label = exact_labels[0]
    if forecast[2] >= label[5] or label[6] > _label_available_at(_mapping(label[8])):
        raise CalibrationQualificationConflict("Calibration temporal order is invalid")
    evaluation_protocol = _load_formal_evaluation_protocol(
        connection, formal_protocol.evaluation_protocol_reference.artifact_id
    )
    expected_partition = {
        "FIT": EvaluationPartition.TRAIN,
        "VALIDATION": EvaluationPartition.VALIDATION,
        "OOS": EvaluationPartition.LOCKED_OOS,
    }[binding.partition]
    forecast_date = forecast[2].date()
    matching_windows = tuple(
        item
        for item in evaluation_protocol.windows
        if item.start_date <= forecast_date <= item.end_date
    )
    observed_partitions = {item.partition for item in matching_windows}
    if (
        observed_partitions != {expected_partition}
        or forecast_date not in formal_protocol.frozen_trading_dates
    ):
        raise CalibrationQualificationConflict(
            "Calibration partition is absent or ambiguous in the frozen Formal Evaluation Calendar"
        )
    sources = tuple(
        ValidationArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(_mapping(forecast[4])["source_references"])
    )
    if not any(
        str(item.artifact_id) == str(label[9])
        and item.content_hash == str(label[10])
        for item in sources
    ):
        raise CalibrationQualificationConflict(
            "Forecast and Outcome do not bind the same frozen Decision"
        )
    score = _barrier_score(_mapping(forecast[7]), policy.barrier_id)
    outcome = _barrier_outcome(_mapping(label[8]), policy.barrier_id)
    return {
        "settlement_id": str(label[0]),
        "score": score,
        "outcome": outcome,
    }


def _barrier_score(payload: Mapping[str, Any], barrier_id: str) -> Decimal:
    matches = tuple(
        item
        for item in _sequence(payload["barrier_scores"])
        if str(_mapping(item)["barrier_id"]) == barrier_id
    )
    if len(matches) != 1:
        raise CalibrationQualificationConflict("Forecast barrier score is missing")
    return Decimal(str(_mapping(matches[0])["score"]))


def _barrier_outcome(payload: Mapping[str, Any], barrier_id: str) -> int:
    matches = tuple(
        item
        for item in _sequence(payload["barrier_passages"])
        if str(_mapping(item)["barrier_id"]) == barrier_id
    )
    if len(matches) != 1:
        raise CalibrationQualificationConflict("Outcome barrier label is missing")
    return 0 if _mapping(matches[0])["first_passage_at"] is None else 1


def _label_available_at(payload: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(payload["outcome_available_at"]))


def _load_engineering_partitions(
    connection: Any, calibration_artifact_id: ArtifactId
) -> tuple[tuple[str, str], ...]:
    artifact = _load_artifact(connection, calibration_artifact_id)
    if str(artifact[3]) != "CALIBRATION_ARTIFACT":
        raise CalibrationQualificationConflict("Calibration Artifact kind mismatch")
    rows = connection.execute(
        """
        SELECT observation_id, partition_name
        FROM calibration_partition_binding
        WHERE calibration_artifact_id = %s
        ORDER BY observation_id
        """,
        (str(calibration_artifact_id),),
    ).fetchall()
    return tuple((str(item[0]), str(item[1])) for item in rows)


def _load_artifact(connection: Any, artifact_id: ArtifactId) -> tuple[Any, ...]:
    row = connection.execute(
        """
        SELECT artifact_hash, payload_json, created_at, artifact_kind,
               evidence_authority, qualified, production_authorized
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(artifact_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(artifact_id))
    if canonical_hash(dict(_mapping(row[1]))) != str(row[0]):
        raise CalibrationQualificationConflict("Validation Artifact hash mismatch")
    if bool(row[5]) or bool(row[6]):
        raise CalibrationQualificationConflict("Migration 046 ceiling drift")
    return tuple(row)


def _load_calibration_protocol(
    connection: Any, protocol_id: ArtifactId
) -> CalibrationProtocol:
    row = _load_artifact(connection, protocol_id)
    if str(row[3]) != "CALIBRATION_PROTOCOL":
        raise CalibrationQualificationConflict("Calibration Protocol kind mismatch")
    payload = _mapping(row[1])
    protocol = CalibrationProtocol.create(
        protocol_version=str(payload["protocol_version"]),
        method=CalibrationMethod(str(payload["method"])),
        bin_count=int(payload["bin_count"]),
        minimum_fit_samples=int(payload["minimum_fit_samples"]),
        maximum_iterations=int(payload["maximum_iterations"]),
        learning_rate=Decimal(str(payload["learning_rate"])),
    )
    if protocol.protocol_id != protocol_id or protocol.protocol_hash != str(row[0]):
        raise CalibrationQualificationConflict("Calibration Protocol replay diverged")
    return protocol


def _load_formal_evaluation_protocol(
    connection: Any, protocol_id: ArtifactId
) -> FormalEvaluationProtocol:
    row = _load_artifact(connection, protocol_id)
    if str(row[3]) != "FORMAL_EVALUATION_PROTOCOL":
        raise CalibrationQualificationConflict(
            "Formal Evaluation Protocol kind mismatch"
        )
    protocol = FormalEvaluationProtocol.from_canonical_dict(
        {
            "protocol_id": str(protocol_id),
            "protocol_hash": str(row[0]),
            **dict(_mapping(row[1])),
        }
    )
    return protocol


def _load_formal_protocol(
    connection: Any, protocol_id: ArtifactId
) -> FormalResearchProtocol:
    try:
        return load_formal_protocol_owner(connection, protocol_id)
    except FormalProtocolConflict as exc:
        raise CalibrationQualificationConflict(
            "Formal Protocol owner replay failed"
        ) from exc


def _verify_protocol_policy(
    protocol: FormalResearchProtocol,
    policy: CalibrationQualificationPolicy,
) -> None:
    expected = ValidationArtifactReference(
        "CALIBRATION_POLICY", policy.policy_id, policy.policy_hash
    )
    if protocol.calibration_policy_reference != expected:
        raise CalibrationQualificationConflict(
            "Calibration Policy is not frozen in Formal Protocol"
        )
    if policy.locked_at > protocol.locked_at:
        raise CalibrationQualificationConflict(
            "Calibration Policy was not locked before the Formal Protocol"
        )
    if policy.target_reference not in protocol.target_references:
        raise CalibrationQualificationConflict(
            "Calibration Target is not frozen in Formal Protocol"
        )
    if protocol.outcome_target_protocol_reference != policy.target_protocol_reference:
        raise CalibrationQualificationConflict(
            "Calibration Target Protocol is not frozen in Formal Protocol"
        )


def _verify_policy_owners(
    connection: Any, policy: CalibrationQualificationPolicy
) -> None:
    protocol = _load_calibration_protocol(
        connection, policy.calibration_protocol_reference.artifact_id
    )
    if protocol.protocol_hash != policy.calibration_protocol_reference.content_hash:
        raise CalibrationQualificationConflict("Calibration Protocol owner mismatch")
    target = connection.execute(
        """
        SELECT target_hash, target_json FROM outcome_target_definition
        WHERE protocol_id = %s AND target_id = %s
        """,
        (
            str(policy.target_protocol_reference.artifact_id),
            str(policy.target_reference.artifact_id),
        ),
    ).fetchall()
    exact = tuple(
        item for item in target if str(item[0]) == policy.target_reference.content_hash
    )
    if len(exact) != 1:
        raise CalibrationQualificationConflict("Outcome Target owner mismatch")
    try:
        target_definition = TargetDefinition.from_canonical_dict(
            _mapping(exact[0][1])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationQualificationConflict(
            "Outcome Target owner replay failed"
        ) from exc
    barriers = {item.barrier_id for item in target_definition.barriers}
    if policy.barrier_id not in barriers:
        raise CalibrationQualificationConflict("Calibration barrier is not in Target")


def _record_policy_in_transaction(
    connection: Any, policy: CalibrationQualificationPolicy
) -> None:
    _verify_policy_owners(connection, policy)
    now = _postgres_now(connection)
    connection.execute(
        """
        INSERT INTO calibration_qualification_policy(
            policy_id, policy_hash, target_protocol_id, target_id,
            calibration_protocol_id,
            payload_json, locked_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (policy_id) DO NOTHING
        """,
        (
            str(policy.policy_id),
            policy.policy_hash,
            str(policy.target_protocol_reference.artifact_id),
            str(policy.target_reference.artifact_id),
            str(policy.calibration_protocol_reference.artifact_id),
            Jsonb(policy.to_canonical_dict()),
            policy.locked_at,
            now,
        ),
    )
    _require_recorded_policy(connection, policy)


def _require_recorded_policy(
    connection: Any, policy: CalibrationQualificationPolicy
) -> None:
    row = connection.execute(
        """
        SELECT policy_hash, payload_json
        FROM calibration_qualification_policy WHERE policy_id = %s
        """,
        (str(policy.policy_id),),
    ).fetchone()
    if row is None or (
        str(row[0]) != policy.policy_hash
        or row[1] != policy.to_canonical_dict()
    ):
        raise CalibrationQualificationConflict("Calibration Policy owner mismatch")


def _postgres_now(connection: Any) -> datetime:
    return connection.execute(
        "SELECT date_trunc('second', clock_timestamp())"
    ).fetchone()[0]


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationQualificationConflict(
            "Calibration owner payload is not an object"
        )
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise CalibrationQualificationConflict(
            "Calibration owner payload is not an array"
        )
    return tuple(value)


__all__ = [
    "CalibrationQualificationConflict",
    "PostgresCalibrationQualificationAuthority",
]
