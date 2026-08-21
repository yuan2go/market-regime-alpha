"""Frozen, one-dimension-at-a-time external Alpha validation capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from statistics import pstdev
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    MovingBlockInferenceProtocol,
    SessionEstimate,
    evaluate_robust_inference,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    HyperparameterDomain,
    ResearchExperimentDefinition,
    SearchBudget,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    composite_percentile_scores,
    fractional_boundary_weights,
)


class ValidationDimension(str, Enum):
    TEMPORAL_VALIDATION = "TEMPORAL_VALIDATION"
    UNIVERSE_VALIDATION = "UNIVERSE_VALIDATION"
    PROVIDER_VALIDATION = "PROVIDER_VALIDATION"


@dataclass(frozen=True, slots=True)
class ValidationScope:
    temporal_partition: str
    universe_reference: ValidationArtifactReference
    provider_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        if not self.temporal_partition.strip():
            raise ValueError("validation temporal partition must be identified")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "temporal_partition": self.temporal_partition,
            "universe_reference": self.universe_reference.to_canonical_dict(),
            "provider_reference": self.provider_reference.to_canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class FrozenAlphaHypothesis:
    hypothesis_id: ArtifactId
    hypothesis_hash: str
    factor_directions: tuple[tuple[str, str], ...]
    candidate_scoring: str
    decision_time_policy: str
    target_reference: ValidationArtifactReference
    feature_reference: ValidationArtifactReference
    feature_version: str
    cost_policy_reference: ValidationArtifactReference
    discovery_evidence_reference: ValidationArtifactReference
    discovery_rank_ic: Decimal
    top_k: int
    cost_assumption: Decimal
    minimum_effect_retention: Decimal
    minimum_coverage: Decimal
    minimum_top_k_net: Decimal
    bootstrap_iterations: int
    block_lengths: tuple[int, ...]
    schema_version: str = "frozen-alpha-hypothesis/v1"

    def __post_init__(self) -> None:
        if self.factor_directions != tuple(sorted(set(self.factor_directions))):
            raise ValueError("frozen factor definitions must be unique and sorted")
        if not self.factor_directions or any(
            direction not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}
            for _factor, direction in self.factor_directions
        ):
            raise ValueError("frozen factor direction is invalid")
        if self.top_k <= 0 or self.bootstrap_iterations <= 0:
            raise ValueError("frozen evaluation dimensions must be positive")
        if not self.block_lengths or any(item <= 0 for item in self.block_lengths):
            raise ValueError("frozen block lengths must be positive")
        if not Decimal("0") <= self.cost_assumption < Decimal("1"):
            raise ValueError("cost assumption is invalid")
        if not self.minimum_top_k_net.is_finite():
            raise ValueError("minimum Top-K net threshold must be finite")
        if self.candidate_scoring != "EQUAL_WEIGHT_RANK_PERCENTILE":
            raise ValueError("unsupported frozen Candidate scoring")
        if self.discovery_evidence_reference.artifact_kind != "HISTORICAL_ALPHA_ABLATION_EVIDENCE":
            raise ValueError("frozen hypothesis requires Alpha Discovery Evidence")
        for value in (self.minimum_effect_retention, self.minimum_coverage):
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError("qualification threshold is invalid")
        if canonical_hash(self.identity_payload()) != self.hypothesis_hash:
            raise ValueError("frozen Alpha hypothesis hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        factor_directions: tuple[tuple[str, str], ...],
        candidate_scoring: str,
        decision_time_policy: str,
        target_reference: ValidationArtifactReference,
        top_k: int,
        cost_assumption: Decimal,
        minimum_effect_retention: Decimal,
        minimum_coverage: Decimal,
        feature_reference: ValidationArtifactReference,
        feature_version: str,
        cost_policy_reference: ValidationArtifactReference,
        discovery_evidence_reference: ValidationArtifactReference,
        discovery_rank_ic: Decimal,
        minimum_top_k_net: Decimal = Decimal("0"),
        bootstrap_iterations: int = 500,
        block_lengths: tuple[int, ...] = (1, 5, 10),
    ) -> FrozenAlphaHypothesis:
        ordered_factors = tuple(sorted(set(factor_directions)))
        ordered_blocks = tuple(sorted(set(block_lengths)))
        values = {
            "schema_version": "frozen-alpha-hypothesis/v1",
            "factor_directions": [list(item) for item in ordered_factors],
            "candidate_scoring": candidate_scoring,
            "decision_time_policy": decision_time_policy,
            "target_reference": target_reference.to_canonical_dict(),
            "feature_reference": feature_reference.to_canonical_dict(),
            "feature_version": feature_version,
            "cost_policy_reference": cost_policy_reference.to_canonical_dict(),
            "discovery_evidence_reference": discovery_evidence_reference.to_canonical_dict(),
            "discovery_rank_ic": str(discovery_rank_ic),
            "top_k": top_k,
            "cost_assumption": str(cost_assumption),
            "minimum_effect_retention": str(minimum_effect_retention),
            "minimum_coverage": str(minimum_coverage),
            "minimum_top_k_net": str(minimum_top_k_net),
            "bootstrap_iterations": bootstrap_iterations,
            "block_lengths": list(ordered_blocks),
        }
        digest = canonical_hash(values)
        return cls(
            ArtifactId(f"frozen-alpha-hypothesis:{digest[7:]}"),
            digest,
            ordered_factors,
            candidate_scoring,
            decision_time_policy,
            target_reference,
            feature_reference,
            feature_version,
            cost_policy_reference,
            discovery_evidence_reference,
            discovery_rank_ic,
            top_k,
            cost_assumption,
            minimum_effect_retention,
            minimum_coverage,
            minimum_top_k_net,
            bootstrap_iterations,
            ordered_blocks,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "FROZEN_ALPHA_HYPOTHESIS", self.hypothesis_id, self.hypothesis_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_directions": [list(item) for item in self.factor_directions],
            "candidate_scoring": self.candidate_scoring,
            "decision_time_policy": self.decision_time_policy,
            "target_reference": self.target_reference.to_canonical_dict(),
            "feature_reference": self.feature_reference.to_canonical_dict(),
            "feature_version": self.feature_version,
            "cost_policy_reference": self.cost_policy_reference.to_canonical_dict(),
            "discovery_evidence_reference": self.discovery_evidence_reference.to_canonical_dict(),
            "discovery_rank_ic": str(self.discovery_rank_ic),
            "top_k": self.top_k,
            "cost_assumption": str(self.cost_assumption),
            "minimum_effect_retention": str(self.minimum_effect_retention),
            "minimum_coverage": str(self.minimum_coverage),
            "minimum_top_k_net": str(self.minimum_top_k_net),
            "bootstrap_iterations": self.bootstrap_iterations,
            "block_lengths": list(self.block_lengths),
        }


@dataclass(frozen=True, slots=True)
class FrozenExternalValidationExperiment:
    experiment_id: ArtifactId
    experiment_hash: str
    hypothesis: FrozenAlphaHypothesis
    correctness_evidence: HistoricalResearchEvidence
    discovery_scope: ValidationScope
    validation_scope: ValidationScope
    dimension: ValidationDimension
    random_seed: int
    experiment_definition: ResearchExperimentDefinition
    schema_version: str = "external-validation-experiment/v1"

    def __post_init__(self) -> None:
        _require_isolated_dimension(
            self.discovery_scope, self.validation_scope, self.dimension
        )
        self.correctness_evidence.verify_identity()
        if (
            self.correctness_evidence.evidence_kind
            is not HistoricalEvidenceKind.ALPHA_CORRECTNESS
            or self.correctness_evidence.payload.get("status")
            != "CORRECTNESS_SUPPORTED"
        ):
            raise ValueError("external validation requires a correctness-supported hypothesis")
        if (
            self.experiment_id != self.experiment_definition.definition_id
            or self.experiment_hash != self.experiment_definition.definition_hash
        ):
            raise ValueError("external validation must use Research Experiment Definition authority")

    @classmethod
    def create(
        cls,
        *,
        hypothesis: FrozenAlphaHypothesis,
        correctness_evidence: HistoricalResearchEvidence,
        discovery_scope: ValidationScope,
        validation_scope: ValidationScope,
        dimension: ValidationDimension,
        random_seed: int,
    ) -> FrozenExternalValidationExperiment:
        definition = ResearchExperimentDefinition.create(
            research_question=(
                "Does the correctness-supported frozen Alpha retain its effect when "
                f"only {dimension.value} changes?"
            ),
            hypothesis=(
                "Factor definitions, direction, Candidate scoring, DecisionTime, Target, "
                "Top-K, costs, thresholds and evaluation remain frozen."
            ),
            decision_time_policy=hypothesis.decision_time_policy,
            target_references=(hypothesis.target_reference,),
            feature_reference=hypothesis.feature_reference,
            feature_version=hypothesis.feature_version,
            allowed_model_families=("FROZEN_EXTERNAL_ALPHA_EVALUATOR",),
            hyperparameter_space=_external_domains(
                hypothesis=hypothesis,
                correctness_evidence_reference=correctness_evidence.reference,
                discovery_scope=discovery_scope,
                validation_scope=validation_scope,
                dimension=dimension,
            ),
            search_budget=SearchBudget(1, 300),
            primary_hypothesis_ids=(
                "EXTERNAL_VALIDATION:RANK_IC:V1",
                "EXTERNAL_VALIDATION:TOP_K_NET:V1",
            ),
            secondary_hypothesis_ids=(
                "EXTERNAL_VALIDATION:CAPACITY:V1",
                "EXTERNAL_VALIDATION:EFFECT_RETENTION:V1",
                "EXTERNAL_VALIDATION:TEMPORAL_STABILITY:V1",
            ),
            multiple_testing_family_id="WP_ALPHA_RESEARCH_02_FROZEN_V1",
            stopping_rule="EXHAUST_FROZEN_VALIDATION_SCOPE_ONCE",
            train_validation_policy="DISCOVERY_NEVER_REUSED_FOR_RETUNING",
            purge_embargo_policy="TARGET_LINEAGE_MUST_PREDATE_EVALUATION_AVAILABILITY",
            oos_unlock_policy="FORMAL_OOS_LOCKED_CLOSED",
            randomness_algorithm="DETERMINISTIC_FROZEN_SEED",
            random_seeds=(random_seed,),
            cost_policy_reference=hypothesis.cost_policy_reference,
            schema_version="research-experiment-definition/v2",
        )
        return cls(
            definition.definition_id,
            definition.definition_hash,
            hypothesis,
            correctness_evidence,
            discovery_scope,
            validation_scope,
            dimension,
            random_seed,
            definition,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION", self.experiment_id, self.experiment_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return self.experiment_definition.identity_payload()


@dataclass(frozen=True, slots=True)
class ExternalValidationObservation:
    session: date
    symbol: str
    factor_values: Mapping[str, Decimal]
    decision_reference_price: Decimal
    executable_entry_price: Decimal
    target_reference_price: Decimal
    source_reference: ValidationArtifactReference
    capacity: Decimal | None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.factor_values:
            raise ValueError("External validation observation is incomplete")
        if any(not value.is_finite() for value in self.factor_values.values()):
            raise ValueError("External validation Factor values must be finite")
        if min(
            self.decision_reference_price,
            self.executable_entry_price,
            self.target_reference_price,
        ) <= 0:
            raise ValueError("External validation prices must be positive")
        if self.source_reference.artifact_kind not in {
            "RESEARCH_PANEL",
            "HISTORICAL_RESEARCH_PANEL",
        }:
            raise ValueError("External validation requires Research Panel lineage")
        if self.capacity is not None and (
            not self.capacity.is_finite() or self.capacity < 0
        ):
            raise ValueError("External validation capacity must be finite and non-negative")

    @property
    def target_return(self) -> Decimal:
        return self.target_reference_price / self.decision_reference_price - Decimal("1")

    @property
    def gross_return(self) -> Decimal:
        return self.target_reference_price / self.executable_entry_price - Decimal("1")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.isoformat(),
            "symbol": self.symbol,
            "factor_values": {
                key: str(value) for key, value in sorted(self.factor_values.items())
            },
            "decision_reference_price": str(self.decision_reference_price),
            "executable_entry_price": str(self.executable_entry_price),
            "target_reference_price": str(self.target_reference_price),
            "source_reference": self.source_reference.to_canonical_dict(),
            "capacity": None if self.capacity is None else str(self.capacity),
        }


@dataclass(frozen=True, slots=True)
class _ScoredObservation:
    session: date
    symbol: str
    score: Decimal
    target_return: Decimal
    gross_return: Decimal
    capacity: Decimal | None


@dataclass(frozen=True, slots=True)
class ExternalValidationEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    experiment_reference: ValidationArtifactReference
    thresholds_reference: ValidationArtifactReference
    factor_directions: tuple[tuple[str, str], ...]
    observation_set_hash: str
    observation_count: int
    coverage: Decimal
    rank_ic: Decimal | None
    confidence_interval: tuple[Decimal, Decimal] | None
    positive_ic_ratio: Decimal | None
    icir: Decimal | None
    bucket_monotonicity: Decimal | None
    top_k_gross: Decimal | None
    cost_diagnostic: Decimal | None
    top_k_net: Decimal | None
    turnover: Decimal | None
    drawdown: Decimal | None
    temporal_stability: str
    capacity_diagnostic: Decimal | None
    effect_retention: Decimal | None
    degradation: Decimal | None
    qualification_status: str
    external_validation_classification: str
    formal_oos: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("evaluation_hash", self.evaluation_hash)
        require_sha256("observation_set_hash", self.observation_set_hash)
        if self.observation_count < 0 or not Decimal("0") <= self.coverage <= Decimal("1"):
            raise ValueError("External validation coverage is invalid")
        if self.formal_oos:
            raise ValueError("External validation cannot grant Formal OOS")
        if self.factor_directions != tuple(sorted(set(self.factor_directions))):
            raise ValueError("External validation Factor directions must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("External validation limitations must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.evaluation_hash or self.evaluation_id != ArtifactId(
            f"external-validation-evaluation:{digest[7:]}"
        ):
            raise ValueError("External validation Evaluation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "experiment_reference": self.experiment_reference.to_canonical_dict(),
            "thresholds_reference": self.thresholds_reference.to_canonical_dict(),
            "factor_directions": [list(item) for item in self.factor_directions],
            "observation_set_hash": self.observation_set_hash,
            "observation_count": self.observation_count,
            "coverage": str(self.coverage),
            "rank_ic": _text(self.rank_ic),
            "confidence_interval": (
                None
                if self.confidence_interval is None
                else [str(item) for item in self.confidence_interval]
            ),
            "positive_ic_ratio": _text(self.positive_ic_ratio),
            "icir": _text(self.icir),
            "bucket_monotonicity": _text(self.bucket_monotonicity),
            "top_k_gross": _text(self.top_k_gross),
            "cost_diagnostic": _text(self.cost_diagnostic),
            "top_k_net": _text(self.top_k_net),
            "turnover": _text(self.turnover),
            "drawdown": _text(self.drawdown),
            "temporal_stability": self.temporal_stability,
            "capacity_diagnostic": _text(self.capacity_diagnostic),
            "effect_retention": _text(self.effect_retention),
            "degradation": _text(self.degradation),
            "qualification_status": self.qualification_status,
            "external_validation_classification": self.external_validation_classification,
            "formal_oos": self.formal_oos,
            "limitations": list(self.limitations),
        }

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "EXTERNAL_VALIDATION_EVALUATION",
            self.evaluation_id,
            self.evaluation_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": str(self.evaluation_id),
            "evaluation_hash": self.evaluation_hash,
            **self.identity_payload(),
        }


def evaluate_external_validation(
    experiment: FrozenExternalValidationExperiment,
    *,
    observations: tuple[ExternalValidationObservation, ...],
    expected_population: int,
    pit_complete: bool,
    free_data: bool,
) -> ExternalValidationEvaluation:
    """Evaluate only the frozen hypothesis; no factor or threshold input is accepted."""

    ordered = tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)) or expected_population <= 0:
        raise ValueError("external validation population is invalid")
    if len(ordered) > expected_population:
        raise ValueError("external validation observations exceed frozen population")
    expected_factors = {item[0] for item in experiment.hypothesis.factor_directions}
    if any(set(item.factor_values) != expected_factors for item in ordered):
        raise ValueError("External validation Factor set drifted from frozen hypothesis")
    coverage = Decimal(len(ordered)) / Decimal(expected_population)
    scored = _score_observations(experiment.hypothesis, ordered)
    daily = _daily_rank_ic(scored)
    rank_ic = _mean(daily)
    top_sets, top_gross, top_cost, top_net, capacity = _top_k_metrics(
        scored,
        experiment.hypothesis.top_k,
        experiment.hypothesis.cost_assumption,
    )
    discovery_rank_ic = experiment.hypothesis.discovery_rank_ic
    retention = (
        None
        if rank_ic is None or discovery_rank_ic in {None, Decimal("0")}
        else rank_ic / discovery_rank_ic
    )
    degradation = (
        None if rank_ic is None or discovery_rank_ic is None else discovery_rank_ic - rank_ic
    )
    block_lengths = tuple(
        item for item in experiment.hypothesis.block_lengths if item <= len(daily)
    )
    confidence: tuple[Decimal, Decimal] | None = None
    stability = "NOT_ESTIMABLE"
    if daily and block_lengths:
        inference = evaluate_robust_inference(
            MovingBlockInferenceProtocol.create(
                iterations=experiment.hypothesis.bootstrap_iterations,
                block_lengths=block_lengths,
                confidence_level=Decimal("0.95"),
                seed=experiment.random_seed,
            ),
            tuple(
                SessionEstimate(session, value)
                for session, value in _daily_rank_ic_with_dates(scored)
            ),
        )
        conservative = inference.sensitivity[-1]
        confidence = (conservative.lower, conservative.upper)
        stability = inference.temporal_stability
    qualified = (
        coverage >= experiment.hypothesis.minimum_coverage
        and retention is not None
        and retention >= experiment.hypothesis.minimum_effect_retention
        and top_net is not None
        and top_net >= experiment.hypothesis.minimum_top_k_net
    )
    limitations = tuple(
        sorted(
            {
                "FORMAL_OOS_FALSE",
                "PRODUCTION_QUALIFIED_FALSE",
                *("FREE_DATA" if free_data else "" ,),
                *("PIT_INCOMPLETE" if not pit_complete else "PIT_COMPLETE_NOT_OOS",),
            }
            - {""}
        )
    )
    observation_set_hash = canonical_hash(
        {"observations": [item.to_canonical_dict() for item in ordered]}
    )
    values = {
        "experiment_reference": experiment.reference.to_canonical_dict(),
        "thresholds_reference": experiment.hypothesis.reference.to_canonical_dict(),
        "factor_directions": [
            list(item) for item in experiment.hypothesis.factor_directions
        ],
        "observation_set_hash": observation_set_hash,
        "observation_count": len(ordered),
        "coverage": str(coverage),
        "rank_ic": _text(rank_ic),
        "confidence_interval": None if confidence is None else [str(item) for item in confidence],
        "positive_ic_ratio": _text(_positive_ratio(daily)),
        "icir": _text(_icir(daily)),
        "bucket_monotonicity": _text(_bucket_monotonicity(scored)),
        "top_k_gross": _text(top_gross),
        "cost_diagnostic": _text(top_cost),
        "top_k_net": _text(top_net),
        "turnover": _text(_turnover(top_sets)),
        "drawdown": _text(
            _drawdown(
                _daily_top_returns(
                    scored,
                    experiment.hypothesis.top_k,
                    experiment.hypothesis.cost_assumption,
                )
            )
        ),
        "temporal_stability": stability,
        "capacity_diagnostic": _text(capacity),
        "effect_retention": _text(retention),
        "degradation": _text(degradation),
        "qualification_status": "SUPPORTED" if qualified else "NOT_SUPPORTED",
        "external_validation_classification": "EXTERNAL_VALIDATION",
        "formal_oos": False,
        "limitations": list(limitations),
    }
    digest = canonical_hash(values)
    return ExternalValidationEvaluation(
        ArtifactId(f"external-validation-evaluation:{digest[7:]}"),
        digest,
        experiment.reference,
        experiment.hypothesis.reference,
        experiment.hypothesis.factor_directions,
        observation_set_hash,
        len(ordered),
        coverage,
        rank_ic,
        confidence,
        _positive_ratio(daily),
        _icir(daily),
        _bucket_monotonicity(scored),
        top_gross,
        top_cost,
        top_net,
        _turnover(top_sets),
        _drawdown(
            _daily_top_returns(
                scored,
                experiment.hypothesis.top_k,
                experiment.hypothesis.cost_assumption,
            )
        ),
        stability,
        capacity,
        retention,
        degradation,
        "SUPPORTED" if qualified else "NOT_SUPPORTED",
        "EXTERNAL_VALIDATION",
        False,
        limitations,
    )


def _external_domains(
    *,
    hypothesis: FrozenAlphaHypothesis,
    correctness_evidence_reference: ValidationArtifactReference,
    discovery_scope: ValidationScope,
    validation_scope: ValidationScope,
    dimension: ValidationDimension,
) -> tuple[HyperparameterDomain, ...]:
    domains = (
        HyperparameterDomain(
            "candidate_scoring", (hypothesis.candidate_scoring,)
        ),
        HyperparameterDomain(
            "correctness_evidence",
            (
                f"{correctness_evidence_reference.artifact_kind}|"
                f"{correctness_evidence_reference.artifact_id}|"
                f"{correctness_evidence_reference.content_hash}",
            ),
        ),
        HyperparameterDomain(
            "discovery_scope_hash", (canonical_hash(discovery_scope.to_canonical_dict()),)
        ),
        HyperparameterDomain(
            "discovery_evidence",
            (
                f"{hypothesis.discovery_evidence_reference.artifact_kind}|"
                f"{hypothesis.discovery_evidence_reference.artifact_id}|"
                f"{hypothesis.discovery_evidence_reference.content_hash}",
            ),
        ),
        HyperparameterDomain("discovery_rank_ic", (str(hypothesis.discovery_rank_ic),)),
        HyperparameterDomain(
            "factor_directions",
            tuple(
                sorted(f"{factor}|{direction}" for factor, direction in hypothesis.factor_directions)
            ),
        ),
        HyperparameterDomain(
            "minimum_coverage", (str(hypothesis.minimum_coverage),)
        ),
        HyperparameterDomain(
            "minimum_effect_retention",
            (str(hypothesis.minimum_effect_retention),),
        ),
        HyperparameterDomain("minimum_top_k_net", (str(hypothesis.minimum_top_k_net),)),
        HyperparameterDomain("cost_assumption", (str(hypothesis.cost_assumption),)),
        HyperparameterDomain("top_k", (str(hypothesis.top_k),)),
        HyperparameterDomain("validation_dimension", (dimension.value,)),
        HyperparameterDomain(
            "validation_scope_hash", (canonical_hash(validation_scope.to_canonical_dict()),)
        ),
    )
    return tuple(sorted(domains, key=lambda item: item.parameter_name))


def _require_isolated_dimension(
    discovery: ValidationScope,
    validation: ValidationScope,
    dimension: ValidationDimension,
) -> None:
    differences = {
        ValidationDimension.TEMPORAL_VALIDATION: discovery.temporal_partition != validation.temporal_partition,
        ValidationDimension.UNIVERSE_VALIDATION: discovery.universe_reference != validation.universe_reference,
        ValidationDimension.PROVIDER_VALIDATION: discovery.provider_reference != validation.provider_reference,
    }
    if {item for item, changed in differences.items() if changed} != {dimension}:
        raise ValueError("Experiment must change exactly the declared validation dimension")


def _groups(
    observations: tuple[_ScoredObservation, ...],
) -> dict[date, tuple[_ScoredObservation, ...]]:
    result: dict[date, list[_ScoredObservation]] = {}
    for item in observations:
        result.setdefault(item.session, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.symbol))
        for key, values in sorted(result.items())
    }


def _score_observations(
    hypothesis: FrozenAlphaHypothesis,
    observations: tuple[ExternalValidationObservation, ...],
) -> tuple[_ScoredObservation, ...]:
    result: list[_ScoredObservation] = []
    by_session: dict[date, list[ExternalValidationObservation]] = {}
    for item in observations:
        by_session.setdefault(item.session, []).append(item)
    for session, rows in sorted(by_session.items()):
        ordered = tuple(sorted(rows, key=lambda item: item.symbol))
        scores = composite_percentile_scores(
            tuple(
                FactorCrossSection(
                    factor_id=factor_id,
                    values={
                        item.symbol: item.factor_values[factor_id] for item in ordered
                    },
                    higher_is_better=direction == "HIGHER_IS_BETTER",
                    weight=Decimal("1"),
                )
                for factor_id, direction in hypothesis.factor_directions
            ),
            entities=tuple(item.symbol for item in ordered),
        ).scores
        result.extend(
            _ScoredObservation(
                session,
                item.symbol,
                scores[item.symbol],
                item.target_return,
                item.gross_return,
                item.capacity,
            )
            for item in ordered
        )
    return tuple(sorted(result, key=lambda item: (item.session, item.symbol)))


def _daily_rank_ic_with_dates(
    observations: tuple[_ScoredObservation, ...],
) -> tuple[tuple[date, Decimal], ...]:
    result: list[tuple[date, Decimal]] = []
    for session, values in _groups(observations).items():
        correlation = _correlation(
            _ranks(tuple(item.score for item in values)),
            _ranks(tuple(item.target_return for item in values)),
        )
        if correlation is not None:
            result.append((session, correlation))
    return tuple(result)


def _daily_rank_ic(
    observations: tuple[_ScoredObservation, ...],
) -> tuple[Decimal, ...]:
    return tuple(value for _session, value in _daily_rank_ic_with_dates(observations))


def _top_k_metrics(
    observations: tuple[_ScoredObservation, ...],
    top_k: int,
    frozen_cost: Decimal,
) -> tuple[tuple[Mapping[str, Decimal], ...], Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    selections: list[Mapping[str, Decimal]] = []
    gross: list[Decimal] = []
    costs: list[Decimal] = []
    net: list[Decimal] = []
    capacities: list[Decimal] = []
    for values in _groups(observations).values():
        boundary = fractional_boundary_weights(
            {item.symbol: item.score for item in values},
            slots=min(top_k, len(values)),
            higher_is_better=True,
        )
        selected = tuple(
            (item, boundary.weights[item.symbol])
            for item in values
            if boundary.weights[item.symbol] > 0
        )
        if not selected:
            continue
        denominator = sum((weight for _item, weight in selected), Decimal("0"))
        selections.append(boundary.weights)
        session_gross = sum(
            (item.gross_return * weight for item, weight in selected), Decimal("0")
        ) / denominator
        gross.append(session_gross)
        costs.append(frozen_cost)
        net.append(session_gross - frozen_cost)
        capacities.extend(
            item.capacity * weight
            for item, weight in selected
            if item.capacity is not None
        )
    return (
        tuple(selections),
        _mean(tuple(gross)),
        _mean(tuple(costs)),
        _mean(tuple(net)),
        _mean(tuple(capacities)),
    )


def _bucket_monotonicity(
    observations: tuple[_ScoredObservation, ...],
) -> Decimal | None:
    bucket_scores: list[Decimal] = []
    bucket_returns: list[Decimal] = []
    for values in _groups(observations).values():
        count = len(values)
        if count < 3:
            continue
        for item in values:
            bucket_scores.append(item.score)
            bucket_returns.append(item.target_return)
    return _correlation(_ranks(tuple(bucket_scores)), _ranks(tuple(bucket_returns)))


def _daily_top_returns(
    observations: tuple[_ScoredObservation, ...],
    top_k: int,
    frozen_cost: Decimal,
) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for rows in _groups(observations).values():
        if not rows:
            continue
        selection = fractional_boundary_weights(
            {item.symbol: item.score for item in rows},
            slots=min(top_k, len(rows)),
            higher_is_better=True,
        )
        denominator = sum(selection.weights.values(), Decimal("0"))
        values.append(
            sum(
                (
                    item.gross_return * selection.weights[item.symbol]
                    for item in rows
                ),
                Decimal("0"),
            )
            / denominator
            - frozen_cost
        )
    return tuple(values)


def _turnover(selections: tuple[Mapping[str, Decimal], ...]) -> Decimal | None:
    if len(selections) < 2:
        return None
    return _mean(
        tuple(
            sum(
                (
                    abs(current.get(symbol, Decimal("0")) - previous.get(symbol, Decimal("0")))
                    for symbol in current.keys() | previous.keys()
                ),
                Decimal("0"),
            )
            / Decimal("2")
            for previous, current in zip(selections, selections[1:], strict=False)
        )
    )


def _drawdown(returns: tuple[Decimal, ...]) -> Decimal | None:
    if not returns:
        return None
    wealth = peak = Decimal("1")
    drawdown = Decimal("0")
    for value in returns:
        wealth *= Decimal("1") + value
        peak = max(peak, wealth)
        drawdown = min(drawdown, wealth / peak - Decimal("1"))
    return drawdown


def _positive_ratio(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if not values else Decimal(sum(item > 0 for item in values)) / Decimal(len(values))


def _icir(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    deviation = pstdev(float(item) for item in values)
    return None if deviation == 0 else (_mean(values) or Decimal("0")) / Decimal(str(deviation))


def _ranks(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [Decimal("0")] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        average = (Decimal(position + 1) + Decimal(end)) / Decimal("2")
        for index, _value in ordered[position:end]:
            result[index] = average
        position = end
    return tuple(result)


def _correlation(xs: tuple[Decimal, ...], ys: tuple[Decimal, ...]) -> Decimal | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    with localcontext() as context:
        context.prec = 48
        mean_x = _mean(xs)
        mean_y = _mean(ys)
        assert mean_x is not None and mean_y is not None
        covariance = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)), Decimal("0"))
        variance_x = sum(((x - mean_x) ** 2 for x in xs), Decimal("0"))
        variance_y = sum(((y - mean_y) ** 2 for y in ys), Decimal("0"))
        if variance_x == 0 or variance_y == 0:
            return None
        result = covariance / Decimal(str(sqrt(float(variance_x * variance_y))))
        return Decimal("1") if abs(result - 1) < Decimal("1e-24") else result


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "ExternalValidationEvaluation",
    "ExternalValidationObservation",
    "FrozenAlphaHypothesis",
    "FrozenExternalValidationExperiment",
    "ValidationDimension",
    "ValidationScope",
    "evaluate_external_validation",
]
