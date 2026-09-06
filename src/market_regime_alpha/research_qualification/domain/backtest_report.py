"""Deterministic derived Backtest report and comparison contracts.

These values never own metric truth.  Every metric is a projection of one
completed canonical Evaluation and carries its exact formula lineage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestSpecification,
    FrozenBacktestRun,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    FormulaResultState,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class BacktestComparisonMode(StrEnum):
    LIKE_FOR_LIKE = "LIKE_FOR_LIKE"
    DESCRIPTIVE_NON_LIKE_FOR_LIKE = "DESCRIPTIVE_NON_LIKE_FOR_LIKE"


@dataclass(frozen=True, slots=True)
class BacktestReportConfiguration:
    market_archive: AuthorityBinding
    market_archive_seal: AuthorityBinding
    universe_revision: AuthorityBinding
    eligibility_policy: AuthorityBinding
    sample_scope_code: str
    sample_roster_sha256: ContentHash | str
    feature_roster_sha256: ContentHash | str
    target: VersionedAuthorityBinding
    walk_forward_policy_sha256: ContentHash | str
    fold_roster_sha256: ContentHash | str
    dependency_roster_sha256: ContentHash | str
    cost_roster_sha256: ContentHash | str
    effective_policy_roster_sha256: ContentHash | str
    evaluation_formula_roster_sha256: ContentHash | str
    code_content_sha256: ContentHash | str
    config_content_sha256: ContentHash | str
    first_session_date: str
    last_session_date: str
    distinct_trading_session_count: int
    fold_session_binding_count: int
    sample_member_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "sample_roster_sha256",
            "feature_roster_sha256",
            "walk_forward_policy_sha256",
            "fold_roster_sha256",
            "dependency_roster_sha256",
            "cost_roster_sha256",
            "effective_policy_roster_sha256",
            "evaluation_formula_roster_sha256",
            "code_content_sha256",
            "config_content_sha256",
        ):
            object.__setattr__(self, field_name, ContentHash(str(getattr(self, field_name))))
        if self.distinct_trading_session_count < 1:
            raise ValueError("report requires at least one distinct trading Session")
        if self.fold_session_binding_count < self.distinct_trading_session_count:
            raise ValueError("report fold binding count cannot be smaller than Session count")
        if self.sample_member_count < 1:
            raise ValueError("report sample roster must be non-empty")


@dataclass(frozen=True, slots=True)
class BacktestReportModel:
    arm_id: UUID
    model_definition: AuthorityBinding
    fit_fold_id: UUID
    validation_fold_id: UUID
    model_training_run_id: UUID | None
    model_version_id: UUID | None
    state: str
    reason_code: str

    def __post_init__(self) -> None:
        if not _REASON.fullmatch(self.reason_code):
            raise ValueError("Model report reason_code has an invalid format")
        if self.model_version_id is not None and self.model_training_run_id is None:
            raise ValueError("ModelVersion report lineage requires a TrainingRun")
        if self.state == "COMPLETED" and (self.model_training_run_id is None or self.model_version_id is None):
            raise ValueError("completed Model report lineage requires TrainingRun and Version")


@dataclass(frozen=True, slots=True)
class BacktestReportMetric:
    evaluation_metric_id: UUID
    evaluation_run_id: UUID
    evaluation_requirement_id: UUID
    protocol_metric_id: UUID
    arm_id: UUID
    fold_id: UUID | None
    scope_kind: str
    slice_key: str | None
    surface: BacktestMetricSurface
    metric_code: str
    formula_code: BacktestFormulaCode
    formula_version: int
    formula_content_sha256: ContentHash | str
    result_state: FormulaResultState
    decimal_value: Decimal | None
    estimable_count: int
    reason_code: str
    acceptance_state: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "formula_content_sha256",
            ContentHash(str(self.formula_content_sha256)),
        )
        if isinstance(self.formula_version, bool) or self.formula_version < 1:
            raise ValueError("report formula_version must be positive")
        if self.estimable_count < 0:
            raise ValueError("report estimable_count must be non-negative")
        if not _REASON.fullmatch(self.reason_code):
            raise ValueError("report metric reason_code has an invalid format")
        estimable = self.result_state is FormulaResultState.ESTIMABLE
        if estimable != (self.decimal_value is not None):
            raise ValueError("report metric estimability and value differ")
        if self.decimal_value is not None and not self.decimal_value.is_finite():
            raise ValueError("report metric value must be finite")


@dataclass(frozen=True, slots=True)
class BacktestReportRiskReason:
    evaluation_run_id: UUID
    decision_run_id: UUID
    risk_decision_id: UUID
    risk_decision_sha256: str
    risk_reason_id: UUID
    risk_reason_sha256: str
    risk_status: str
    result: str
    reason_code: str

    def __post_init__(self) -> None:
        ContentHash(self.risk_decision_sha256)
        ContentHash(self.risk_reason_sha256)
        if self.risk_status not in {"AUTHORIZED", "REJECTED", "UNKNOWN", "NO_ACTION"}:
            raise ValueError("report Risk status is invalid")
        if self.result not in {"FAIL", "UNKNOWN"} or not _REASON.fullmatch(self.reason_code):
            raise ValueError("report Risk reason is not a canonical failure or unknown")


@dataclass(frozen=True, slots=True)
class BacktestReportSource:
    run: FrozenBacktestRun
    configuration: BacktestReportConfiguration
    canonical_completed_at: datetime
    evaluation_run_ids: tuple[UUID, ...]
    metrics: tuple[BacktestReportMetric, ...]
    models: tuple[BacktestReportModel, ...]
    comparison_scope: BacktestComparisonFingerprint
    execution_failure_reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    recommended_next_experiment: str = "Collect qualified prospective evidence."
    risk_reasons: tuple[BacktestReportRiskReason, ...] = ()
    evaluation_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if self.canonical_completed_at.tzinfo is None:
            raise ValueError("canonical completion time must be timezone-aware")
        if not self.evaluation_run_ids or len(set(self.evaluation_run_ids)) != len(self.evaluation_run_ids):
            raise ValueError("report Evaluation roster must be non-empty and unique")
        if not self.metrics:
            raise ValueError("report requires canonical Evaluation metrics")
        if any(metric.evaluation_run_id not in self.evaluation_run_ids for metric in self.metrics):
            raise ValueError("report metric is outside the Evaluation roster")
        if any(reason.evaluation_run_id not in self.evaluation_run_ids for reason in self.risk_reasons):
            raise ValueError("report Risk reason is outside the Evaluation roster")
        if any(not _REASON.fullmatch(reason) for reason in self.execution_failure_reasons):
            raise ValueError("report execution failure reason is invalid")
        evaluation_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "evaluation_run_id": identity,
                        "ordinal": ordinal,
                    }
                    for ordinal, identity in enumerate(self.evaluation_run_ids, start=1)
                )
            )
        )
        object.__setattr__(self, "evaluation_roster_sha256", evaluation_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "canonical_completed_at": self.canonical_completed_at,
                        "configuration": self.configuration,
                        "evaluation_roster_sha256": str(evaluation_hash),
                        "execution_failure_reasons": self.execution_failure_reasons,
                        "limitations": self.limitations,
                        "metrics": self.metrics,
                        "models": self.models,
                        "recommended_next_experiment": self.recommended_next_experiment,
                        "run_projection_sha256": str(self.run.projection_sha256),
                        **({"risk_reasons": self.risk_reasons} if self.risk_reasons else {}),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestReportArtifactBinding:
    """Derived content-addressed report bundle; never research Authority."""

    backtest_report_artifact_id: UUID
    exploratory_backtest_run_id: UUID
    specification_sha256: ContentHash | str
    evaluation_count: int
    evaluation_roster_sha256: ContentHash | str
    source_projection_sha256: ContentHash | str
    code_content_sha256: ContentHash | str
    config_content_sha256: ContentHash | str
    report_schema: str
    renderer_version: str
    json_artifact: ArtifactBinding
    markdown_artifact: ArtifactBinding
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if self.evaluation_count < 1:
            raise ValueError("report Artifact requires an Evaluation roster")
        hashes = {}
        for field_name in (
            "specification_sha256",
            "evaluation_roster_sha256",
            "source_projection_sha256",
            "code_content_sha256",
            "config_content_sha256",
        ):
            normalized = ContentHash(str(getattr(self, field_name)))
            object.__setattr__(self, field_name, normalized)
            hashes[field_name] = str(normalized)
        if self.report_schema != "mra-backtest-report-v1":
            raise ValueError("report schema is unsupported")
        if self.renderer_version != "1":
            raise ValueError("report renderer version is unsupported")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        **hashes,
                        "evaluation_count": self.evaluation_count,
                        "exploratory_backtest_run_id": (self.exploratory_backtest_run_id),
                        # The persistent report contract stores digest strings,
                        # not the ContentHash value object's dataclass shape.
                        "json_artifact": {
                            "artifact_id": self.json_artifact.artifact_id,
                            "content_sha256": str(self.json_artifact.content_sha256),
                            "size_bytes": self.json_artifact.size_bytes,
                        },
                        "markdown_artifact": {
                            "artifact_id": self.markdown_artifact.artifact_id,
                            "content_sha256": str(self.markdown_artifact.content_sha256),
                            "size_bytes": self.markdown_artifact.size_bytes,
                        },
                        "renderer_version": self.renderer_version,
                        "report_schema": self.report_schema,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestComparisonFingerprint:
    market_archive_sha256: ContentHash | str
    universe_sample_sha256: ContentHash | str
    target_sha256: ContentHash | str
    fold_dependency_sha256: ContentHash | str
    cost_sha256: ContentHash | str
    portfolio_risk_sha256: ContentHash | str
    evaluation_formula_sha256: ContentHash | str
    evidence_lane: str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        values: dict[str, str] = {}
        for field_name in (
            "market_archive_sha256",
            "universe_sample_sha256",
            "target_sha256",
            "fold_dependency_sha256",
            "cost_sha256",
            "portfolio_risk_sha256",
            "evaluation_formula_sha256",
        ):
            normalized = ContentHash(str(getattr(self, field_name)))
            object.__setattr__(self, field_name, normalized)
            values[field_name] = str(normalized)
        values["evidence_lane"] = self.evidence_lane
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256(values)),
        )


@dataclass(frozen=True, slots=True)
class BacktestMetricDelta:
    metric_code: str
    scope_key: str
    left_value: Decimal | None
    right_value: Decimal | None
    delta: Decimal | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class BacktestComparison:
    mode: BacktestComparisonMode
    left_run_id: UUID
    right_run_id: UUID
    mismatch_fields: tuple[str, ...]
    metric_deltas: tuple[BacktestMetricDelta, ...]
    winner_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.mode is BacktestComparisonMode.DESCRIPTIVE_NON_LIKE_FOR_LIKE and self.winner_run_id is not None:
            raise ValueError("non-like-for-like comparison cannot emit a winner")


def comparison_fingerprint(
    source: BacktestReportSource,
) -> BacktestComparisonFingerprint:
    return source.comparison_scope


def specification_comparison_fingerprint(
    specification: BacktestSpecification,
    metrics: tuple[BacktestReportMetric, ...],
) -> BacktestComparisonFingerprint:
    """Compare canonical scopes without conflating them with execution IDs.

    This derived value is deliberately outside the persisted report payload
    and its hash. Authority identities, effective policies and formula hashes
    remain exact; only Run-owned roster identities are normalized.
    """
    spec = specification
    arms = {arm.exploratory_backtest_arm_id: arm.ordinal for arm in spec.arms}
    folds = {fold.exploratory_backtest_fold_id: fold.ordinal for fold in spec.folds}
    return BacktestComparisonFingerprint(
        market_archive_sha256=canonical_json_sha256((spec.market_archive, spec.market_archive_seal)),
        universe_sample_sha256=canonical_json_sha256(
            (
                spec.universe_revision, spec.eligibility_policy,
                spec.sample_scope_code, spec.sample_roster_sha256,
                spec.sample_algorithm_version, spec.sample_input_key,
                spec.random_seed, spec.feature_roster_sha256,
            )
        ),
        target_sha256=canonical_json_sha256(spec.target),
        fold_dependency_sha256=canonical_json_sha256(
            (
                spec.walk_forward_policy,
                tuple(
                    (fold.ordinal, fold.purpose, fold.exchange_code,
                     fold.purge_sessions, fold.embargo_sessions,
                     tuple((session.ordinal, session.trading_session_id,
                            session.session_date, session.role) for session in fold.sessions))
                    for fold in spec.folds
                ),
                tuple((item.ordinal, folds[item.fit_fold_id], folds[item.validation_fold_id])
                      for item in spec.fold_dependencies),
                tuple((item.ordinal, arms[item.arm_id], folds[item.fold_id])
                      for item in spec.arm_folds),
            )
        ),
        cost_sha256=canonical_json_sha256((
            tuple((item.ordinal, item.cost_kind, item.charge_side, item.amount_bps,
                   None if item.arm_id is None else arms[item.arm_id])
                  for item in spec.cost_assumptions),
            tuple((arm.ordinal, arm.cost_binding_source) for arm in spec.arms),
        )),
        portfolio_risk_sha256=canonical_json_sha256(tuple(
            (arm.ordinal, arm.arm_code, arm.execution_kind, arm.comparison_role,
             arm.context_mode, arm.candidate, arm.context, arm.strategy,
             arm.portfolio, arm.risk)
            for arm in spec.arms
        )),
        evaluation_formula_sha256=canonical_json_sha256((
            tuple((item.ordinal, arms[item.arm_id], None if item.fold_id is None else folds[item.fold_id],
                   item.scope_kind, item.slice_key, item.primary, item.evaluation_protocol)
                  for item in spec.evaluation_requirements if item.arm_id is not None),
            tuple(sorted(
                (arms[item.arm_id], item.scope_kind,
                 0 if item.fold_id is None else folds[item.fold_id],
                 "" if item.slice_key is None else item.slice_key,
                 item.metric_code, item.surface.value, item.formula_code.value,
                 item.formula_version, str(item.formula_content_sha256))
                for item in metrics
            )),
        )),
        evidence_lane=spec.evidence_lane,
    )


__all__ = [
    "BacktestComparison",
    "BacktestComparisonFingerprint",
    "BacktestComparisonMode",
    "BacktestMetricDelta",
    "BacktestReportConfiguration",
    "BacktestReportArtifactBinding",
    "BacktestReportMetric",
    "BacktestReportModel",
    "BacktestReportSource",
    "comparison_fingerprint",
    "specification_comparison_fingerprint",
]
