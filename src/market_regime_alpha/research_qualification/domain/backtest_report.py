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
class BacktestReportSource:
    run: FrozenBacktestRun
    configuration: BacktestReportConfiguration
    canonical_completed_at: datetime
    evaluation_run_ids: tuple[UUID, ...]
    metrics: tuple[BacktestReportMetric, ...]
    models: tuple[BacktestReportModel, ...]
    execution_failure_reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    recommended_next_experiment: str = "Collect qualified prospective evidence."
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
                        "json_artifact": self.json_artifact,
                        "markdown_artifact": self.markdown_artifact,
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
    configuration = source.configuration
    return BacktestComparisonFingerprint(
        market_archive_sha256=canonical_json_sha256((configuration.market_archive, configuration.market_archive_seal)),
        universe_sample_sha256=canonical_json_sha256(
            (
                configuration.universe_revision,
                configuration.eligibility_policy,
                configuration.sample_scope_code,
                configuration.sample_roster_sha256,
            )
        ),
        target_sha256=configuration.target.content_sha256,
        fold_dependency_sha256=canonical_json_sha256(
            (
                configuration.fold_roster_sha256,
                configuration.dependency_roster_sha256,
            )
        ),
        cost_sha256=configuration.cost_roster_sha256,
        portfolio_risk_sha256=configuration.effective_policy_roster_sha256,
        evaluation_formula_sha256=(configuration.evaluation_formula_roster_sha256),
        evidence_lane=source.run.evidence.value,
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
]
