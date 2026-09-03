"""Deterministic read-only Backtest report and comparison projections."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import Protocol
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestComparison,
    BacktestComparisonFingerprint,
    BacktestComparisonMode,
    BacktestMetricDelta,
    BacktestReportMetric,
    BacktestReportArtifactBinding,
    BacktestReportSource,
    comparison_fingerprint,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestMetricSurface,
    FormulaResultState,
)
from market_regime_alpha.research_qualification.errors import (
    BacktestReportIntegrityError,
    IncompatibleBacktestComparisonError,
)
from market_regime_alpha.research_qualification.ports.backtest_queries import (
    BacktestReplayVerification,
)
from market_regime_alpha.research_qualification.ports.backtest_reports import (
    BacktestReportArtifactPublisher,
    BacktestReportBindingWriter,
    BacktestReportSourcePort,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.shared.hashing import sha256_bytes


_REPORT_SCHEMA = "mra-backtest-report-v1"
_RENDERER_VERSION = "1"
_SURFACE_SECTIONS = {
    BacktestMetricSurface.DATA: "data_coverage",
    BacktestMetricSurface.CANDIDATE: "candidate_metrics",
    BacktestMetricSurface.CONTEXT: "context_attribution",
    BacktestMetricSurface.SIGNAL_FORECAST: "signal_forecast_metrics",
    BacktestMetricSurface.PORTFOLIO_RISK: "portfolio_risk_metrics",
    BacktestMetricSurface.ECONOMICS: "gross_net_economics",
    BacktestMetricSurface.STABILITY: "fold_time_stability",
}


class _BacktestVerifier(Protocol):
    def verify(self, exploratory_backtest_run_id: UUID) -> BacktestReplayVerification: ...


class BacktestReportApplication:
    """Project only reconciled canonical owners; owns no metric computation."""

    def __init__(
        self,
        source: BacktestReportSourcePort,
        verifier: _BacktestVerifier,
    ) -> None:
        self._source = source
        self._verifier = verifier

    def project(self, exploratory_backtest_run_id: UUID) -> dict[str, object]:
        source = self._load_reconciled(exploratory_backtest_run_id)
        return _report_payload(source)

    def render_json(self, exploratory_backtest_run_id: UUID) -> bytes:
        return _canonical_json_bytes(self.project(exploratory_backtest_run_id))

    def render_markdown(self, exploratory_backtest_run_id: UUID) -> bytes:
        payload = self.project(exploratory_backtest_run_id)
        return _markdown_bytes(payload)

    def publish(
        self,
        exploratory_backtest_run_id: UUID,
        *,
        artifacts: BacktestReportArtifactPublisher,
        bindings: BacktestReportBindingWriter,
        context: CommandContext,
    ) -> BacktestReportArtifactBinding:
        """Publish both deterministic formats, then bind their exact bytes."""

        source = self._load_reconciled(exploratory_backtest_run_id)
        payload = _report_payload(source)
        json_bytes = _canonical_json_bytes(payload)
        markdown_bytes = _markdown_bytes(payload)
        json_record = artifacts.publish(
            json_bytes,
            media_type="application/json",
            context=context,
        )
        markdown_record = artifacts.publish(
            markdown_bytes,
            media_type="text/markdown",
            context=context,
        )
        if (
            json_record.content_sha256 != sha256_bytes(json_bytes)
            or json_record.size_bytes != len(json_bytes)
            or markdown_record.content_sha256 != sha256_bytes(markdown_bytes)
            or markdown_record.size_bytes != len(markdown_bytes)
        ):
            raise BacktestReportIntegrityError("published report Artifact bytes differ from deterministic projection")
        binding = BacktestReportArtifactBinding(
            backtest_report_artifact_id=uuid5(
                exploratory_backtest_run_id,
                f"backtest-report:{source.content_sha256}:{_RENDERER_VERSION}",
            ),
            exploratory_backtest_run_id=exploratory_backtest_run_id,
            specification_sha256=source.run.specification_sha256,
            evaluation_count=len(source.evaluation_run_ids),
            evaluation_roster_sha256=source.evaluation_roster_sha256,
            source_projection_sha256=source.content_sha256,
            code_content_sha256=source.configuration.code_content_sha256,
            config_content_sha256=source.configuration.config_content_sha256,
            report_schema=_REPORT_SCHEMA,
            renderer_version=_RENDERER_VERSION,
            json_artifact=ArtifactBinding(
                json_record.artifact_id,
                json_record.content_sha256,
                json_record.size_bytes,
            ),
            markdown_artifact=ArtifactBinding(
                markdown_record.artifact_id,
                markdown_record.content_sha256,
                markdown_record.size_bytes,
            ),
        )
        bindings.bind_report(binding, context)
        return binding

    def compare(
        self,
        left_run_id: UUID,
        right_run_id: UUID,
        *,
        descriptive: bool = False,
    ) -> BacktestComparison:
        left = self._load_reconciled(left_run_id)
        right = self._load_reconciled(right_run_id)
        left_fingerprint = comparison_fingerprint(left)
        right_fingerprint = comparison_fingerprint(right)
        mismatches = _fingerprint_mismatches(
            left_fingerprint,
            right_fingerprint,
        )
        if mismatches and not descriptive:
            raise IncompatibleBacktestComparisonError("Backtest scopes are not like-for-like: " + ", ".join(mismatches))
        mode = BacktestComparisonMode.DESCRIPTIVE_NON_LIKE_FOR_LIKE if mismatches else BacktestComparisonMode.LIKE_FOR_LIKE
        return BacktestComparison(
            mode=mode,
            left_run_id=left_run_id,
            right_run_id=right_run_id,
            mismatch_fields=mismatches,
            metric_deltas=_metric_deltas(left, right),
            winner_run_id=None,
        )

    def _load_reconciled(self, run_id: UUID) -> BacktestReportSource:
        verification = self._verifier.verify(run_id)
        if not verification.matched or verification.mismatch_count:
            raise BacktestReportIntegrityError(
                "Backtest report requires zero-mismatch reconciliation: " + ", ".join(verification.mismatch_codes)
            )
        source = self._source.load(run_id)
        if source.run.exploratory_backtest_run_id != run_id:
            raise BacktestReportIntegrityError("Backtest report source returned a different identity")
        return source


def _report_payload(source: BacktestReportSource) -> dict[str, object]:
    run = source.run
    configuration = source.configuration
    metric_payloads = tuple(_metric_payload(metric) for metric in source.metrics)
    metrics_by_surface = {
        surface: tuple(payload for metric, payload in zip(source.metrics, metric_payloads, strict=True) if metric.surface is surface)
        for surface in BacktestMetricSurface
    }
    not_estimable = tuple(
        payload
        for metric, payload in zip(source.metrics, metric_payloads, strict=True)
        if metric.result_state is FormulaResultState.NOT_ESTIMABLE
    )
    baseline_challenger = tuple(
        {
            "arm_code": arm.arm_code,
            "arm_id": str(arm.exploratory_backtest_arm_id),
            "comparison_role": arm.comparison_role.value,
            "context_mode": arm.context_mode.value,
            "execution_kind": arm.execution_kind.value,
            "model_definition_id": (None if arm.model is None else str(arm.model.authority_id)),
            "strategy_version_id": str(arm.strategy.authority_id),
        }
        for arm in run.arms
    )
    payload: dict[str, object] = {
        "schema": _REPORT_SCHEMA,
        "renderer_version": _RENDERER_VERSION,
        "executive_summary": {
            "backtest_run_id": str(run.exploratory_backtest_run_id),
            "run_code": run.run_code,
            "definition_sha256": str(run.definition_sha256),
            "specification_sha256": str(run.specification_sha256),
            "canonical_completed_at": source.canonical_completed_at.isoformat(),
            "evaluation_count": len(source.evaluation_run_ids),
            "estimable_metric_count": sum(metric.result_state is FormulaResultState.ESTIMABLE for metric in source.metrics),
            "not_estimable_metric_count": len(not_estimable),
        },
        "evidence_classification": {
            "retrospective": "EXPLORATORY_RETROSPECTIVE",
            "source": run.source.value,
            "evidence": run.evidence.value,
        },
        "configuration": _json_value(configuration),
        "universe_sample": {
            "universe_revision_id": str(configuration.universe_revision.authority_id),
            "universe_revision_sha256": str(configuration.universe_revision.content_sha256),
            "sample_scope_code": configuration.sample_scope_code,
            "sample_member_count": configuration.sample_member_count,
            "sample_roster_sha256": str(configuration.sample_roster_sha256),
            "distinct_trading_session_count": (configuration.distinct_trading_session_count),
            "fold_session_binding_count": configuration.fold_session_binding_count,
        },
        "feature_target_definitions": {
            "feature_roster_sha256": str(configuration.feature_roster_sha256),
            "target_definition_id": str(configuration.target.authority_id),
            "target_version": configuration.target.version,
            "target_definition_sha256": str(configuration.target.content_sha256),
        },
        "model_model_versions": _json_value(source.models),
        "walk_forward_design": {
            "first_session_date": configuration.first_session_date,
            "last_session_date": configuration.last_session_date,
            "walk_forward_policy_sha256": str(configuration.walk_forward_policy_sha256),
            "fold_roster_sha256": str(configuration.fold_roster_sha256),
            "dependency_roster_sha256": str(configuration.dependency_roster_sha256),
            "folds": tuple(
                {
                    "fold_id": str(fold.exploratory_backtest_fold_id),
                    "ordinal": fold.ordinal,
                    "purpose": fold.purpose.value,
                    "purge_sessions": fold.purge_sessions,
                    "embargo_sessions": fold.embargo_sessions,
                    "session_count": len(fold.sessions),
                }
                for fold in run.folds
            ),
        },
        "alpha_funnel_diagnosis": _alpha_funnel(source),
        "baseline_challenger_comparison": baseline_challenger,
        "not_estimable_failure_reasons": {
            "not_estimable_metrics": not_estimable,
            "execution_failure_reasons": source.execution_failure_reasons,
        },
        "limitations": source.limitations,
        "evidence_ceiling": {
            "retrospective": "EXPLORATORY_RETROSPECTIVE",
            "formal_provider": "BLOCKED",
            "formal_pit": "BLOCKED",
            "formal_oos": "NOT_RUN",
            "prospective_proven": "NO",
            "alpha_proven": "NO",
        },
        "recommended_next_experiment": source.recommended_next_experiment,
        "bindings": {
            "evaluation_roster_sha256": str(source.evaluation_roster_sha256),
            "projection_sha256": str(source.content_sha256),
            "code_content_sha256": str(configuration.code_content_sha256),
            "config_content_sha256": str(configuration.config_content_sha256),
        },
    }
    for surface, section in _SURFACE_SECTIONS.items():
        payload[section] = metrics_by_surface[surface]
    return payload


def _metric_payload(metric: BacktestReportMetric) -> dict[str, object]:
    return {
        "acceptance_state": metric.acceptance_state,
        "arm_id": str(metric.arm_id),
        "decimal_value": (None if metric.decimal_value is None else format(metric.decimal_value, "f")),
        "estimable_count": metric.estimable_count,
        "evaluation_metric_id": str(metric.evaluation_metric_id),
        "evaluation_requirement_id": str(metric.evaluation_requirement_id),
        "evaluation_run_id": str(metric.evaluation_run_id),
        "fold_id": None if metric.fold_id is None else str(metric.fold_id),
        "formula_code": metric.formula_code.value,
        "formula_content_sha256": str(metric.formula_content_sha256),
        "formula_version": metric.formula_version,
        "metric_code": metric.metric_code,
        "protocol_metric_id": str(metric.protocol_metric_id),
        "reason_code": metric.reason_code,
        "result_state": metric.result_state.value,
        "scope_kind": metric.scope_kind,
        "slice_key": metric.slice_key,
    }


def _alpha_funnel(source: BacktestReportSource) -> dict[str, object]:
    order = (
        BacktestMetricSurface.DATA,
        BacktestMetricSurface.CANDIDATE,
        BacktestMetricSurface.CONTEXT,
        BacktestMetricSurface.SIGNAL_FORECAST,
        BacktestMetricSurface.PORTFOLIO_RISK,
        BacktestMetricSurface.ECONOMICS,
    )
    for surface in order:
        metrics = tuple(metric for metric in source.metrics if metric.surface is surface)
        if not metrics:
            return {
                "state": "INCOMPLETE_STANDARD_SURFACE",
                "bottleneck_surface": surface.value,
                "reason_codes": ("NO_CANONICAL_EVALUATION_METRIC",),
                "evidence_class": "ENGINEERING_DIAGNOSTIC_ONLY",
            }
        unavailable = tuple(metric.reason_code for metric in metrics if metric.result_state is FormulaResultState.NOT_ESTIMABLE)
        if unavailable:
            return {
                "state": "NOT_ESTIMABLE",
                "bottleneck_surface": surface.value,
                "reason_codes": tuple(dict.fromkeys(unavailable)),
                "evidence_class": "ENGINEERING_DIAGNOSTIC_ONLY",
            }
    return {
        "state": "ESTIMABLE",
        "bottleneck_surface": None,
        "reason_codes": (),
        "evidence_class": "ENGINEERING_DIAGNOSTIC_ONLY",
    }


def _fingerprint_mismatches(
    left: BacktestComparisonFingerprint,
    right: BacktestComparisonFingerprint,
) -> tuple[str, ...]:
    return tuple(
        field.name
        for field in fields(BacktestComparisonFingerprint)
        if field.name != "content_sha256" and getattr(left, field.name) != getattr(right, field.name)
    )


def _metric_deltas(
    left: BacktestReportSource,
    right: BacktestReportSource,
) -> tuple[BacktestMetricDelta, ...]:
    def index(source: BacktestReportSource) -> dict[tuple[str, str], BacktestReportMetric]:
        arm_codes = {arm.exploratory_backtest_arm_id: arm.arm_code for arm in source.run.arms}
        result: dict[tuple[str, str], BacktestReportMetric] = {}
        for metric in source.metrics:
            scope = ":".join(
                (
                    arm_codes[metric.arm_id],
                    metric.scope_kind,
                    "-" if metric.fold_id is None else str(metric.fold_id),
                    "-" if metric.slice_key is None else metric.slice_key,
                )
            )
            result[(metric.metric_code, scope)] = metric
        return result

    left_metrics = index(left)
    right_metrics = index(right)
    shared = tuple(sorted(set(left_metrics).intersection(right_metrics)))
    deltas: list[BacktestMetricDelta] = []
    for metric_code, scope in shared:
        left_metric = left_metrics[(metric_code, scope)]
        right_metric = right_metrics[(metric_code, scope)]
        estimable = left_metric.result_state is FormulaResultState.ESTIMABLE and right_metric.result_state is FormulaResultState.ESTIMABLE
        delta = (
            right_metric.decimal_value - left_metric.decimal_value
            if estimable and right_metric.decimal_value is not None and left_metric.decimal_value is not None
            else None
        )
        deltas.append(
            BacktestMetricDelta(
                metric_code=metric_code,
                scope_key=scope,
                left_value=left_metric.decimal_value,
                right_value=right_metric.decimal_value,
                delta=delta,
                reason_code=("ESTIMABLE_DELTA" if delta is not None else "NOT_ESTIMABLE_COMPARISON"),
            )
        )
    return tuple(deltas)


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (UUID, datetime, date)):
        return value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _markdown_bytes(payload: dict[str, object]) -> bytes:
    summary = payload["executive_summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Standard Backtest Report",
        "",
        f"Run: `{summary['run_code']}` (`{summary['backtest_run_id']}`)",
        "",
    ]
    sections = (
        ("Executive Summary", "executive_summary"),
        ("Evidence Classification", "evidence_classification"),
        ("Configuration", "configuration"),
        ("Data Coverage", "data_coverage"),
        ("Universe / Sample", "universe_sample"),
        ("Feature / Target Definitions", "feature_target_definitions"),
        ("Model / ModelVersion", "model_model_versions"),
        ("Walk-forward Design", "walk_forward_design"),
        ("Candidate Metrics", "candidate_metrics"),
        ("Context Attribution", "context_attribution"),
        ("Signal / Forecast Metrics", "signal_forecast_metrics"),
        ("Portfolio / Risk Metrics", "portfolio_risk_metrics"),
        ("Gross / Net Economics", "gross_net_economics"),
        ("Fold / Time Stability", "fold_time_stability"),
        ("AlphaFunnelDiagnosis", "alpha_funnel_diagnosis"),
        ("Baseline / Challenger Comparison", "baseline_challenger_comparison"),
        ("NOT_ESTIMABLE / Failure Reasons", "not_estimable_failure_reasons"),
        ("Limitations", "limitations"),
        ("Evidence Ceiling", "evidence_ceiling"),
        ("Recommended Next Experiment", "recommended_next_experiment"),
    )
    for heading, key in sections:
        lines.extend(
            (
                f"## {heading}",
                "",
                "```json",
                json.dumps(
                    _json_value(payload[key]),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "```",
                "",
            )
        )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


__all__ = ["BacktestReportApplication"]
