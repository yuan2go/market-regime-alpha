"""Operational, exploratory calibration over frozen PathForecast exposures.

The operator never converts a Forecast score into a probability by assertion.
It resolves immutable Panel/Forecast/Target Outcome rows from PostgreSQL,
partitions by trading date with label-aware purging, and only then invokes the
existing calibration methods.  Every produced artifact remains unqualified and
``calibrated=false``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    CalibrationPartition,
    CalibrationProtocol,
    fit_calibration,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


PATH_CALIBRATION_SCORE_FACTOR = "forecast.return_quantile.0.5"


@dataclass(frozen=True, slots=True)
class _ResolvedCalibrationObservation:
    trading_date: date
    label_end_date: date
    label_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference
    barrier_id: str
    observation_id: str
    score: Decimal
    outcome: int
    panel_reference: ValidationArtifactReference
    forecast_reference: ValidationArtifactReference


class PostgresPathForecastCalibrationOperator:
    """Fit multi-target engineering calibration from PostgreSQL owner facts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        repository: PostgresResearchValidationRepository | None = None,
    ) -> None:
        self._factory = factory
        self._repository = repository or PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )

    def run(
        self,
        *,
        target_protocol: OutcomeTargetProtocol,
        through_date: date,
        created_at: datetime,
        method: CalibrationMethod = CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples: int = 30,
        minimum_validation_samples: int = 10,
        score_factor_id: str = PATH_CALIBRATION_SCORE_FACTOR,
    ) -> dict[str, Any]:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("Path calibration created_at must be timezone-aware")
        if minimum_fit_samples <= 0 or minimum_validation_samples <= 0:
            raise ValueError("Path calibration sample floors must be positive")
        resolved = self._load_observations(
            target_protocol=target_protocol,
            through_date=through_date,
            created_at=created_at,
            score_factor_id=score_factor_id,
        )
        by_hypothesis: dict[
            tuple[str, str], list[_ResolvedCalibrationObservation]
        ] = {}
        for item in resolved:
            by_hypothesis.setdefault(
                (str(item.target_reference.artifact_id), item.barrier_id),
                [],
            ).append(item)

        target_by_id = {
            str(item.target_id): item for item in target_protocol.targets
        }
        results: list[dict[str, Any]] = []
        fitted_count = 0
        for target_id, target in sorted(target_by_id.items()):
            target_reference = ValidationArtifactReference(
                "OUTCOME_TARGET",
                target.target_id,
                target.target_hash,
            )
            for barrier in target.barriers:
                protocol = CalibrationProtocol.create(
                    protocol_version=(
                        "path-forecast-multi-target-engineering-v1:"
                        f"{target_id}:{barrier.barrier_id}:{score_factor_id}"
                    ),
                    method=method,
                    minimum_fit_samples=minimum_fit_samples,
                )
                self._repository.record_calibration_protocol(
                    protocol,
                    recorded_at=created_at,
                )
                values = tuple(
                    sorted(
                        by_hypothesis.get((target_id, barrier.barrier_id), ()),
                        key=lambda item: (
                            item.trading_date,
                            item.observation_id,
                        ),
                    )
                )
                partitioned, partition_reasons = _partition_observations(
                    values,
                    minimum_fit_samples=minimum_fit_samples,
                    minimum_validation_samples=minimum_validation_samples,
                )
                if partitioned is None:
                    if not values:
                        partition_reasons = tuple(
                            sorted(
                                {
                                    *partition_reasons,
                                    "NOT_ESTIMABLE_TARGET_BOUND_PATH_FORECAST_MISSING",
                                }
                            )
                        )
                    results.append(
                        self._record_hypothesis(
                            target_protocol=target_protocol,
                            target_reference=target_reference,
                            barrier_id=barrier.barrier_id,
                            protocol=protocol,
                            resolved=values,
                            observations=(),
                            calibration_artifact_id=None,
                            through_date=through_date,
                            score_factor_id=score_factor_id,
                            created_at=created_at,
                            status="NOT_ESTIMABLE",
                            reason_codes=partition_reasons,
                        )
                    )
                    continue
                artifact = fit_calibration(
                    protocol=protocol,
                    observations=partitioned,
                    created_at=created_at,
                )
                self._repository.record_calibration(
                    protocol=protocol,
                    artifact=artifact,
                    observations=partitioned,
                )
                fitted_count += 1
                results.append(
                    self._record_hypothesis(
                        target_protocol=target_protocol,
                        target_reference=target_reference,
                        barrier_id=barrier.barrier_id,
                        protocol=protocol,
                        resolved=values,
                        observations=partitioned,
                        calibration_artifact_id=artifact.artifact_id,
                        through_date=through_date,
                        score_factor_id=score_factor_id,
                        created_at=created_at,
                        status="FITTED_ENGINEERING_ONLY",
                        reason_codes=(
                            "CALIBRATED_FALSE",
                            "FORMAL_OOS_FALSE",
                            "PATH_FORECAST_SCORE_CALIBRATION_FITTED",
                        ),
                    )
                )
        status = (
            "NOT_ESTIMABLE"
            if fitted_count == 0
            else "FITTED_ENGINEERING_ONLY"
            if fitted_count == len(results)
            else "PARTIAL_ENGINEERING_ONLY"
        )
        return {
            "operation": "PATH_FORECAST_MULTI_TARGET_CALIBRATION",
            "status": status,
            "target_protocol_id": str(target_protocol.protocol_id),
            "through_date": through_date.isoformat(),
            "score_factor_id": score_factor_id,
            "hypothesis_count": len(results),
            "fitted_count": fitted_count,
            "hypotheses": results,
            "calibrated": False,
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
            "limitations": [
                "BACKFILLED_FREE_DATA_NOT_FORMAL_PIT",
                "CALIBRATED_FALSE",
                "FREE_DATA_EXPLORATORY",
                "NO_TARGET_SELECTED_AS_WINNER",
                "NO_TRADING_AUTHORITY",
            ],
        }

    def _record_hypothesis(
        self,
        *,
        target_protocol: OutcomeTargetProtocol,
        target_reference: ValidationArtifactReference,
        barrier_id: str,
        protocol: CalibrationProtocol,
        resolved: tuple[_ResolvedCalibrationObservation, ...],
        observations: tuple[CalibrationObservation, ...],
        calibration_artifact_id: ArtifactId | None,
        through_date: date,
        score_factor_id: str,
        created_at: datetime,
        status: str,
        reason_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        payload = _hypothesis_payload(
            target_protocol=target_protocol,
            target_reference=target_reference,
            barrier_id=barrier_id,
            protocol=protocol,
            resolved=resolved,
            observations=observations,
            calibration_artifact_id=calibration_artifact_id,
            through_date=through_date,
            score_factor_id=score_factor_id,
            created_at=created_at,
            status=status,
            reason_codes=reason_codes,
        )
        hypothesis_id, hypothesis_hash = content_identity(
            "path-calibration-hypothesis",
            payload,
        )
        self._repository.record(
            artifact_id=hypothesis_id,
            artifact_hash=hypothesis_hash,
            artifact_kind="PATH_CALIBRATION_HYPOTHESIS",
            evidence_authority="ENGINEERING_ONLY",
            payload=payload,
            created_at=created_at,
        )
        return {
            "hypothesis_artifact_id": str(hypothesis_id),
            "hypothesis_artifact_hash": hypothesis_hash,
            **payload,
        }

    def _load_observations(
        self,
        *,
        target_protocol: OutcomeTargetProtocol,
        through_date: date,
        created_at: datetime,
        score_factor_id: str,
    ) -> tuple[_ResolvedCalibrationObservation, ...]:
        target_hashes = {
            str(item.target_id): item.target_hash for item in target_protocol.targets
        }
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT slice.trading_date, slice.shadow_decision_id,
                       panel.panel_id, panel.panel_hash, row.symbol,
                       exposure.exposure_json,
                       target_exposure.exposure_json, label.label_json
                FROM research_evaluation_panel_slice_v2 AS slice
                JOIN research_evaluation_panel_v2 AS panel
                  ON panel.panel_id = slice.panel_id
                JOIN research_evaluation_panel_row_v2 AS row
                  ON row.panel_id = slice.panel_id
                 AND row.slice_id = slice.slice_id
                JOIN research_validation_artifact AS enrichment
                  ON enrichment.artifact_kind = 'PANEL_ENRICHMENT'
                 AND enrichment.payload_json->'panel_reference'->>'artifact_id'
                     = panel.panel_id
                 AND enrichment.payload_json->'panel_reference'->>'content_hash'
                     = panel.panel_hash
                JOIN research_panel_factor_exposure AS exposure
                  ON exposure.enrichment_id = enrichment.artifact_id
                 AND exposure.symbol = row.symbol
                 AND exposure.factor_family = 'FORECAST'
                 AND exposure.factor_id = %s
                JOIN research_panel_factor_exposure AS target_exposure
                  ON target_exposure.enrichment_id = enrichment.artifact_id
                 AND target_exposure.symbol = row.symbol
                 AND target_exposure.factor_family = 'FORECAST'
                 AND target_exposure.factor_id = 'forecast.target_id'
                 AND target_exposure.source_artifact_id
                     = exposure.source_artifact_id
                 AND target_exposure.source_content_hash
                     = exposure.source_content_hash
                JOIN targeted_shadow_outcome_label AS label
                  ON label.settlement_id = slice.targeted_outcome_id
                 AND label.symbol = row.symbol
                WHERE slice.trading_date <= %s
                  AND label.label_interval_end <= %s
                  AND label.availability_status = 'COMPLETE'
                  AND label.target_protocol_id = %s
                ORDER BY slice.shadow_decision_id, row.symbol, label.target_id,
                         panel.created_at DESC, panel.panel_id DESC
                """,
                (
                    score_factor_id,
                    through_date,
                    created_at,
                    str(target_protocol.protocol_id),
                ),
            ).fetchall()
        observed: dict[
            tuple[str, str, str, str], _ResolvedCalibrationObservation
        ] = {}
        for row in rows:
            exposure = _mapping(row[5])
            raw_score = exposure.get("raw_numeric")
            source = _mapping(exposure.get("source_reference"))
            if raw_score is None or source.get("artifact_kind") != "PATH_FORECAST":
                continue
            forecast_target = _mapping(row[6]).get("raw_text")
            label = TargetOutcomeLabel.from_canonical_dict(_mapping(row[7]))
            target_id = str(label.target.artifact_id)
            if target_hashes.get(target_id) != label.target.content_hash:
                raise ValueError("Path calibration Target lineage mismatch")
            if forecast_target != target_id:
                continue
            target_reference = ValidationArtifactReference(
                "OUTCOME_TARGET",
                label.target.artifact_id,
                label.target.content_hash,
            )
            forecast_reference = ValidationArtifactReference.from_canonical_dict(source)
            label_reference = ValidationArtifactReference(
                "TARGET_OUTCOME_LABEL",
                label.label_id,
                label.label_hash,
            )
            panel_reference = ValidationArtifactReference(
                "RESEARCH_PANEL_V2",
                ArtifactId(str(row[2])),
                str(row[3]),
            )
            for barrier_id, first_passage_at in label.barrier_passages:
                key = (str(row[1]), str(row[4]), target_id, barrier_id)
                observed.setdefault(
                    key,
                    _ResolvedCalibrationObservation(
                        trading_date=row[0],
                        label_end_date=label.label_interval_end.date(),
                        label_reference=label_reference,
                        target_reference=target_reference,
                        barrier_id=barrier_id,
                        observation_id=(
                            f"{label.label_id}:{forecast_reference.artifact_id}:"
                            f"{score_factor_id}:{barrier_id}"
                        ),
                        score=Decimal(str(raw_score)),
                        outcome=0 if first_passage_at is None else 1,
                        panel_reference=panel_reference,
                        forecast_reference=forecast_reference,
                    ),
                )
        return tuple(
            sorted(
                observed.values(),
                key=lambda item: (
                    str(item.target_reference.artifact_id),
                    item.barrier_id,
                    item.trading_date,
                    item.observation_id,
                ),
            )
        )


def _partition_observations(
    values: tuple[_ResolvedCalibrationObservation, ...],
    *,
    minimum_fit_samples: int,
    minimum_validation_samples: int,
) -> tuple[tuple[CalibrationObservation, ...] | None, tuple[str, ...]]:
    dates = tuple(sorted({item.trading_date for item in values}))
    if len(dates) < 2:
        return None, ("NOT_ESTIMABLE_TRADING_DATE_PARTITION",)
    candidates: list[
        tuple[
            tuple[int, int, int],
            tuple[_ResolvedCalibrationObservation, ...],
            tuple[_ResolvedCalibrationObservation, ...],
        ]
    ] = []
    for split_index in range(1, len(dates)):
        validation_start = dates[split_index]
        fit = tuple(
            item
            for item in values
            if item.trading_date < validation_start
            and item.label_end_date < validation_start
        )
        validation = tuple(
            item for item in values if item.trading_date >= validation_start
        )
        if (
            len(fit) >= minimum_fit_samples
            and len(validation) >= minimum_validation_samples
        ):
            target_validation = max(1, len(values) // 5)
            candidates.append(
                (
                    (
                        abs(len(validation) - target_validation),
                        -len(fit),
                        split_index,
                    ),
                    fit,
                    validation,
                )
            )
    if not candidates:
        return None, (
            "NOT_ESTIMABLE_LABEL_AWARE_PURGED_FIT",
            "NOT_ESTIMABLE_MINIMUM_FIT_OR_VALIDATION_SAMPLES",
        )
    _rank, fit, validation = min(candidates, key=lambda item: item[0])
    observations = tuple(
        CalibrationObservation(
            item.observation_id,
            item.score,
            item.outcome,
            partition,
        )
        for partition, partition_values in (
            (CalibrationPartition.FIT, fit),
            (CalibrationPartition.VALIDATION, validation),
        )
        for item in partition_values
    )
    return observations, (
        "LABEL_AWARE_PURGE_APPLIED",
        "TRADING_DATE_PARTITION_APPLIED",
    )


def _hypothesis_payload(
    *,
    target_protocol: OutcomeTargetProtocol,
    target_reference: ValidationArtifactReference,
    barrier_id: str,
    protocol: CalibrationProtocol,
    resolved: tuple[_ResolvedCalibrationObservation, ...],
    observations: tuple[CalibrationObservation, ...],
    calibration_artifact_id: ArtifactId | None,
    through_date: date,
    score_factor_id: str,
    created_at: datetime,
    status: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    partitions = {item.observation_id: item.partition.value for item in observations}
    return {
        "schema_version": "path-calibration-hypothesis/v1",
        "target_protocol_reference": ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ).to_canonical_dict(),
        "target_reference": target_reference.to_canonical_dict(),
        "barrier_id": barrier_id,
        "calibration_protocol_reference": ValidationArtifactReference(
            "CALIBRATION_PROTOCOL",
            protocol.protocol_id,
            protocol.protocol_hash,
        ).to_canonical_dict(),
        "method": protocol.method.value,
        "through_date": through_date.isoformat(),
        "score_factor_id": score_factor_id,
        "status": status,
        "resolved_sample_count": len(resolved),
        "fit_sample_count": sum(
            item.partition is CalibrationPartition.FIT for item in observations
        ),
        "validation_sample_count": sum(
            item.partition is CalibrationPartition.VALIDATION
            for item in observations
        ),
        "observations": [
            {
                "observation_id": item.observation_id,
                "trading_date": item.trading_date.isoformat(),
                "label_end_date": item.label_end_date.isoformat(),
                "label_reference": item.label_reference.to_canonical_dict(),
                "target_reference": item.target_reference.to_canonical_dict(),
                "barrier_id": item.barrier_id,
                "raw_score": str(item.score),
                "binary_outcome": item.outcome,
                "partition": partitions.get(item.observation_id, "NOT_ASSIGNED"),
                "panel_reference": item.panel_reference.to_canonical_dict(),
                "forecast_reference": item.forecast_reference.to_canonical_dict(),
            }
            for item in resolved
        ],
        "calibration_artifact_id": (
            None
            if calibration_artifact_id is None
            else str(calibration_artifact_id)
        ),
        "created_at": timestamp(created_at),
        "calibrated": False,
        "formal_pit": False,
        "formal_oos": False,
        "production_authorized": False,
        "qualification_evidence": None,
        "reason_codes": list(sorted(set(reason_codes))),
        "limitations": [
            "BACKFILLED_FREE_DATA_NOT_FORMAL_PIT",
            "CALIBRATED_FALSE",
            "FREE_DATA_EXPLORATORY",
            "NO_TRADING_AUTHORITY",
        ],
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Path calibration PostgreSQL payload is not an object")
    return value


__all__ = [
    "PATH_CALIBRATION_SCORE_FACTOR",
    "PostgresPathForecastCalibrationOperator",
]
