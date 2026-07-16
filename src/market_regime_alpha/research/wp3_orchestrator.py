"""Source-aware composition of Xuntou and Tencent WP-3 Candidate runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

from market_regime_alpha.candidates.directional_accuracy import (
    R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID,
)
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    r5_next_session_opportunity_target_contracts,
)
from market_regime_alpha.data import DataEligibility
from market_regime_alpha.features.rehearsal_baselines import (
    r5_baseline_feature_definitions,
)
from market_regime_alpha.research.provider_candidate_runner import (
    ProviderCandidateRun,
    ProviderCandidateRunOutcome,
    run_provider_candidate_experiment,
)
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
)
from market_regime_alpha.research.provider_routing import (
    CandidateDataSource,
    CandidateRunSourceMode,
    ProviderAvailabilityStatus,
    ProviderCapabilityReport,
    ProviderRoutingError,
    ProviderSelectionDecision,
    select_candidate_data_source,
)
from market_regime_alpha.research.r5_baseline_runner import candidate_evaluation_record
from market_regime_alpha.research.wp3_run_artifacts import (
    WP3FailureArtifactPayload,
    WP3RunArtifactPayload,
    write_wp3_candidate_failure,
    write_wp3_candidate_run,
)
from market_regime_alpha.research.xuntou_provider_adapter import (
    XUNTOU_LIQUIDITY_MEASURE_ID,
    XuntouProviderAdapterError,
    load_xuntou_p0_native_bundle,
)
from market_regime_alpha.universe.eligibility_policy import (
    r5_provider_rehearsal_trading_eligibility_policy_v2,
)


WP3_RUN_SCHEMA_VERSION = "wp3-provider-candidate-run-v1"
WP3_DECISION_TIME_CONVENTION = "14:55:00 Asia/Shanghai"


class WP3ExecutionErrorCode(str, Enum):
    """Stable source-aware execution failures outside the pure router."""

    XUNTOU_BUNDLE_REQUIRED = "WP3_XUNTOU_BUNDLE_REQUIRED"
    XUNTOU_PREFLIGHT_FAILED = "WP3_XUNTOU_PREFLIGHT_FAILED"
    TENCENT_QUALITY_GATE_FAILED = "WP3_TENCENT_QUALITY_GATE_FAILED"
    CANDIDATE_MATERIALIZATION_FAILED = "WP3_CANDIDATE_MATERIALIZATION_FAILED"


class WP3BackendExecutionError(RuntimeError):
    """Backend failure carrying stable code and JSON-ready diagnostic evidence."""

    def __init__(
        self,
        code: WP3ExecutionErrorCode,
        detail: str,
        *,
        evidence: Any = None,
    ) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail
        self.evidence = evidence


@dataclass(frozen=True, slots=True)
class WP3RunRequest:
    """Configuration and identity of one source-aware WP-3 attempt."""

    run_id: str
    source_mode: CandidateRunSourceMode
    minimum_eligibility: DataEligibility
    output_root: Path
    xuntou_bundle: Path | None
    decision_count: int
    code_revision: str
    config_hash: str
    minimum_liquidity_value: float | None

    def __post_init__(self) -> None:
        _require_non_empty("run_id", self.run_id)
        if Path(self.run_id).name != self.run_id:
            raise ValueError("run_id must be a path-safe name")
        if not isinstance(self.source_mode, CandidateRunSourceMode):
            raise TypeError("source_mode must be a CandidateRunSourceMode")
        if not isinstance(self.minimum_eligibility, DataEligibility):
            raise TypeError("minimum_eligibility must be a DataEligibility")
        if self.minimum_eligibility is DataEligibility.FORMAL_RESEARCH:
            raise ValueError("WP-3 cannot request FORMAL_RESEARCH")
        if not isinstance(self.output_root, Path):
            raise TypeError("output_root must be a Path")
        if self.xuntou_bundle is not None and not isinstance(self.xuntou_bundle, Path):
            raise TypeError("xuntou_bundle must be a Path or None")
        if isinstance(self.decision_count, bool) or not isinstance(self.decision_count, int):
            raise TypeError("decision_count must be an integer")
        if self.decision_count <= 0:
            raise ValueError("decision_count must be positive")
        _require_non_empty("code_revision", self.code_revision)
        _require_non_empty("config_hash", self.config_hash)
        if self.minimum_liquidity_value is not None:
            if isinstance(self.minimum_liquidity_value, bool) or not math.isfinite(
                float(self.minimum_liquidity_value)
            ):
                raise ValueError("minimum_liquidity_value must be positive and finite")
            if float(self.minimum_liquidity_value) <= 0.0:
                raise ValueError("minimum_liquidity_value must be positive and finite")


@dataclass(frozen=True, slots=True)
class XuntouWP3Preflight:
    """Xuntou report plus an optional validated normalized-export artifact."""

    report: ProviderCapabilityReport
    prepared: object | None

    def __post_init__(self) -> None:
        if self.report.source is not CandidateDataSource.XUNTOU:
            raise ValueError("Xuntou preflight report must describe XUNTOU")
        if self.report.availability_status is ProviderAvailabilityStatus.AVAILABLE:
            if self.prepared is None:
                raise ValueError("available Xuntou preflight requires prepared input")
        elif self.prepared is not None:
            raise ValueError("unavailable or invalid Xuntou preflight cannot carry prepared input")


@dataclass(frozen=True, slots=True)
class WP3BackendResult:
    """Provider-specific execution normalized only for run-artifact publication."""

    source: CandidateDataSource
    data_eligibility: DataEligibility
    dataset_id: DatasetId
    provider_references: Any
    source_artifacts: Any
    quality: Any
    candidate_panel_summary: Any
    b0_b1_evaluation: Any
    limitations: tuple[str, ...]
    manifest_details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.source, CandidateDataSource):
            raise TypeError("source must be a CandidateDataSource")
        expected = (
            DataEligibility.REHEARSAL
            if self.source is CandidateDataSource.XUNTOU
            else DataEligibility.EXPLORATORY
        )
        if self.data_eligibility is not expected:
            raise ValueError(
                f"{self.source.value} WP-3 result must remain {expected.value}"
            )
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("backend limitations must be unique")


class XuntouWP3Backend(Protocol):
    """Prepared-input boundary for the canonical Xuntou route."""

    def preflight(self, bundle: Path | None) -> XuntouWP3Preflight: ...

    def execute(
        self,
        request: WP3RunRequest,
        preflight: XuntouWP3Preflight,
    ) -> WP3BackendResult: ...


class TencentWP3Backend(Protocol):
    """Temporary EXPLORATORY Tencent composite route."""

    def capability_report(self) -> ProviderCapabilityReport: ...

    def execute(self, request: WP3RunRequest) -> WP3BackendResult: ...


class NormalizedXuntouWP3Backend:
    """Strict normalized-export backend with no import-time XtQuant dependency."""

    def preflight(self, bundle: Path | None) -> XuntouWP3Preflight:
        if bundle is None:
            return XuntouWP3Preflight(
                report=_xuntou_report(
                    ProviderAvailabilityStatus.UNAVAILABLE,
                    input_identity="xuntou-normalized-bundle:not-supplied",
                    limitations=("XUNTOU_NORMALIZED_BUNDLE_NOT_SUPPLIED",),
                ),
                prepared=None,
            )
        if not bundle.is_file():
            return XuntouWP3Preflight(
                report=_xuntou_report(
                    ProviderAvailabilityStatus.INVALID,
                    input_identity=f"xuntou-normalized-bundle:{bundle}",
                    limitations=("XUNTOU_NORMALIZED_BUNDLE_PATH_INVALID",),
                ),
                prepared=None,
            )
        try:
            artifact = load_xuntou_p0_native_bundle(bundle)
        except (OSError, XuntouProviderAdapterError) as exc:
            return XuntouWP3Preflight(
                report=_xuntou_report(
                    ProviderAvailabilityStatus.INVALID,
                    input_identity=f"xuntou-normalized-bundle:{bundle}",
                    limitations=(f"XUNTOU_PREFLIGHT_ERROR={exc}",),
                ),
                prepared=None,
            )
        input_identity = (
            f"artifact={artifact.artifact_id};dataset={artifact.dataset_contract.dataset_id}"
        )
        return XuntouWP3Preflight(
            report=_xuntou_report(
                ProviderAvailabilityStatus.AVAILABLE,
                input_identity=input_identity,
                limitations=artifact.dataset_contract.limitations,
            ),
            prepared=artifact,
        )

    def execute(
        self,
        request: WP3RunRequest,
        preflight: XuntouWP3Preflight,
    ) -> WP3BackendResult:
        if not isinstance(preflight.prepared, ProviderRehearsalMarketArtifact):
            raise WP3BackendExecutionError(
                WP3ExecutionErrorCode.XUNTOU_PREFLIGHT_FAILED,
                "validated ProviderRehearsalMarketArtifact is absent",
            )
        if request.minimum_liquidity_value is None:
            raise WP3BackendExecutionError(
                WP3ExecutionErrorCode.CANDIDATE_MATERIALIZATION_FAILED,
                "Xuntou Candidate runs require explicit --minimum-liquidity-value",
            )
        artifact = preflight.prepared
        policy = r5_provider_rehearsal_trading_eligibility_policy_v2(
            minimum_liquidity_value=request.minimum_liquidity_value,
            liquidity_measure_id=XUNTOU_LIQUIDITY_MEASURE_ID,
        )
        materialized_at = AsOfTime(
            max(
                *(item.retrieved_at.value for item in artifact.source_artifacts),
                *(item.available_at.value for item in artifact.next_session_bars),
            )
        )
        run = run_provider_candidate_experiment(
            market_artifact=artifact,
            eligibility_policy=policy,
            materialized_at=materialized_at,
            code_revision=request.code_revision,
            config_hash=request.config_hash,
            decision_count=request.decision_count,
        )
        return _xuntou_backend_result(artifact=artifact, run=run, policy=policy)


def execute_wp3_candidate_run(
    request: WP3RunRequest,
    *,
    tencent_backend: TencentWP3Backend,
    xuntou_backend: XuntouWP3Backend | None = None,
) -> Path:
    """Select one backend, execute it, and publish success or explicit failure evidence."""

    xuntou = xuntou_backend or NormalizedXuntouWP3Backend()
    preflight = xuntou.preflight(request.xuntou_bundle)
    tencent_report = tencent_backend.capability_report()

    if (
        request.source_mode is CandidateRunSourceMode.XUNTOU
        and request.xuntou_bundle is None
    ):
        return _write_failure(
            request,
            code=WP3ExecutionErrorCode.XUNTOU_BUNDLE_REQUIRED.value,
            detail="explicit Xuntou mode requires --xuntou-bundle",
            data_eligibility=DataEligibility.UNQUALIFIED,
            evidence={"xuntou_report": preflight.report},
        )

    try:
        selection = select_candidate_data_source(
            mode=request.source_mode,
            minimum_eligibility=request.minimum_eligibility,
            xuntou=preflight.report,
            tencent=tencent_report,
        )
    except ProviderRoutingError as exc:
        code = (
            WP3ExecutionErrorCode.XUNTOU_PREFLIGHT_FAILED.value
            if preflight.report.availability_status is ProviderAvailabilityStatus.INVALID
            else exc.code.value
        )
        return _write_failure(
            request,
            code=code,
            detail=str(exc),
            data_eligibility=DataEligibility.UNQUALIFIED,
            evidence={
                "route_error_code": exc.code.value,
                "attempts": exc.attempts,
                "xuntou_report": preflight.report,
                "tencent_report": tencent_report,
            },
        )

    try:
        result = (
            xuntou.execute(request, preflight)
            if selection.selected_source is CandidateDataSource.XUNTOU
            else tencent_backend.execute(request)
        )
        _validate_selected_result(selection, result)
    except WP3BackendExecutionError as exc:
        return _write_failure(
            request,
            code=exc.code.value,
            detail=exc.detail,
            data_eligibility=selection.selected_data_eligibility,
            evidence={"provider_selection": selection, "backend_evidence": exc.evidence},
        )
    except (KeyError, LookupError, ValueError) as exc:
        return _write_failure(
            request,
            code=WP3ExecutionErrorCode.CANDIDATE_MATERIALIZATION_FAILED.value,
            detail=str(exc),
            data_eligibility=selection.selected_data_eligibility,
            evidence={"provider_selection": selection, "exception_type": type(exc).__name__},
        )

    limitations = _unique((*selection.limitations, *result.limitations))
    manifest = {
        **dict(result.manifest_details),
        "schema_version": WP3_RUN_SCHEMA_VERSION,
        "run_id": request.run_id,
        "code_revision": request.code_revision,
        "config_hash": request.config_hash,
        "requested_source_mode": request.source_mode.value,
        "minimum_data_eligibility": request.minimum_eligibility.value,
        "selected_source": selection.selected_source.value,
        "data_eligibility": result.data_eligibility.value,
        "provider_selection_policy": selection.policy_version,
        "provider_selection_decision_id": selection.decision_id,
        "dataset_id": str(result.dataset_id),
        "provider_references": result.provider_references,
        "evaluation_protocol_ids": [
            R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID
        ],
        "decision_time_convention": WP3_DECISION_TIME_CONVENTION,
        "limitations": list(limitations),
    }
    payload = WP3RunArtifactPayload(
        manifest=manifest,
        provider_selection=selection,
        source_artifacts=result.source_artifacts,
        quality=result.quality,
        candidate_panel_summary=result.candidate_panel_summary,
        b0_b1_evaluation=result.b0_b1_evaluation,
        limitations={"items": list(limitations)},
        report=_render_report(
            request=request,
            selection=selection,
            result=result,
            limitations=limitations,
        ),
    )
    return write_wp3_candidate_run(
        root=request.output_root,
        run_id=request.run_id,
        payload=payload,
    )


def _xuntou_backend_result(
    *,
    artifact: ProviderRehearsalMarketArtifact,
    run: ProviderCandidateRun,
    policy: object,
) -> WP3BackendResult:
    panel_summary = {
        "outcome": run.outcome.value,
        "decision_times": [item.isoformat() for item in run.decision_times],
        "decision_diagnostics": run.decision_diagnostics,
        "targets": [
            {
                "target_id": str(target.target_id),
                "panel_dataset_id": str(target.panel.dataset_id),
                "slice_count": target.panel.slice_count,
                "row_count": target.panel.row_count,
                "data_eligibility": target.panel.data_eligibility.value,
            }
            for target in run.target_runs
        ],
    }
    if run.outcome is ProviderCandidateRunOutcome.NO_CANDIDATES_AFTER_ELIGIBILITY:
        evaluation: dict[str, Any] = {
            "status": "NOT_PRODUCED",
            "reason": run.outcome.value,
            "targets": [],
        }
    else:
        evaluation = {
            "status": "PRODUCED",
            "selection_policy": "FIXED_UNTUNED_NO_WINNER_SELECTION",
            "targets": [
                {
                    "target_id": str(target.target_id),
                    "b0": [
                        candidate_evaluation_record(item)
                        for item in target.b0_evaluations
                    ],
                    "b1": [
                        candidate_evaluation_record(item)
                        for item in target.b1_evaluations
                    ],
                }
                for target in run.target_runs
            ],
        }
    feature_ids = [
        str(item.feature_id) for item in r5_baseline_feature_definitions()
    ]
    target_ids = [
        str(item.target_id) for item in r5_next_session_opportunity_target_contracts()
    ]
    return WP3BackendResult(
        source=CandidateDataSource.XUNTOU,
        data_eligibility=run.data_eligibility,
        dataset_id=run.source_dataset_id,
        provider_references=artifact.dataset_contract.provider_references,
        source_artifacts=artifact.source_artifacts,
        quality={
            "status": "ACCEPTED",
            "market_artifact_id": str(run.market_artifact_id),
            "eligibility_artifact_id": str(run.eligibility_artifact_id),
            "eligibility_policy_artifact_id": str(run.eligibility_policy_artifact_id),
            "pit_correct_for_scope": artifact.dataset_contract.pit_correct_for_scope,
            "candidate_outcome": run.outcome.value,
        },
        candidate_panel_summary=panel_summary,
        b0_b1_evaluation=evaluation,
        limitations=run.limitations,
        manifest_details={
            "market_artifact_id": str(run.market_artifact_id),
            "feature_definition_ids": feature_ids,
            "target_ids": target_ids,
            "eligibility_policy": getattr(policy, "policy_version"),
        },
    )


def _xuntou_report(
    status: ProviderAvailabilityStatus,
    *,
    input_identity: str,
    limitations: tuple[str, ...],
) -> ProviderCapabilityReport:
    return ProviderCapabilityReport(
        source=CandidateDataSource.XUNTOU,
        availability_status=status,
        maximum_data_eligibility=DataEligibility.REHEARSAL,
        supported_evidence=(
            "TRADING_CALENDAR",
            "SECURITY_IDENTITY",
            "UNIVERSE_MEMBERSHIP_WITH_UNVERIFIED_PIT",
            "DAILY_OHLCV_AMOUNT",
            "DECISION_TIME_REFERENCE_PRICE",
            "NEXT_SESSION_OHLC",
        ),
        unsupported_evidence=("FORMAL_PIT", "FORMAL_RESEARCH", "FILLABILITY"),
        limitations=_unique(limitations),
        input_identity=input_identity,
    )


def _validate_selected_result(
    selection: ProviderSelectionDecision,
    result: WP3BackendResult,
) -> None:
    if result.source is not selection.selected_source:
        raise ValueError("backend result source differs from provider selection")
    if result.data_eligibility is not selection.selected_data_eligibility:
        raise ValueError("backend result authority differs from provider selection")


def _write_failure(
    request: WP3RunRequest,
    *,
    code: str,
    detail: str,
    data_eligibility: DataEligibility,
    evidence: Mapping[str, Any],
) -> Path:
    failure = {"code": code, "message": detail, **dict(evidence)}
    manifest = {
        "schema_version": WP3_RUN_SCHEMA_VERSION,
        "run_id": request.run_id,
        "code_revision": request.code_revision,
        "config_hash": request.config_hash,
        "requested_source_mode": request.source_mode.value,
        "minimum_data_eligibility": request.minimum_eligibility.value,
        "data_eligibility": data_eligibility.value,
        "status": "FAILED",
    }
    return write_wp3_candidate_failure(
        root=request.output_root,
        run_id=request.run_id,
        payload=WP3FailureArtifactPayload(manifest=manifest, failure=failure),
    )


def _render_report(
    *,
    request: WP3RunRequest,
    selection: ProviderSelectionDecision,
    result: WP3BackendResult,
    limitations: tuple[str, ...],
) -> str:
    return "\n".join(
        (
            "# WP-3 Provider-Backed Candidate Run",
            "",
            "## Authority",
            "",
            f"- Selected source: {selection.selected_source.value}",
            f"- Data eligibility: {result.data_eligibility.value}",
            f"- Requested minimum: {request.minimum_eligibility.value}",
            "- Candidate scores are descriptive rankings, not probabilities or trade actions.",
            "- This artifact does not constitute an Alpha or FORMAL_RESEARCH claim.",
            "",
            "## Outcome",
            "",
            f"- Dataset: {result.dataset_id}",
            f"- Candidate outcome: {result.candidate_panel_summary.get('outcome', 'RECORDED')}",
            "- B0/B1 uses the fixed untuned ladder with no winner selection.",
            "",
            "## Limitations",
            "",
            *(f"- {item}" for item in limitations),
            "",
        )
    )


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
