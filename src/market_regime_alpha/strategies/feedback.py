"""Strategy-scoped Outcome -> Attribution -> Challenger -> Qualification facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.strategies.path_outcomes import (
    BarrierOrderingOutcome,
    StrategyPathOutcome,
)


class StrategyFeedbackKind(str, Enum):
    ATTRIBUTION = "ATTRIBUTION"
    CHALLENGER_EVALUATION = "CHALLENGER_EVALUATION"
    QUALIFICATION_DECISION = "QUALIFICATION_DECISION"


class StrategyFeedbackStatus(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    NOT_QUALIFIED = "NOT_QUALIFIED"


_FEEDBACK_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class StrategyFeedbackArtifact:
    artifact_id: ArtifactId
    artifact_hash: str
    artifact_kind: StrategyFeedbackKind
    strategy_version_reference: RuntimeArtifactReference
    source_references: tuple[RuntimeArtifactReference, ...]
    status: StrategyFeedbackStatus
    metrics: tuple[tuple[str, str], ...]
    findings: tuple[str, ...]
    created_at: datetime
    schema_version: str = "strategy-feedback-artifact/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "strategy-feedback-artifact/v1":
            raise ValueError("unsupported Strategy Feedback schema")
        require_sha256("artifact_hash", self.artifact_hash)
        if not self.source_references or self.source_references != _references(self.source_references):
            raise ValueError("Strategy Feedback sources must be non-empty and sorted")
        if self.metrics != tuple(sorted(set(self.metrics))):
            raise ValueError("Strategy Feedback metrics must be unique and sorted")
        if not self.findings or self.findings != tuple(sorted(set(self.findings))):
            raise ValueError("Strategy Feedback findings must be non-empty and sorted")
        canonical_datetime(self.created_at)
        digest = canonical_hash(self.identity_payload())
        expected_id = f"strategy-feedback:{digest[7:]}"
        if digest != self.artifact_hash or str(self.artifact_id) != expected_id:
            raise ValueError("Strategy Feedback identity mismatch")

    @property
    def production_authorized(self) -> bool:
        return False

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            f"STRATEGY_{self.artifact_kind.value}",
            self.artifact_id,
            self.artifact_hash,
        )

    @classmethod
    def create(
        cls,
        *,
        artifact_kind: StrategyFeedbackKind,
        strategy_version_reference: RuntimeArtifactReference,
        source_references: tuple[RuntimeArtifactReference, ...],
        status: StrategyFeedbackStatus,
        metrics: tuple[tuple[str, str], ...],
        findings: tuple[str, ...],
        created_at: datetime,
    ) -> StrategyFeedbackArtifact:
        ordered_sources = _references(source_references)
        ordered_metrics = tuple(sorted(set(metrics)))
        ordered_findings = tuple(sorted(set(findings)))
        schema_version = "strategy-feedback-artifact/v1"
        digest = canonical_hash(
            _feedback_payload(
                artifact_kind=artifact_kind,
                strategy_version_reference=strategy_version_reference,
                source_references=ordered_sources,
                status=status,
                metrics=ordered_metrics,
                findings=ordered_findings,
                created_at=created_at,
                schema_version=schema_version,
            )
        )
        return cls(
            artifact_id=ArtifactId(f"strategy-feedback:{digest[7:]}"),
            artifact_hash=digest,
            artifact_kind=artifact_kind,
            strategy_version_reference=strategy_version_reference,
            source_references=ordered_sources,
            status=status,
            metrics=ordered_metrics,
            findings=ordered_findings,
            created_at=created_at,
            schema_version=schema_version,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _feedback_payload(
            artifact_kind=self.artifact_kind,
            strategy_version_reference=self.strategy_version_reference,
            source_references=self.source_references,
            status=self.status,
            metrics=self.metrics,
            findings=self.findings,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "artifact_hash": self.artifact_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> StrategyFeedbackArtifact:
        return cls(
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            artifact_hash=str(payload["artifact_hash"]),
            artifact_kind=StrategyFeedbackKind(str(payload["artifact_kind"])),
            strategy_version_reference=_reference(payload["strategy_version_reference"]),
            source_references=_references_from(payload["source_references"]),
            status=StrategyFeedbackStatus(str(payload["status"])),
            metrics=_pairs(payload["metrics"]),
            findings=_strings(payload["findings"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            schema_version=str(payload["schema_version"]),
        )


def attribute_path_outcomes(
    *,
    strategy_version_reference: RuntimeArtifactReference,
    outcomes: tuple[StrategyPathOutcome, ...],
    created_at: datetime,
) -> StrategyFeedbackArtifact:
    with localcontext(_FEEDBACK_DECIMAL_CONTEXT):
        return _attribute_path_outcomes(
            strategy_version_reference=strategy_version_reference,
            outcomes=outcomes,
            created_at=created_at,
        )


def _attribute_path_outcomes(
    *,
    strategy_version_reference: RuntimeArtifactReference,
    outcomes: tuple[StrategyPathOutcome, ...],
    created_at: datetime,
) -> StrategyFeedbackArtifact:
    canonical_datetime(created_at)
    if any(item.strategy_version_reference != strategy_version_reference for item in outcomes):
        raise ValueError("Attribution cannot cross Strategy Version boundaries")
    if outcomes and created_at < max(item.measured_at for item in outcomes):
        raise ValueError("Attribution cannot be created before its Path Outcome")
    if not outcomes:
        return StrategyFeedbackArtifact.create(
            artifact_kind=StrategyFeedbackKind.ATTRIBUTION,
            strategy_version_reference=strategy_version_reference,
            source_references=(strategy_version_reference,),
            status=StrategyFeedbackStatus.NOT_ESTIMABLE,
            metrics=(("outcome_count", "0"),),
            findings=("PATH_OUTCOME_NOT_AVAILABLE",),
            created_at=created_at,
        )
    count = Decimal(len(outcomes))
    failures = sum(1 for item in outcomes if item.failure)
    target_first = sum(1 for item in outcomes if item.barrier_ordering is BarrierOrderingOutcome.TARGET_BEFORE_STOP)
    return StrategyFeedbackArtifact.create(
        artifact_kind=StrategyFeedbackKind.ATTRIBUTION,
        strategy_version_reference=strategy_version_reference,
        source_references=tuple(
            RuntimeArtifactReference(
                "STRATEGY_PATH_OUTCOME",
                item.outcome_id,
                item.outcome_hash,
            )
            for item in outcomes
        ),
        status=StrategyFeedbackStatus.EXPLORATORY,
        metrics=(
            ("average_mae", str(sum((item.mae for item in outcomes), Decimal("0")) / count)),
            ("average_mfe", str(sum((item.mfe for item in outcomes), Decimal("0")) / count)),
            ("failure_rate", str(Decimal(failures) / count)),
            ("outcome_count", str(len(outcomes))),
            ("target_before_stop_rate", str(Decimal(target_first) / count)),
        ),
        findings=(
            "ATTRIBUTION_IS_STRATEGY_VERSION_SCOPED",
            "MARKET_OUTCOME_NOT_STRATEGY_PNL",
        ),
        created_at=created_at,
    )


def evaluate_strategy_challenger(
    *,
    incumbent: StrategyFeedbackArtifact,
    challenger: StrategyFeedbackArtifact,
    created_at: datetime,
) -> StrategyFeedbackArtifact:
    with localcontext(_FEEDBACK_DECIMAL_CONTEXT):
        return _evaluate_strategy_challenger(
            incumbent=incumbent,
            challenger=challenger,
            created_at=created_at,
        )


def _evaluate_strategy_challenger(
    *,
    incumbent: StrategyFeedbackArtifact,
    challenger: StrategyFeedbackArtifact,
    created_at: datetime,
) -> StrategyFeedbackArtifact:
    canonical_datetime(created_at)
    if incumbent.artifact_kind is not StrategyFeedbackKind.ATTRIBUTION or challenger.artifact_kind is not StrategyFeedbackKind.ATTRIBUTION:
        raise ValueError("Challenger evaluation requires Attribution inputs")
    if incumbent.strategy_version_reference == challenger.strategy_version_reference:
        raise ValueError("Challenger must be a different Strategy Version")
    if created_at < max(incumbent.created_at, challenger.created_at):
        raise ValueError("Challenger cannot be created before its Attribution")
    comparable = set(dict(incumbent.metrics)).intersection(dict(challenger.metrics))
    deltas = tuple(
        (
            f"delta_{name}",
            str(Decimal(dict(challenger.metrics)[name]) - Decimal(dict(incumbent.metrics)[name])),
        )
        for name in sorted(comparable)
        if name != "outcome_count"
    )
    status = StrategyFeedbackStatus.EXPLORATORY if deltas else StrategyFeedbackStatus.NOT_ESTIMABLE
    return StrategyFeedbackArtifact.create(
        artifact_kind=StrategyFeedbackKind.CHALLENGER_EVALUATION,
        strategy_version_reference=challenger.strategy_version_reference,
        source_references=(incumbent.reference, challenger.reference),
        status=status,
        metrics=deltas or (("comparable_metric_count", "0"),),
        findings=(
            "CHALLENGER_NOT_AUTO_PROMOTED",
            "COMPARISON_REMAINS_EXPLORATORY",
        ),
        created_at=created_at,
    )


def decide_strategy_qualification(
    *,
    strategy_version_reference: RuntimeArtifactReference,
    attribution: StrategyFeedbackArtifact,
    challenger_evaluation: StrategyFeedbackArtifact,
    formal_pit: bool,
    formal_oos: bool,
    calibrated: bool,
    net_economics_established: bool,
    prospective_evidence: bool,
    created_at: datetime,
) -> StrategyFeedbackArtifact:
    canonical_datetime(created_at)
    if attribution.strategy_version_reference != strategy_version_reference or (
        challenger_evaluation.strategy_version_reference != strategy_version_reference
    ):
        raise ValueError("Qualification inputs must bind one Strategy Version")
    if created_at < max(attribution.created_at, challenger_evaluation.created_at):
        raise ValueError("Qualification cannot be created before its feedback inputs")
    checks = {
        "CALIBRATED": calibrated,
        "FORMAL_OOS": formal_oos,
        "FORMAL_PIT": formal_pit,
        "NET_ECONOMICS": net_economics_established,
        "PROSPECTIVE_EVIDENCE": prospective_evidence,
    }
    failed_findings = {
        "CALIBRATED": "CALIBRATED_FALSE",
        "FORMAL_OOS": "FORMAL_OOS_FALSE",
        "FORMAL_PIT": "FORMAL_PIT_NOT_ESTABLISHED",
        "NET_ECONOMICS": "NET_ECONOMICS_NOT_ESTABLISHED",
        "PROSPECTIVE_EVIDENCE": "PROSPECTIVE_EVIDENCE_NOT_ESTABLISHED",
    }
    findings = {
        "ALPHA_NOT_ESTABLISHED",
        "PRODUCTION_AUTHORIZED_FALSE",
        *(failed_findings[name] for name, passed in checks.items() if not passed),
    }
    # The current product has no Production Admission owner. Even a future
    # all-green research evidence set must pass that separate boundary.
    return StrategyFeedbackArtifact.create(
        artifact_kind=StrategyFeedbackKind.QUALIFICATION_DECISION,
        strategy_version_reference=strategy_version_reference,
        source_references=(attribution.reference, challenger_evaluation.reference),
        status=StrategyFeedbackStatus.NOT_QUALIFIED,
        metrics=tuple((name.lower(), str(passed).lower()) for name, passed in checks.items()),
        findings=tuple(findings),
        created_at=created_at,
    )


def _feedback_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "artifact_kind": values["artifact_kind"].value,
        "strategy_version_reference": values["strategy_version_reference"].to_canonical_dict(),
        "source_references": [item.to_canonical_dict() for item in values["source_references"]],
        "status": values["status"].value,
        "metrics": [list(item) for item in values["metrics"]],
        "findings": list(values["findings"]),
        "created_at": canonical_datetime(values["created_at"]),
    }


def _references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    values = {(item.reference_kind, str(item.artifact_id), item.content_hash): item for item in references}
    return tuple(values[key] for key in sorted(values))


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("Strategy Feedback reference must be an object")
    return RuntimeArtifactReference.from_canonical_dict(value)


def _references_from(value: object) -> tuple[RuntimeArtifactReference, ...]:
    if not isinstance(value, list):
        raise ValueError("Strategy Feedback references must be an array")
    return _references(tuple(_reference(item) for item in value))


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Strategy Feedback value must be a string array")
    return tuple(str(item) for item in value)


def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("Strategy Feedback pairs must be an array")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("Strategy Feedback pair is invalid")
        pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)


__all__ = [
    "StrategyFeedbackArtifact",
    "StrategyFeedbackKind",
    "StrategyFeedbackStatus",
    "attribute_path_outcomes",
    "decide_strategy_qualification",
    "evaluate_strategy_challenger",
]
