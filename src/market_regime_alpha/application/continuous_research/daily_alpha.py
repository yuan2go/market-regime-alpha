"""Immutable daily Alpha projection inside the sole Continuous control plane.

The projection does not replace Dataset, Feature, Candidate, Signal, Forecast or
Strategy owners.  It freezes their exact identities plus a human-readable
per-symbol view before any future Outcome can exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.candidates.policy import research_panel_dataset_reference
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


DAILY_ALPHA_PREDICTION_KIND = "DAILY_ALPHA_PREDICTION_SNAPSHOT"
DAILY_ALPHA_PREDICTION_SCHEMA_V1 = "daily-alpha-prediction-snapshot/v1"
DAILY_ALPHA_PREDICTION_SCHEMA_V2 = "daily-alpha-prediction-snapshot/v2"
DAILY_ALPHA_PREDICTION_SCHEMA = "daily-alpha-prediction-snapshot/v3"
EVIDENCE_DEPENDENCY_NOT_SATISFIED = "EVIDENCE_DEPENDENCY_NOT_SATISFIED"


class DailyAlphaActivationStatus(str, Enum):
    VALIDATED_CHALLENGER_ACTIVE = "VALIDATED_CHALLENGER_ACTIVE"
    VALIDATED_CHALLENGER_INACTIVE = "VALIDATED_CHALLENGER_INACTIVE"


@dataclass(frozen=True, slots=True)
class DailyAlphaEvidenceGate:
    status: DailyAlphaActivationStatus
    correctness_reference: ValidationArtifactReference | None
    external_validation_reference: ValidationArtifactReference | None
    candidate_policy_reference: ValidationArtifactReference | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _ordered_text("gate reason_codes", self.reason_codes, required=True)
        references = (
            self.correctness_reference,
            self.external_validation_reference,
            self.candidate_policy_reference,
        )
        if self.status is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE:
            if any(item is None for item in references):
                raise ValueError("active daily Alpha gate requires every Evidence owner")
            if EVIDENCE_DEPENDENCY_NOT_SATISFIED in self.reason_codes:
                raise ValueError("active daily Alpha gate cannot report unmet Evidence")
        elif EVIDENCE_DEPENDENCY_NOT_SATISFIED not in self.reason_codes:
            raise ValueError("inactive daily Alpha gate requires explicit dependency reason")

    @classmethod
    def inactive(
        cls,
        *,
        correctness_reference: ValidationArtifactReference | None = None,
        external_validation_reference: ValidationArtifactReference | None = None,
        candidate_policy_reference: ValidationArtifactReference | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> DailyAlphaEvidenceGate:
        return cls(
            DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE,
            correctness_reference,
            external_validation_reference,
            candidate_policy_reference,
            tuple(sorted({EVIDENCE_DEPENDENCY_NOT_SATISFIED, *reason_codes})),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "correctness_reference": _optional_validation_reference(
                self.correctness_reference
            ),
            "external_validation_reference": _optional_validation_reference(
                self.external_validation_reference
            ),
            "candidate_policy_reference": _optional_validation_reference(
                self.candidate_policy_reference
            ),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DailyAlphaEvidenceGate:
        _fields(
            payload,
            {
                "status",
                "correctness_reference",
                "external_validation_reference",
                "candidate_policy_reference",
                "reason_codes",
            },
            "Daily Alpha Evidence gate",
        )
        return cls(
            DailyAlphaActivationStatus(str(payload["status"])),
            _validation_reference(payload["correctness_reference"]),
            _validation_reference(payload["external_validation_reference"]),
            _validation_reference(payload["candidate_policy_reference"]),
            _strings(payload["reason_codes"]),
        )


class HistoricalEvidenceReader(Protocol):
    def list_for_run(
        self, run_id: ArtifactId
    ) -> tuple[HistoricalResearchEvidence, ...]: ...


def assess_daily_alpha_evidence_gate(
    evidence: tuple[HistoricalResearchEvidence, ...],
    *,
    root_candidate_policy_reference: ValidationArtifactReference | None = None,
    superseded_references: tuple[ValidationArtifactReference, ...] = (),
) -> DailyAlphaEvidenceGate:
    """Admit one explicitly configured immutable Evidence lineage.

    No database recency, metric ordering, or implicit policy selection is used.
    The Candidate Policy Evidence root must bind the exact External,
    Correctness and Discovery owners plus their Experiment, hypothesis, dataset,
    factor-family and run/command lineage.
    """

    if root_candidate_policy_reference is None:
        return DailyAlphaEvidenceGate.inactive(
            reason_codes=("EVIDENCE_ROOT_NOT_CONFIGURED",)
        )
    by_reference: dict[ValidationArtifactReference, HistoricalResearchEvidence] = {}
    try:
        for item in evidence:
            item.verify_identity()
            by_reference[item.reference] = item
    except ValueError:
        return DailyAlphaEvidenceGate.inactive(
            candidate_policy_reference=root_candidate_policy_reference,
            reason_codes=("EVIDENCE_HASH_DRIFT",),
        )
    candidate = by_reference.get(root_candidate_policy_reference)
    if candidate is None:
        return DailyAlphaEvidenceGate.inactive(
            candidate_policy_reference=root_candidate_policy_reference,
            reason_codes=("EVIDENCE_LINEAGE_INCOMPLETE",),
        )
    try:
        correctness, external, discovery, contexts = _daily_alpha_lineage(
            candidate=candidate,
            by_reference=by_reference,
        )
    except _DailyAlphaLineageError as exc:
        return DailyAlphaEvidenceGate.inactive(
            correctness_reference=exc.correctness_reference,
            external_validation_reference=exc.external_reference,
            candidate_policy_reference=root_candidate_policy_reference,
            reason_codes=(exc.reason_code,),
        )
    chain_references = {
        candidate.reference,
        external.reference,
        correctness.reference,
        discovery.reference,
        *(item.reference for item in contexts),
    }
    if chain_references.intersection(superseded_references):
        return DailyAlphaEvidenceGate.inactive(
            correctness_reference=correctness.reference,
            external_validation_reference=external.reference,
            candidate_policy_reference=candidate.reference,
            reason_codes=("EVIDENCE_SUPERSEDED",),
        )
    reasons: list[str] = []
    if (
        correctness.classification is not ResearchFinding.POSITIVE
        or correctness.payload.get("status") != "CORRECTNESS_SUPPORTED"
    ):
        reasons.append("CORRECTNESS_NOT_SUPPORTED")
    if (
        external.classification is not ResearchFinding.POSITIVE
        or external.payload.get("qualification_status") != "SUPPORTED"
    ):
        reasons.append("EXTERNAL_VALIDATION_NOT_SUPPORTED")
    if discovery.classification is not ResearchFinding.POSITIVE:
        reasons.append("DISCOVERY_NOT_SUPPORTED")
    if any(
        item.classification is not ResearchFinding.POSITIVE
        or item.payload.get("status") not in {"AMPLIFIER", "SUPPRESSOR"}
        for item in contexts
    ):
        reasons.append("CONTEXT_NOT_SUPPORTED")
    if (
        candidate.classification is not ResearchFinding.POSITIVE
        or candidate.payload.get("activation_status") != "CHALLENGER_ACTIVE"
        or candidate.payload.get("stability") != "STABLE"
    ):
        reasons.append("CANDIDATE_CHALLENGER_NOT_ACTIVE")
    if reasons:
        return DailyAlphaEvidenceGate.inactive(
            correctness_reference=correctness.reference,
            external_validation_reference=external.reference,
            candidate_policy_reference=candidate.reference,
            reason_codes=tuple(reasons),
        )
    return DailyAlphaEvidenceGate(
        DailyAlphaActivationStatus.VALIDATED_CHALLENGER_ACTIVE,
        correctness.reference,
        external.reference,
        candidate.reference,
        reason_codes=("EVIDENCE_DEPENDENCIES_SUPPORTED",),
    )


class _DailyAlphaLineageError(ValueError):
    def __init__(
        self,
        reason_code: str,
        *,
        correctness_reference: ValidationArtifactReference | None = None,
        external_reference: ValidationArtifactReference | None = None,
    ) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.correctness_reference = correctness_reference
        self.external_reference = external_reference


def daily_alpha_admission_evidence_references(
    candidate: HistoricalResearchEvidence,
) -> tuple[ValidationArtifactReference, ...]:
    """Return the exact upstream Evidence references declared by one root."""

    try:
        admission = _mapping(candidate.payload.get("daily_alpha_admission"))
        if admission.get("schema_version") != "daily-alpha-evidence-admission/v2":
            raise ValueError("unsupported Daily Alpha admission schema")
        core = (
            _required_validation_reference(
                admission, "discovery_evidence_reference"
            ),
            _required_validation_reference(
                admission, "correctness_evidence_reference"
            ),
            _required_validation_reference(
                admission, "external_validation_evidence_reference"
            ),
        )
        return (*core, *_context_evidence_references(admission))
    except (KeyError, ValueError) as exc:
        raise _DailyAlphaLineageError("EVIDENCE_LINEAGE_INVALID") from exc


def _daily_alpha_lineage(
    *,
    candidate: HistoricalResearchEvidence,
    by_reference: Mapping[
        ValidationArtifactReference, HistoricalResearchEvidence
    ],
) -> tuple[
    HistoricalResearchEvidence,
    HistoricalResearchEvidence,
    HistoricalResearchEvidence,
    tuple[HistoricalResearchEvidence, ...],
]:
    correctness_reference: ValidationArtifactReference | None = None
    external_reference: ValidationArtifactReference | None = None
    try:
        if candidate.evidence_kind is not HistoricalEvidenceKind.CANDIDATE_POLICY:
            raise ValueError("root is not Candidate Policy Evidence")
        admission = _mapping(candidate.payload.get("daily_alpha_admission"))
        if admission.get("schema_version") != "daily-alpha-evidence-admission/v2":
            raise ValueError("unsupported Daily Alpha admission schema")
        discovery_reference = _required_validation_reference(
            admission, "discovery_evidence_reference"
        )
        correctness_reference = _required_validation_reference(
            admission, "correctness_evidence_reference"
        )
        external_reference = _required_validation_reference(
            admission, "external_validation_evidence_reference"
        )
        candidate_policy_reference = _required_validation_reference(
            admission, "candidate_policy_reference"
        )
        dataset_reference = _required_validation_reference(
            admission, "candidate_dataset_reference"
        )
        external_experiment_reference = _required_validation_reference(
            admission, "external_experiment_reference"
        )
        hypothesis_reference = _required_validation_reference(
            admission, "frozen_hypothesis_reference"
        )
        context_references = _context_evidence_references(admission)
        required_candidate_sources = {
            discovery_reference,
            correctness_reference,
            external_reference,
            candidate_policy_reference,
            dataset_reference,
            external_experiment_reference,
            hypothesis_reference,
            *context_references,
        }
        if not required_candidate_sources.issubset(candidate.source_references):
            raise ValueError("Candidate Evidence source lineage is incomplete")
        discovery = by_reference[discovery_reference]
        correctness = by_reference[correctness_reference]
        external = by_reference[external_reference]
        contexts = tuple(by_reference[item] for item in context_references)
        if (
            discovery.evidence_kind is not HistoricalEvidenceKind.ALPHA_ABLATION
            or correctness.evidence_kind
            is not HistoricalEvidenceKind.ALPHA_CORRECTNESS
            or external.evidence_kind
            is not HistoricalEvidenceKind.EXTERNAL_VALIDATION
            or any(
                item.evidence_kind is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL
                for item in contexts
            )
        ):
            raise ValueError("Evidence kind drifted")
        if not {discovery.reference, correctness.reference}.issubset(
            external.source_references
        ):
            raise ValueError("External Evidence does not bind upstream Evidence")
        external_experiment = _mapping(external.payload.get("experiment"))
        embedded_experiment_reference = ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            ArtifactId(str(external_experiment["experiment_id"])),
            str(external_experiment["experiment_hash"]),
        )
        if (
            embedded_experiment_reference != external.experiment_reference
            or embedded_experiment_reference != external_experiment_reference
            or candidate.experiment_reference != external_experiment_reference
        ):
            raise ValueError("External Experiment identity drifted")
        if (
            ValidationArtifactReference.from_canonical_dict(
                _mapping(external_experiment["correctness_evidence_reference"])
            )
            != correctness.reference
        ):
            raise ValueError("External Correctness lineage drifted")
        hypothesis = _mapping(external_experiment["hypothesis"])
        embedded_hypothesis_reference = ValidationArtifactReference(
            "FROZEN_ALPHA_HYPOTHESIS",
            ArtifactId(str(hypothesis["hypothesis_id"])),
            str(hypothesis["hypothesis_hash"]),
        )
        if embedded_hypothesis_reference != hypothesis_reference:
            raise ValueError("frozen hypothesis identity drifted")
        if (
            ValidationArtifactReference.from_canonical_dict(
                _mapping(hypothesis["discovery_evidence_reference"])
            )
            != discovery.reference
        ):
            raise ValueError("Discovery lineage drifted")
        factor_directions = _factor_directions(admission.get("factor_directions"))
        if (
            factor_directions
            != _factor_directions(hypothesis.get("factor_directions"))
            or factor_directions
            != _factor_directions(external.payload.get("validated_factors"))
        ):
            raise ValueError("Factor family/direction drifted")
        panels = tuple(
            ValidationArtifactReference.from_canonical_dict(_mapping(item))
            for item in _sequence(
                external_experiment.get("validation_panel_references")
            )
        )
        if research_panel_dataset_reference(panels) != dataset_reference:
            raise ValueError("Candidate/External dataset drifted")
        for context in contexts:
            if (
                context.experiment_reference != external_experiment_reference
                or external.reference not in context.source_references
            ):
                raise ValueError("Context/External Experiment lineage drifted")
            evaluation = _mapping(context.payload.get("evaluation"))
            definition_reference = ValidationArtifactReference.from_canonical_dict(
                _mapping(evaluation["definition_reference"])
            )
            context_panels = tuple(
                item
                for item in context.source_references
                if item.artifact_kind
                in {"RESEARCH_PANEL", "HISTORICAL_RESEARCH_PANEL"}
            )
            if (
                definition_reference not in context.source_references
                or not context_panels
                or research_panel_dataset_reference(context_panels)
                != dataset_reference
            ):
                raise ValueError("Context owner/Dataset lineage drifted")
        _verify_lineage_stages(
            admission.get("lineage_stages"),
            ("DISCOVERY", discovery),
            ("CORRECTNESS", correctness),
            ("EXTERNAL_VALIDATION", external),
            *(("CONTEXT_CONDITIONAL", item) for item in contexts),
        )
        return correctness, external, discovery, contexts
    except (KeyError, TypeError, ValueError) as exc:
        raise _DailyAlphaLineageError(
            "EVIDENCE_LINEAGE_INCOMPLETE",
            correctness_reference=correctness_reference,
            external_reference=external_reference,
        ) from exc


def _required_validation_reference(
    payload: Mapping[str, Any], name: str
) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(_mapping(payload[name]))


def _factor_directions(value: object) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for item in _sequence(value):
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], str)
            or not item[1].strip()
        ):
            raise ValueError("Factor direction lineage is malformed")
        result.append((item[0], item[1]))
    parsed = tuple(result)
    if not parsed or parsed != tuple(sorted(set(parsed))):
        raise ValueError("Factor directions must be non-empty, unique and sorted")
    return parsed


def _context_evidence_references(
    admission: Mapping[str, Any],
) -> tuple[ValidationArtifactReference, ...]:
    references = tuple(
        ValidationArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(admission.get("context_evidence_references"))
    )
    if references != tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    ):
        raise ValueError("Context Evidence references must be unique and sorted")
    return references


def _verify_lineage_stages(
    value: object,
    *expected: tuple[str, HistoricalResearchEvidence],
) -> None:
    stages = tuple(_mapping(item) for item in _sequence(value))
    projected = tuple(
        (
            str(item["stage"]),
            str(item["run_id"]),
            str(item["command_hash"]),
            str(item["experiment_id"]),
            str(item["experiment_hash"]),
        )
        for item in stages
    )
    actual = tuple(
        (
            stage,
            str(evidence.run_id),
            evidence.command_hash,
            str(evidence.experiment_reference.artifact_id),
            evidence.experiment_reference.content_hash,
        )
        for stage, evidence in expected
    )
    if projected != actual:
        raise ValueError("Evidence run/command/Experiment lineage drifted")


@dataclass(frozen=True, slots=True)
class DailyAlphaPathForecastProjection:
    reference: RuntimeArtifactReference
    forecast_status: str
    expected_mfe: str | None
    expected_mae: str | None
    return_quantiles: tuple[tuple[str, str | None], ...]
    usable_sample_count: int
    excluded_sample_count: int
    calibration_status: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reference.reference_kind != "PATH_FORECAST":
            raise ValueError("Path Forecast projection requires its typed owner")
        require_text("Path Forecast status", self.forecast_status)
        require_text("Path Forecast calibration status", self.calibration_status)
        if min(self.usable_sample_count, self.excluded_sample_count) < 0:
            raise ValueError("Path Forecast sample counts cannot be negative")
        _ordered_pairs("Path Forecast return quantiles", self.return_quantiles)
        _ordered_text("Path Forecast reason_codes", self.reason_codes, required=True)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.to_canonical_dict(),
            "forecast_status": self.forecast_status,
            "expected_mfe": self.expected_mfe,
            "expected_mae": self.expected_mae,
            "return_quantiles": _pairs_payload(self.return_quantiles),
            "usable_sample_count": self.usable_sample_count,
            "excluded_sample_count": self.excluded_sample_count,
            "calibration_status": self.calibration_status,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaPathForecastProjection:
        _fields(
            payload,
            {
                "reference",
                "forecast_status",
                "expected_mfe",
                "expected_mae",
                "return_quantiles",
                "usable_sample_count",
                "excluded_sample_count",
                "calibration_status",
                "reason_codes",
            },
            "Daily Alpha Path Forecast projection",
        )
        return cls(
            reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["reference"])
            ),
            forecast_status=str(payload["forecast_status"]),
            expected_mfe=_optional_text(payload["expected_mfe"]),
            expected_mae=_optional_text(payload["expected_mae"]),
            return_quantiles=_pairs(payload["return_quantiles"]),
            usable_sample_count=int(payload["usable_sample_count"]),
            excluded_sample_count=int(payload["excluded_sample_count"]),
            calibration_status=str(payload["calibration_status"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DailyAlphaConditionalForecastProjection:
    availability_status: str
    reference: RuntimeArtifactReference | None
    selected_expected_return: str | None
    prediction_uncertainty: str | None
    model_reference: RuntimeArtifactReference | None
    baseline_reference: RuntimeArtifactReference | None
    calibration_status: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.availability_status not in {
            "AVAILABLE_FOR_RESEARCH",
            "DATA_INSUFFICIENT",
            "NOT_AVAILABLE",
        }:
            raise ValueError("unsupported Conditional Forecast availability")
        _ordered_text(
            "Conditional Forecast reason_codes", self.reason_codes, required=True
        )
        if self.reference is not None and (
            self.reference.reference_kind != "CONDITIONAL_FORECAST_RESULT"
        ):
            raise ValueError("Conditional Forecast projection owner kind drifted")
        values = (
            self.selected_expected_return,
            self.prediction_uncertainty,
            self.model_reference,
            self.baseline_reference,
        )
        if self.availability_status == "AVAILABLE_FOR_RESEARCH":
            if self.reference is None or self.selected_expected_return is None:
                raise ValueError("available Conditional Forecast owner is incomplete")
            if self.model_reference is None or self.baseline_reference is None:
                raise ValueError("available Conditional Forecast lineage is incomplete")
        elif self.availability_status == "DATA_INSUFFICIENT":
            if self.reference is None or self.baseline_reference is None:
                raise ValueError("insufficient Conditional Forecast owner is incomplete")
            if any(
                item is not None
                for item in (
                    self.selected_expected_return,
                    self.prediction_uncertainty,
                    self.model_reference,
                )
            ):
                raise ValueError(
                    "insufficient Conditional Forecast cannot carry estimates"
                )
        elif any(item is not None for item in values):
            raise ValueError("unavailable Conditional Forecast cannot carry estimates")

    @classmethod
    def not_available(
        cls,
        *reason_codes: str,
    ) -> DailyAlphaConditionalForecastProjection:
        return cls(
            availability_status="NOT_AVAILABLE",
            reference=None,
            selected_expected_return=None,
            prediction_uncertainty=None,
            model_reference=None,
            baseline_reference=None,
            calibration_status="NOT_AVAILABLE",
            reason_codes=tuple(
                sorted(
                    set(
                        reason_codes
                        or ("CONDITIONAL_FORECAST_OWNER_NOT_AVAILABLE",)
                    )
                )
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "availability_status": self.availability_status,
            "reference": _optional_runtime_reference(self.reference),
            "selected_expected_return": self.selected_expected_return,
            "prediction_uncertainty": self.prediction_uncertainty,
            "model_reference": _optional_runtime_reference(self.model_reference),
            "baseline_reference": _optional_runtime_reference(self.baseline_reference),
            "calibration_status": self.calibration_status,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaConditionalForecastProjection:
        _fields(
            payload,
            {
                "availability_status",
                "reference",
                "selected_expected_return",
                "prediction_uncertainty",
                "model_reference",
                "baseline_reference",
                "calibration_status",
                "reason_codes",
            },
            "Daily Alpha Conditional Forecast projection",
        )
        return cls(
            availability_status=str(payload["availability_status"]),
            reference=_runtime_reference(payload["reference"]),
            selected_expected_return=_optional_text(
                payload["selected_expected_return"]
            ),
            prediction_uncertainty=_optional_text(payload["prediction_uncertainty"]),
            model_reference=_runtime_reference(payload["model_reference"]),
            baseline_reference=_runtime_reference(payload["baseline_reference"]),
            calibration_status=str(payload["calibration_status"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DailyAlphaSymbolProjection:
    symbol: str
    selection_status: str
    candidate_rank: int | None
    incumbent_diagnostics: tuple[tuple[str, str | None], ...]
    validated_alpha_contributions: tuple[tuple[str, str | None], ...]
    conditional_context: tuple[tuple[str, str | None], ...]
    signal_reference: RuntimeArtifactReference | None
    signal_state: str | None
    signal_score: str | None
    path_forecast: DailyAlphaPathForecastProjection | None
    conditional_forecast: DailyAlphaConditionalForecastProjection
    strategy_diagnostic_reference: RuntimeArtifactReference
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("selection_status", self.selection_status)
        if self.candidate_rank is not None and self.candidate_rank < 1:
            raise ValueError("daily Alpha Candidate rank must be positive")
        for label, values in (
            ("incumbent_diagnostics", self.incumbent_diagnostics),
            ("validated_alpha_contributions", self.validated_alpha_contributions),
            ("conditional_context", self.conditional_context),
        ):
            _ordered_pairs(f"daily Alpha {label}", values)
        _ordered_text("symbol reason_codes", self.reason_codes, required=True)
        if (self.signal_reference is None) != (self.signal_state is None):
            raise ValueError("Signal reference/state must be paired")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "selection_status": self.selection_status,
            "candidate_rank": self.candidate_rank,
            "incumbent_diagnostics": _pairs_payload(self.incumbent_diagnostics),
            "validated_alpha_contributions": _pairs_payload(
                self.validated_alpha_contributions
            ),
            "conditional_context": _pairs_payload(self.conditional_context),
            "signal_reference": _optional_runtime_reference(self.signal_reference),
            "signal_state": self.signal_state,
            "signal_score": self.signal_score,
            "path_forecast": (
                None if self.path_forecast is None else self.path_forecast.to_canonical_dict()
            ),
            "conditional_forecast": self.conditional_forecast.to_canonical_dict(),
            "strategy_diagnostic_reference": self.strategy_diagnostic_reference.to_canonical_dict(),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaSymbolProjection:
        _fields(
            payload,
            {
                "symbol",
                "selection_status",
                "candidate_rank",
                "incumbent_diagnostics",
                "validated_alpha_contributions",
                "conditional_context",
                "signal_reference",
                "signal_state",
                "signal_score",
                "path_forecast",
                "conditional_forecast",
                "strategy_diagnostic_reference",
                "reason_codes",
            },
            "Daily Alpha symbol projection",
        )
        rank = payload["candidate_rank"]
        return cls(
            symbol=str(payload["symbol"]),
            selection_status=str(payload["selection_status"]),
            candidate_rank=None if rank is None else int(rank),
            incumbent_diagnostics=_pairs(payload["incumbent_diagnostics"]),
            validated_alpha_contributions=_pairs(
                payload["validated_alpha_contributions"]
            ),
            conditional_context=_pairs(payload["conditional_context"]),
            signal_reference=_runtime_reference(payload["signal_reference"]),
            signal_state=_optional_text(payload["signal_state"]),
            signal_score=_optional_text(payload["signal_score"]),
            path_forecast=(
                None
                if payload["path_forecast"] is None
                else DailyAlphaPathForecastProjection.from_canonical_dict(
                    _mapping(payload["path_forecast"])
                )
            ),
            conditional_forecast=DailyAlphaConditionalForecastProjection.from_canonical_dict(
                _mapping(payload["conditional_forecast"])
            ),
            strategy_diagnostic_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["strategy_diagnostic_reference"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DailyAlphaLegacySymbolProjection:
    """Exact v1 decoder/encoder; never used for newly created snapshots."""

    symbol: str
    selection_status: str
    candidate_rank: int | None
    factor_score: str | None
    factor_values: tuple[tuple[str, str | None], ...]
    factor_contributions: tuple[tuple[str, str | None], ...]
    context: tuple[tuple[str, str | None], ...]
    signal_reference: RuntimeArtifactReference | None
    signal_state: str | None
    signal_score: str | None
    forecast_reference: RuntimeArtifactReference | None
    forecast_expected_return: str | None
    forecast_uncertainty: str | None
    calibration_status: str
    strategy_diagnostic_reference: RuntimeArtifactReference
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("selection_status", self.selection_status)
        require_text("calibration_status", self.calibration_status)
        if self.candidate_rank is not None and self.candidate_rank < 1:
            raise ValueError("daily Alpha Candidate rank must be positive")
        for label, values in (
            ("factor_values", self.factor_values),
            ("factor_contributions", self.factor_contributions),
            ("context", self.context),
        ):
            _ordered_pairs(f"daily Alpha v1 {label}", values)
        _ordered_text("symbol reason_codes", self.reason_codes, required=True)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "selection_status": self.selection_status,
            "candidate_rank": self.candidate_rank,
            "factor_score": self.factor_score,
            "factor_values": _pairs_payload(self.factor_values),
            "factor_contributions": _pairs_payload(self.factor_contributions),
            "context": _pairs_payload(self.context),
            "signal_reference": _optional_runtime_reference(self.signal_reference),
            "signal_state": self.signal_state,
            "signal_score": self.signal_score,
            "forecast_reference": _optional_runtime_reference(self.forecast_reference),
            "forecast_expected_return": self.forecast_expected_return,
            "forecast_uncertainty": self.forecast_uncertainty,
            "calibration_status": self.calibration_status,
            "strategy_diagnostic_reference": self.strategy_diagnostic_reference.to_canonical_dict(),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaLegacySymbolProjection:
        _fields(
            payload,
            {
                "symbol",
                "selection_status",
                "candidate_rank",
                "factor_score",
                "factor_values",
                "factor_contributions",
                "context",
                "signal_reference",
                "signal_state",
                "signal_score",
                "forecast_reference",
                "forecast_expected_return",
                "forecast_uncertainty",
                "calibration_status",
                "strategy_diagnostic_reference",
                "reason_codes",
            },
            "Daily Alpha v1 symbol projection",
        )
        rank = payload["candidate_rank"]
        return cls(
            symbol=str(payload["symbol"]),
            selection_status=str(payload["selection_status"]),
            candidate_rank=None if rank is None else int(rank),
            factor_score=_optional_text(payload["factor_score"]),
            factor_values=_pairs(payload["factor_values"]),
            factor_contributions=_pairs(payload["factor_contributions"]),
            context=_pairs(payload["context"]),
            signal_reference=_runtime_reference(payload["signal_reference"]),
            signal_state=_optional_text(payload["signal_state"]),
            signal_score=_optional_text(payload["signal_score"]),
            forecast_reference=_runtime_reference(payload["forecast_reference"]),
            forecast_expected_return=_optional_text(
                payload["forecast_expected_return"]
            ),
            forecast_uncertainty=_optional_text(payload["forecast_uncertainty"]),
            calibration_status=str(payload["calibration_status"]),
            strategy_diagnostic_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["strategy_diagnostic_reference"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class DailyAlphaPredictionSnapshot:
    snapshot_id: ArtifactId
    snapshot_hash: str
    run_reference: RuntimeArtifactReference
    tick_reference: RuntimeArtifactReference
    code_reference: RuntimeArtifactReference
    configuration_references: tuple[RuntimeArtifactReference, ...]
    provider_evidence_reference: RuntimeArtifactReference
    dataset_reference: RuntimeArtifactReference
    universe_reference: RuntimeArtifactReference
    feature_references: tuple[RuntimeArtifactReference, ...]
    context_references: tuple[RuntimeArtifactReference, ...]
    candidate_reference: RuntimeArtifactReference
    signal_reference: RuntimeArtifactReference | None
    forecast_references: tuple[RuntimeArtifactReference, ...]
    strategy_diagnostic_reference: RuntimeArtifactReference
    evidence_gate: DailyAlphaEvidenceGate
    trading_date: date
    target_session_date: date | None
    target_calendar_reference: RuntimeArtifactReference | None
    decision_time: datetime
    available_at: datetime
    symbols: tuple[
        DailyAlphaSymbolProjection | DailyAlphaLegacySymbolProjection, ...
    ]
    reason_codes: tuple[str, ...]
    schema_version: str = DAILY_ALPHA_PREDICTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {
            DAILY_ALPHA_PREDICTION_SCHEMA_V1,
            DAILY_ALPHA_PREDICTION_SCHEMA_V2,
            DAILY_ALPHA_PREDICTION_SCHEMA,
        }:
            raise ValueError("unsupported Daily Alpha prediction schema")
        require_sha256("snapshot_hash", self.snapshot_hash)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("available_at", self.available_at)
        if self.available_at < self.decision_time:
            raise ValueError("Daily Alpha snapshot cannot predate DecisionTime")
        if self.schema_version == DAILY_ALPHA_PREDICTION_SCHEMA:
            if (
                self.target_session_date is None
                or self.target_session_date <= self.trading_date
                or self.target_calendar_reference is None
                or self.target_calendar_reference.reference_kind
                != "TRADING_CALENDAR"
            ):
                raise ValueError(
                    "Daily Alpha v3 requires one future canonical target session"
                )
        elif (
            self.target_session_date is not None
            or self.target_calendar_reference is not None
        ):
            raise ValueError("legacy Daily Alpha snapshots cannot gain target lineage")
        for label, references in (
            ("configuration", self.configuration_references),
            ("feature", self.feature_references),
            ("context", self.context_references),
            ("forecast", self.forecast_references),
        ):
            _ordered_runtime_references(
                label,
                references,
                # A fail-closed DATA_INSUFFICIENT or MODEL_NOT_QUALIFIED tick
                # has no Forecast owner.  The immutable snapshot must still
                # expose that absence instead of fabricating a projection.
                required=label != "forecast",
            )
        symbol_keys = tuple(item.symbol for item in self.symbols)
        if symbol_keys != tuple(sorted(set(symbol_keys))):
            raise ValueError("Daily Alpha symbols must be unique and sorted")
        expected_symbol_type = (
            DailyAlphaLegacySymbolProjection
            if self.schema_version == DAILY_ALPHA_PREDICTION_SCHEMA_V1
            else DailyAlphaSymbolProjection
        )
        if any(not isinstance(item, expected_symbol_type) for item in self.symbols):
            raise ValueError("Daily Alpha symbol projection schema drifted")
        _ordered_text("snapshot reason_codes", self.reason_codes, required=True)
        if (
            self.evidence_gate.status
            is DailyAlphaActivationStatus.VALIDATED_CHALLENGER_INACTIVE
            and EVIDENCE_DEPENDENCY_NOT_SATISFIED not in self.reason_codes
        ):
            raise ValueError("inactive Daily Alpha snapshot must expose Evidence gate")
        self.verify_identity()

    @classmethod
    def create(cls, **values: Any) -> DailyAlphaPredictionSnapshot:
        normalized = dict(values)
        normalized["configuration_references"] = _sort_runtime_references(
            values["configuration_references"]
        )
        normalized["feature_references"] = _sort_runtime_references(
            values["feature_references"]
        )
        normalized["context_references"] = _sort_runtime_references(
            values["context_references"]
        )
        normalized["forecast_references"] = _sort_runtime_references(
            values["forecast_references"]
        )
        normalized["symbols"] = tuple(
            sorted(values["symbols"], key=lambda item: item.symbol)
        )
        normalized["reason_codes"] = tuple(
            sorted(
                {
                    "FREE_DATA_RESEARCH_ONLY",
                    "FORMAL_OOS_FALSE",
                    "NO_TRADING_AUTHORITY",
                    "PRODUCTION_QUALIFIED_FALSE",
                    *values["reason_codes"],
                    *values["evidence_gate"].reason_codes,
                }
            )
        )
        normalized.setdefault("schema_version", DAILY_ALPHA_PREDICTION_SCHEMA)
        normalized.setdefault("target_session_date", None)
        normalized.setdefault("target_calendar_reference", None)
        digest = canonical_hash(_snapshot_payload(**normalized))
        return cls(
            snapshot_id=ArtifactId(f"daily-alpha-prediction:{digest[7:]}"),
            snapshot_hash=digest,
            **normalized,
        )

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            DAILY_ALPHA_PREDICTION_KIND, self.snapshot_id, self.snapshot_hash
        )

    def verify_identity(self) -> None:
        if canonical_hash(self.identity_payload()) != self.snapshot_hash:
            raise ValueError("Daily Alpha snapshot hash mismatch")
        if self.snapshot_id != ArtifactId(
            f"daily-alpha-prediction:{self.snapshot_hash[7:]}"
        ):
            raise ValueError("Daily Alpha snapshot identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _snapshot_payload(
            run_reference=self.run_reference,
            tick_reference=self.tick_reference,
            code_reference=self.code_reference,
            configuration_references=self.configuration_references,
            provider_evidence_reference=self.provider_evidence_reference,
            dataset_reference=self.dataset_reference,
            universe_reference=self.universe_reference,
            feature_references=self.feature_references,
            context_references=self.context_references,
            candidate_reference=self.candidate_reference,
            signal_reference=self.signal_reference,
            forecast_references=self.forecast_references,
            strategy_diagnostic_reference=self.strategy_diagnostic_reference,
            evidence_gate=self.evidence_gate,
            trading_date=self.trading_date,
            target_session_date=self.target_session_date,
            target_calendar_reference=self.target_calendar_reference,
            decision_time=self.decision_time,
            available_at=self.available_at,
            symbols=self.symbols,
            reason_codes=self.reason_codes,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id),
            "snapshot_hash": self.snapshot_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> DailyAlphaPredictionSnapshot:
        schema_version = str(payload.get("schema_version"))
        expected = {
            "snapshot_id",
            "snapshot_hash",
            "schema_version",
            "run_reference",
            "tick_reference",
            "code_reference",
            "configuration_references",
            "provider_evidence_reference",
            "dataset_reference",
            "universe_reference",
            "feature_references",
            "context_references",
            "candidate_reference",
            "signal_reference",
            "forecast_references",
            "strategy_diagnostic_reference",
            "evidence_gate",
            "trading_date",
            "decision_time",
            "available_at",
            "symbols",
            "reason_codes",
        }
        if schema_version == DAILY_ALPHA_PREDICTION_SCHEMA:
            expected.update({"target_session_date", "target_calendar_reference"})
        _fields(payload, expected, "Daily Alpha prediction snapshot")
        return cls(
            snapshot_id=ArtifactId(str(payload["snapshot_id"])),
            snapshot_hash=str(payload["snapshot_hash"]),
            run_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["run_reference"])
            ),
            tick_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["tick_reference"])
            ),
            code_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["code_reference"])
            ),
            configuration_references=_runtime_references(
                payload["configuration_references"]
            ),
            provider_evidence_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["provider_evidence_reference"])
            ),
            dataset_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["dataset_reference"])
            ),
            universe_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["universe_reference"])
            ),
            feature_references=_runtime_references(payload["feature_references"]),
            context_references=_runtime_references(payload["context_references"]),
            candidate_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["candidate_reference"])
            ),
            signal_reference=_runtime_reference(payload["signal_reference"]),
            forecast_references=_runtime_references(payload["forecast_references"]),
            strategy_diagnostic_reference=RuntimeArtifactReference.from_canonical_dict(
                _mapping(payload["strategy_diagnostic_reference"])
            ),
            evidence_gate=DailyAlphaEvidenceGate.from_canonical_dict(
                _mapping(payload["evidence_gate"])
            ),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            target_session_date=(
                None
                if schema_version != DAILY_ALPHA_PREDICTION_SCHEMA
                else date.fromisoformat(str(payload["target_session_date"]))
            ),
            target_calendar_reference=(
                None
                if schema_version != DAILY_ALPHA_PREDICTION_SCHEMA
                else RuntimeArtifactReference.from_canonical_dict(
                    _mapping(payload["target_calendar_reference"])
                )
            ),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            symbols=_symbol_projections(
                payload["symbols"], schema_version=str(payload["schema_version"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
            schema_version=schema_version,
        )


class DailyAlphaOwnerResolver(Protocol):
    def verify_snapshot_sources(self, snapshot: DailyAlphaPredictionSnapshot) -> None: ...


class DailyAlphaPredictionAuthority(Protocol):
    def put(
        self,
        snapshot: DailyAlphaPredictionSnapshot,
        *,
        universe: OperationalUniverseArtifact | None = None,
    ) -> DailyAlphaPredictionSnapshot: ...


def _snapshot_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": values["schema_version"],
        "run_reference": values["run_reference"].to_canonical_dict(),
        "tick_reference": values["tick_reference"].to_canonical_dict(),
        "code_reference": values["code_reference"].to_canonical_dict(),
        "configuration_references": [
            item.to_canonical_dict() for item in values["configuration_references"]
        ],
        "provider_evidence_reference": values[
            "provider_evidence_reference"
        ].to_canonical_dict(),
        "dataset_reference": values["dataset_reference"].to_canonical_dict(),
        "universe_reference": values["universe_reference"].to_canonical_dict(),
        "feature_references": [
            item.to_canonical_dict() for item in values["feature_references"]
        ],
        "context_references": [
            item.to_canonical_dict() for item in values["context_references"]
        ],
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "signal_reference": _optional_runtime_reference(values["signal_reference"]),
        "forecast_references": [
            item.to_canonical_dict() for item in values["forecast_references"]
        ],
        "strategy_diagnostic_reference": values[
            "strategy_diagnostic_reference"
        ].to_canonical_dict(),
        "evidence_gate": values["evidence_gate"].to_canonical_dict(),
        "trading_date": values["trading_date"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "available_at": canonical_datetime(values["available_at"]),
        "symbols": [item.to_canonical_dict() for item in values["symbols"]],
        "reason_codes": list(values["reason_codes"]),
    }
    if values["schema_version"] == DAILY_ALPHA_PREDICTION_SCHEMA:
        payload["target_session_date"] = values["target_session_date"].isoformat()
        payload["target_calendar_reference"] = values[
            "target_calendar_reference"
        ].to_canonical_dict()
    return payload


def _sort_runtime_references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _ordered_runtime_references(
    label: str,
    references: tuple[RuntimeArtifactReference, ...],
    *,
    required: bool,
) -> None:
    if required and not references:
        raise ValueError(f"Daily Alpha {label} references are required")
    if references != _sort_runtime_references(references):
        raise ValueError(f"Daily Alpha {label} references must be unique and sorted")


def _ordered_text(label: str, values: tuple[str, ...], *, required: bool) -> None:
    if required and not values:
        raise ValueError(f"{label} are required")
    if values != tuple(sorted(set(values))) or any(not item.strip() for item in values):
        raise ValueError(f"{label} must be unique, non-empty, and sorted")


def _ordered_pairs(
    label: str, values: tuple[tuple[str, str | None], ...]
) -> None:
    keys = tuple(item[0] for item in values)
    if keys != tuple(sorted(set(keys))) or any(not key.strip() for key in keys):
        raise ValueError(f"{label} keys must be unique and sorted")


def _symbol_projections(
    value: object,
    *,
    schema_version: str,
) -> tuple[DailyAlphaSymbolProjection | DailyAlphaLegacySymbolProjection, ...]:
    if schema_version == DAILY_ALPHA_PREDICTION_SCHEMA_V1:
        return tuple(
            DailyAlphaLegacySymbolProjection.from_canonical_dict(_mapping(item))
            for item in _sequence(value)
        )
    if schema_version in {
        DAILY_ALPHA_PREDICTION_SCHEMA_V2,
        DAILY_ALPHA_PREDICTION_SCHEMA,
    }:
        return tuple(
            DailyAlphaSymbolProjection.from_canonical_dict(_mapping(item))
            for item in _sequence(value)
        )
    raise ValueError("unsupported Daily Alpha prediction schema")


def _optional_validation_reference(
    value: ValidationArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _validation_reference(value: object) -> ValidationArtifactReference | None:
    if value is None:
        return None
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _optional_runtime_reference(
    value: RuntimeArtifactReference | None,
) -> dict[str, str] | None:
    return None if value is None else value.to_canonical_dict()


def _runtime_reference(value: object) -> RuntimeArtifactReference | None:
    if value is None:
        return None
    return RuntimeArtifactReference.from_canonical_dict(_mapping(value))


def _runtime_references(value: object) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        RuntimeArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(value)
    )


def _pairs_payload(values: tuple[tuple[str, str | None], ...]) -> list[dict[str, str | None]]:
    return [{"name": key, "value": value} for key, value in values]


def _pairs(value: object) -> tuple[tuple[str, str | None], ...]:
    pairs = []
    for item in _sequence(value):
        payload = _mapping(item)
        _fields(payload, {"name", "value"}, "Daily Alpha named value")
        pairs.append((str(payload["name"]), _optional_text(payload["value"])))
    return tuple(pairs)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Daily Alpha value must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Daily Alpha value must be an array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    values = _sequence(value)
    if any(not isinstance(item, str) for item in values):
        raise ValueError("Daily Alpha value must be a string array")
    return tuple(str(item) for item in values)


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


__all__ = [
    "DAILY_ALPHA_PREDICTION_KIND",
    "DAILY_ALPHA_PREDICTION_SCHEMA",
    "DAILY_ALPHA_PREDICTION_SCHEMA_V1",
    "DailyAlphaActivationStatus",
    "DailyAlphaConditionalForecastProjection",
    "DailyAlphaEvidenceGate",
    "DailyAlphaLegacySymbolProjection",
    "DailyAlphaOwnerResolver",
    "DailyAlphaPathForecastProjection",
    "DailyAlphaPredictionAuthority",
    "DailyAlphaPredictionSnapshot",
    "DailyAlphaSymbolProjection",
    "EVIDENCE_DEPENDENCY_NOT_SATISFIED",
    "assess_daily_alpha_evidence_gate",
    "daily_alpha_admission_evidence_references",
]
