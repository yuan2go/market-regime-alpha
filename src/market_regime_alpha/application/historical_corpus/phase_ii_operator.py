"""Single resumable operator surface for Historical Alpha Research Phase II.

This adapter owns no Runtime, scheduler, research kernel, or Evidence store. It
parses one immutable command, reloads typed PostgreSQL owners, and delegates to
``HistoricalPhaseIIResearchService``. Replaying the same command is idempotent
because the existing Historical Evidence owner is content addressed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    MovingBlockInferenceProtocol,
)
from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextKind,
    ContextResearchRole,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalEvidenceMetric,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    FrozenAlphaHypothesis,
    ValidationDimension,
    ValidationScope,
)
from market_regime_alpha.application.historical_corpus.phase_ii_service import (
    HistoricalPhaseIIResearchService,
    PhaseIIEvidenceWrite,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_temporal_validation_window import (
    PostgresTemporalValidationWindowAuthority,
)
from market_regime_alpha.application.historical_corpus.raw_normalization_correctness import (
    PhysicalAcquisitionProvenance,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.candidates.policy import (
    CandidateComparisonProtocol,
    CandidatePolicyDefinition,
    CandidatePolicyRole,
    research_panel_dataset_reference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.evidence.canonical import require_sha256
from market_regime_alpha.market_data.contracts import parse_utc_second
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


PHASE_II_OPERATOR_SCHEMA = "historical-phase-ii-operator-command/v1"
CORRECTNESS_PLACEBO_SEED = 20260813
CORRECTNESS_INFERENCE_ITERATIONS = 2_000
CORRECTNESS_INFERENCE_BLOCK_LENGTHS = (1, 5, 10)
CORRECTNESS_INFERENCE_CONFIDENCE = Decimal("0.95")


class PhaseIIOperation(str, Enum):
    CORRECTNESS = "CORRECTNESS"
    EXTERNAL_VALIDATION = "EXTERNAL_VALIDATION"
    CONTEXT = "CONTEXT"
    CANDIDATE = "CANDIDATE"


@dataclass(frozen=True, slots=True)
class HistoricalPhaseIIResearchOperator:
    """Typed adapter over the existing Phase II application service."""

    service: HistoricalPhaseIIResearchService
    calendars: PostgresPITTradingCalendarSnapshotRepository
    temporal_windows: PostgresTemporalValidationWindowAuthority

    def execute(self, payload: Mapping[str, Any]) -> HistoricalResearchEvidence:
        _exact_fields(
            payload,
            required={"schema_version", "operation", "evidence", "parameters"},
            label="Phase II operator command",
        )
        if payload["schema_version"] != PHASE_II_OPERATOR_SCHEMA:
            raise ValueError("unsupported Phase II operator command schema")
        operation = PhaseIIOperation(str(payload["operation"]))
        evidence = _mapping(payload["evidence"], "evidence")
        parameters = _mapping(payload["parameters"], "parameters")
        if operation is PhaseIIOperation.CORRECTNESS:
            return self._correctness(evidence, parameters)
        if operation is PhaseIIOperation.EXTERNAL_VALIDATION:
            return self._external(evidence, parameters)
        if operation is PhaseIIOperation.CONTEXT:
            return self._context(evidence, parameters)
        return self._candidate(evidence, parameters)

    def _correctness(
        self,
        evidence: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> HistoricalResearchEvidence:
        _exact_fields(
            parameters,
            required={
                "experiment_reference",
                "calendar_reference",
                "physical_packages",
                "physical_provenance",
                "target_id",
            },
            label="Correctness parameters",
        )
        experiment_reference = _reference(parameters["experiment_reference"])
        calendar_reference = _reference(parameters["calendar_reference"])
        if calendar_reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Correctness requires a Trading Calendar owner")
        calendar = self.calendars.get(calendar_reference.artifact_id)
        if calendar.content_hash != calendar_reference.content_hash:
            raise ValueError("Correctness Trading Calendar owner drifted")
        physical_packages = _physical_packages(parameters["physical_packages"])
        proof = self.service.evaluate_correctness_campaign(
            run_id=ArtifactId(str(evidence["run_id"])),
            trading_calendar=calendar,
            physical_package_paths=physical_packages,
            physical_provenance=PhysicalAcquisitionProvenance(
                str(parameters["physical_provenance"])
            ),
            target_id=_nonempty_text(parameters["target_id"], "target_id"),
            placebo_seed=CORRECTNESS_PLACEBO_SEED,
            inference_protocol=MovingBlockInferenceProtocol.create(
                iterations=CORRECTNESS_INFERENCE_ITERATIONS,
                block_lengths=CORRECTNESS_INFERENCE_BLOCK_LENGTHS,
                confidence_level=CORRECTNESS_INFERENCE_CONFIDENCE,
                seed=CORRECTNESS_PLACEBO_SEED,
            ),
        )
        write = _evidence_write(
            evidence,
            evidence_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
            experiment_reference=experiment_reference,
            source_references=(calendar_reference, *physical_packages),
        )
        return self.service.persist_correctness_proof(
            write,
            proof,
            run_id=write.run_id,
            trading_calendar=calendar,
            physical_package_paths=physical_packages,
        )

    def _external(
        self,
        evidence: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> HistoricalResearchEvidence:
        _exact_fields(
            parameters,
            required={
                "hypothesis",
                "correctness_evidence_id",
                "discovery_scope",
                "validation_scope",
                "temporal_window_reference",
                "validation_panel_references",
                "dimension",
                "expected_population",
                "random_seed",
                "expected_experiment_reference",
            },
            label="External Validation parameters",
        )
        hypothesis = _hypothesis(parameters["hypothesis"])
        dimension = ValidationDimension(str(parameters["dimension"]))
        raw_window = parameters["temporal_window_reference"]
        temporal_window = (
            None
            if raw_window is None
            else self.temporal_windows.get(_reference(raw_window))
        )
        panels = _references(
            parameters["validation_panel_references"],
            label="validation_panel_references",
        )
        experiment = self.service.create_external_experiment(
            hypothesis=hypothesis,
            correctness_evidence_id=ArtifactId(
                str(parameters["correctness_evidence_id"])
            ),
            discovery_scope=_scope(parameters["discovery_scope"]),
            validation_scope=_scope(parameters["validation_scope"]),
            temporal_window=temporal_window,
            validation_panel_references=panels,
            dimension=dimension,
            expected_population=_positive_int(
                parameters["expected_population"], "expected_population"
            ),
            random_seed=_integer(parameters["random_seed"], "random_seed"),
        )
        if experiment.reference != _reference(
            parameters["expected_experiment_reference"]
        ):
            raise ValueError("External Experiment Definition owner drifted")
        evaluation = self.service.evaluate_external_experiment(experiment)
        write = _evidence_write(
            evidence,
            evidence_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
            experiment_reference=experiment.reference,
            source_references=panels,
        )
        return self.service.persist_external_evaluation(
            write,
            experiment,
            evaluation,
        )

    def _context(
        self,
        evidence: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> HistoricalResearchEvidence:
        _exact_fields(
            parameters,
            required={
                "external_evidence_id",
                "context_id",
                "kind",
                "role",
                "public_observable_proxy",
                "research_panel_references",
                "top_k",
                "expected_population",
                "effect_threshold",
            },
            label="Context parameters",
        )
        external = self.service.load_evidence(
            ArtifactId(str(parameters["external_evidence_id"])),
            expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        )
        panels = _references(
            parameters["research_panel_references"],
            label="research_panel_references",
        )
        definition = self.service.context_definition(
            context_id=_nonempty_text(parameters["context_id"], "context_id"),
            kind=ContextKind(str(parameters["kind"])),
            role=ContextResearchRole(str(parameters["role"])),
            public_observable_proxy=_boolean(
                parameters["public_observable_proxy"],
                "public_observable_proxy",
            ),
            research_panel_references=panels,
            top_k=_positive_int(parameters["top_k"], "top_k"),
            expected_population=_positive_int(
                parameters["expected_population"], "expected_population"
            ),
            effect_threshold=_decimal(
                parameters["effect_threshold"], "effect_threshold"
            ),
            external_evidence_id=external.evidence_id,
        )
        evaluation = self.service.evaluate_context_definition(definition)
        write = _evidence_write(
            evidence,
            evidence_kind=HistoricalEvidenceKind.CONTEXT_CONDITIONAL,
            experiment_reference=external.experiment_reference,
            source_references=(external.reference, *panels),
        )
        return self.service.persist_context_evaluation(write, definition, evaluation)

    def _candidate(
        self,
        evidence: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> HistoricalResearchEvidence:
        _exact_fields(
            parameters,
            required={
                "external_evidence_id",
                "context_adjustments",
                "validated_factors",
                "research_panel_references",
                "incumbent_policy",
                "challenger_policy",
                "target_reference",
                "cost_assumption",
                "activation_status",
            },
            label="Candidate parameters",
        )
        external = self.service.load_evidence(
            ArtifactId(str(parameters["external_evidence_id"])),
            expected_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        )
        panels = _references(
            parameters["research_panel_references"],
            label="research_panel_references",
        )
        dataset = research_panel_dataset_reference(panels)
        factors = tuple(
            self.service.validated_factor(
                factor_id=_nonempty_text(item["factor_id"], "factor_id"),
                direction=_nonempty_text(item["direction"], "direction"),
                weight=_decimal(item["weight"], "weight"),
                external_evidence_id=external.evidence_id,
            )
            for item in _validated_factor_inputs(parameters["validated_factors"])
        )
        contexts = tuple(
            self.service.context_adjustment(
                context_id=_nonempty_text(item["context_id"], "context_id"),
                weight=_decimal(item["weight"], "weight"),
                mode=_nonempty_text(item["mode"], "mode"),
                context_evidence_id=ArtifactId(str(item["context_evidence_id"])),
            )
            for item in _context_adjustment_inputs(
                parameters["context_adjustments"]
            )
        )
        incumbent = _candidate_policy(
            parameters["incumbent_policy"],
            role=CandidatePolicyRole.INCUMBENT,
            dataset=dataset,
            factors=(),
            contexts=(),
        )
        challenger = _candidate_policy(
            parameters["challenger_policy"],
            role=CandidatePolicyRole.CHALLENGER,
            dataset=dataset,
            factors=factors,
            contexts=contexts,
        )
        protocol = CandidateComparisonProtocol.create(
            dataset_reference=dataset,
            target_reference=_reference(parameters["target_reference"]),
            cost_assumption=_decimal(parameters["cost_assumption"], "cost_assumption"),
        )
        comparison = self.service.compare_candidate_policies(
            incumbent,
            challenger,
            protocol=protocol,
            panel_references=panels,
        )
        write = _evidence_write(
            evidence,
            evidence_kind=HistoricalEvidenceKind.CANDIDATE_POLICY,
            experiment_reference=external.experiment_reference,
            source_references=(external.reference, *panels),
        )
        return self.service.persist_candidate_admission(
            write,
            comparison=comparison,
            challenger_policy=challenger,
            activation_status=_nonempty_text(
                parameters["activation_status"], "activation_status"
            ),
        )


def build_postgres_phase_ii_operator(
    factory: PostgresConnectionFactory,
    *,
    artifact_root: Path,
) -> HistoricalPhaseIIResearchOperator:
    """Compose the operator from existing owners without applying migrations."""

    validation = PostgresResearchValidationRepository(factory)
    service = HistoricalPhaseIIResearchService(
        PostgresHistoricalEvidenceRepository(factory),
        components=PostgresHistoricalMaterializationRepository(factory),
        corpus=PostgresHistoricalCorpusRepository(
            factory,
            artifact_root=artifact_root,
        ),
        validation=validation,
    )
    return HistoricalPhaseIIResearchOperator(
        service=service,
        calendars=PostgresPITTradingCalendarSnapshotRepository(factory),
        temporal_windows=PostgresTemporalValidationWindowAuthority(validation),
    )


def _evidence_write(
    payload: Mapping[str, Any],
    *,
    evidence_kind: HistoricalEvidenceKind,
    experiment_reference: ValidationArtifactReference,
    source_references: tuple[ValidationArtifactReference, ...],
) -> PhaseIIEvidenceWrite:
    _exact_fields(
        payload,
        required={
            "run_id",
            "command_hash",
            "research_question",
            "classification",
            "rationale",
            "created_at",
            "statements",
        },
        optional={"metrics", "limitations"},
        label="Evidence metadata",
    )
    command_hash = str(payload["command_hash"])
    require_sha256("command_hash", command_hash)
    return PhaseIIEvidenceWrite(
        run_id=ArtifactId(str(payload["run_id"])),
        command_hash=command_hash,
        experiment_reference=experiment_reference,
        evidence_kind=evidence_kind,
        research_question=_nonempty_text(
            payload["research_question"], "research_question"
        ),
        classification=ResearchFinding(str(payload["classification"])),
        rationale=_nonempty_text(payload["rationale"], "rationale"),
        source_references=_ordered_references(source_references),
        metrics=tuple(
            HistoricalEvidenceMetric.from_canonical_dict(item)
            for item in _object_array(payload.get("metrics", []), "metrics")
        ),
        payload={},
        created_at=parse_utc_second("created_at", payload["created_at"]),
        statements=tuple(
            ResearchStatement.from_canonical_dict(item)
            for item in _object_array(payload["statements"], "statements")
        ),
        limitations=tuple(
            sorted(
                set(
                    _string_array(payload.get("limitations", []), "limitations")
                )
            )
        ),
    )


def _hypothesis(value: object) -> FrozenAlphaHypothesis:
    payload = _mapping(value, "hypothesis")
    _exact_fields(
        payload,
        required={
            "hypothesis_id",
            "hypothesis_hash",
            "schema_version",
            "factor_directions",
            "candidate_scoring",
            "decision_time_policy",
            "target_reference",
            "feature_reference",
            "feature_version",
            "cost_policy_reference",
            "economics_policy_reference",
            "execution_entry_kind",
            "discovery_evidence_reference",
            "discovery_variant_id",
            "discovery_rank_ic",
            "top_k",
            "cost_assumption",
            "minimum_effect_retention",
            "minimum_coverage",
            "minimum_top_k_net",
            "bootstrap_iterations",
            "block_lengths",
        },
        label="Frozen Alpha Hypothesis",
    )
    factor_values = _array(payload["factor_directions"], "factor_directions")
    factors: list[tuple[str, str]] = []
    for item in factor_values:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("factor_directions must contain two-item arrays")
        factors.append((str(item[0]), str(item[1])))
    hypothesis = FrozenAlphaHypothesis.create(
        factor_directions=tuple(factors),
        candidate_scoring=str(payload["candidate_scoring"]),
        decision_time_policy=str(payload["decision_time_policy"]),
        target_reference=_reference(payload["target_reference"]),
        top_k=_positive_int(payload["top_k"], "top_k"),
        cost_assumption=_decimal(payload["cost_assumption"], "cost_assumption"),
        minimum_effect_retention=_decimal(
            payload["minimum_effect_retention"], "minimum_effect_retention"
        ),
        minimum_coverage=_decimal(payload["minimum_coverage"], "minimum_coverage"),
        feature_reference=_reference(payload["feature_reference"]),
        feature_version=str(payload["feature_version"]),
        cost_policy_reference=_reference(payload["cost_policy_reference"]),
        economics_policy_reference=_reference(
            payload["economics_policy_reference"]
        ),
        execution_entry_kind=str(payload["execution_entry_kind"]),
        discovery_evidence_reference=_reference(
            payload["discovery_evidence_reference"]
        ),
        discovery_variant_id=str(payload["discovery_variant_id"]),
        discovery_rank_ic=_decimal(payload["discovery_rank_ic"], "discovery_rank_ic"),
        minimum_top_k_net=_decimal(payload["minimum_top_k_net"], "minimum_top_k_net"),
        bootstrap_iterations=_positive_int(
            payload["bootstrap_iterations"], "bootstrap_iterations"
        ),
        block_lengths=tuple(
            _positive_int(item, "block_length")
            for item in _array(payload["block_lengths"], "block_lengths")
        ),
    )
    if (
        hypothesis.hypothesis_id != ArtifactId(str(payload["hypothesis_id"]))
        or hypothesis.hypothesis_hash != str(payload["hypothesis_hash"])
        or hypothesis.schema_version != str(payload["schema_version"])
    ):
        raise ValueError("Frozen Alpha Hypothesis identity drifted")
    return hypothesis


def _scope(value: object) -> ValidationScope:
    payload = _mapping(value, "validation scope")
    _exact_fields(
        payload,
        required={
            "temporal_partition",
            "first_session",
            "last_session",
            "universe_reference",
            "provider_reference",
        },
        label="Validation scope",
    )
    return ValidationScope(
        temporal_partition=str(payload["temporal_partition"]),
        first_session=date.fromisoformat(str(payload["first_session"])),
        last_session=date.fromisoformat(str(payload["last_session"])),
        universe_reference=_reference(payload["universe_reference"]),
        provider_reference=_reference(payload["provider_reference"]),
    )


def _candidate_policy(
    value: object,
    *,
    role: CandidatePolicyRole,
    dataset: ValidationArtifactReference,
    factors: tuple[Any, ...],
    contexts: tuple[Any, ...],
) -> CandidatePolicyDefinition:
    payload = _mapping(value, f"{role.value} policy")
    _exact_fields(
        payload,
        required={"policy_version", "top_k", "minimum_liquidity"},
        label=f"{role.value} policy",
    )
    return CandidatePolicyDefinition.create(
        role=role,
        policy_version=_nonempty_text(payload["policy_version"], "policy_version"),
        validated_factors=factors,
        context_adjustments=contexts,
        top_k=_positive_int(payload["top_k"], "top_k"),
        minimum_liquidity=_decimal(
            payload["minimum_liquidity"], "minimum_liquidity"
        ),
        dataset_reference=dataset,
    )


def _physical_packages(
    value: object,
) -> Mapping[ValidationArtifactReference, Path]:
    result: dict[ValidationArtifactReference, Path] = {}
    for item in _object_array(value, "physical_packages"):
        _exact_fields(
            item,
            required={"owner_reference", "path"},
            label="physical package",
        )
        reference = _reference(item["owner_reference"])
        if reference in result:
            raise ValueError("physical package owner references must be unique")
        result[reference] = Path(str(item["path"])).expanduser().resolve()
    if not result:
        raise ValueError("Correctness requires physical packages")
    return result


def _validated_factor_inputs(
    value: object,
) -> tuple[Mapping[str, Any], ...]:
    values = _object_array(value, "validated_factors")
    for item in values:
        _exact_fields(
            item,
            required={"factor_id", "direction", "weight"},
            label="validated Factor",
        )
    return values


def _context_adjustment_inputs(
    value: object,
) -> tuple[Mapping[str, Any], ...]:
    values = _object_array(value, "context_adjustments")
    for item in values:
        _exact_fields(
            item,
            required={
                "context_id",
                "weight",
                "mode",
                "context_evidence_id",
            },
            label="Context adjustment",
        )
    return values


def _reference(value: object) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(
        _mapping(value, "artifact reference")
    )


def _references(value: object, *, label: str) -> tuple[ValidationArtifactReference, ...]:
    references = tuple(_reference(item) for item in _array(value, label))
    ordered = _ordered_references(references)
    if not ordered or len(ordered) != len(references):
        raise ValueError(f"{label} must be non-empty and unique")
    return ordered


def _ordered_references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _object_array(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    values = _array(value, label)
    if any(not isinstance(item, Mapping) for item in values):
        raise ValueError(f"{label} must be an object array")
    return tuple(item for item in values if isinstance(item, Mapping))


def _string_array(value: object, label: str) -> tuple[str, ...]:
    values = _array(value, label)
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{label} must contain non-empty strings")
    return tuple(str(item) for item in values)


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    required: set[str],
    label: str,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    fields = set(payload)
    if not required.issubset(fields) or not fields.issubset(required | optional):
        raise ValueError(f"{label} fields mismatch")


def _nonempty_text(value: object, label: str) -> str:
    text = str(value)
    if not text.strip() or text != text.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    return text


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive_int(value: object, label: str) -> int:
    number = _integer(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _decimal(value: object, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} must be a decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{label} must be finite")
    return number


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


__all__ = [
    "CORRECTNESS_INFERENCE_BLOCK_LENGTHS",
    "CORRECTNESS_INFERENCE_CONFIDENCE",
    "CORRECTNESS_INFERENCE_ITERATIONS",
    "CORRECTNESS_PLACEBO_SEED",
    "HistoricalPhaseIIResearchOperator",
    "PHASE_II_OPERATOR_SCHEMA",
    "PhaseIIOperation",
    "build_postgres_phase_ii_operator",
]
