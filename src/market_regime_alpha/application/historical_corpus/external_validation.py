"""Frozen, one-dimension-at-a-time external Alpha validation capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from statistics import pstdev
from typing import Any

from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessStatus,
)
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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


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
    top_k: int
    cost_assumption: Decimal
    minimum_effect_retention: Decimal
    minimum_coverage: Decimal
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
            "top_k": top_k,
            "cost_assumption": str(cost_assumption),
            "minimum_effect_retention": str(minimum_effect_retention),
            "minimum_coverage": str(minimum_coverage),
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
            top_k,
            cost_assumption,
            minimum_effect_retention,
            minimum_coverage,
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
            "top_k": self.top_k,
            "cost_assumption": str(self.cost_assumption),
            "minimum_effect_retention": str(self.minimum_effect_retention),
            "minimum_coverage": str(self.minimum_coverage),
            "bootstrap_iterations": self.bootstrap_iterations,
            "block_lengths": list(self.block_lengths),
        }


@dataclass(frozen=True, slots=True)
class FrozenExternalValidationExperiment:
    experiment_id: ArtifactId
    experiment_hash: str
    hypothesis: FrozenAlphaHypothesis
    correctness_evidence_reference: ValidationArtifactReference
    correctness_status: AlphaCorrectnessStatus
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
        if self.correctness_status is not AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED:
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
        correctness_evidence_reference: ValidationArtifactReference,
        correctness_status: AlphaCorrectnessStatus,
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
                correctness_evidence_reference=correctness_evidence_reference,
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
            correctness_evidence_reference,
            correctness_status,
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
    score: Decimal
    target_return: Decimal
    gross_return: Decimal
    cost_return: Decimal
    capacity: Decimal | None


@dataclass(frozen=True, slots=True)
class ExternalValidationEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    experiment_reference: ValidationArtifactReference
    thresholds_reference: ValidationArtifactReference
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


def evaluate_external_validation(
    experiment: FrozenExternalValidationExperiment,
    *,
    observations: tuple[ExternalValidationObservation, ...],
    expected_population: int,
    discovery_rank_ic: Decimal | None,
    pit_complete: bool,
    free_data: bool,
) -> ExternalValidationEvaluation:
    """Evaluate only the frozen hypothesis; no factor or threshold input is accepted."""

    ordered = tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)) or expected_population <= 0:
        raise ValueError("external validation population is invalid")
    coverage = Decimal(len(ordered)) / Decimal(expected_population)
    daily = _daily_rank_ic(ordered)
    rank_ic = _mean(daily)
    top_sets, top_gross, top_cost, top_net, capacity = _top_k_metrics(
        ordered, experiment.hypothesis.top_k
    )
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
                for session, value in _daily_rank_ic_with_dates(ordered)
            ),
        )
        conservative = inference.sensitivity[-1]
        confidence = (conservative.lower, conservative.upper)
        stability = inference.temporal_stability
    qualified = (
        coverage >= experiment.hypothesis.minimum_coverage
        and retention is not None
        and retention >= experiment.hypothesis.minimum_effect_retention
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
    values = {
        "experiment_reference": experiment.reference.to_canonical_dict(),
        "thresholds_reference": experiment.hypothesis.reference.to_canonical_dict(),
        "observation_count": len(ordered),
        "coverage": str(coverage),
        "rank_ic": _text(rank_ic),
        "confidence_interval": None if confidence is None else [str(item) for item in confidence],
        "positive_ic_ratio": _text(_positive_ratio(daily)),
        "icir": _text(_icir(daily)),
        "bucket_monotonicity": _text(_bucket_monotonicity(ordered)),
        "top_k_gross": _text(top_gross),
        "cost_diagnostic": _text(top_cost),
        "top_k_net": _text(top_net),
        "turnover": _text(_turnover(top_sets)),
        "drawdown": _text(_drawdown(_daily_top_returns(ordered, experiment.hypothesis.top_k))),
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
        len(ordered),
        coverage,
        rank_ic,
        confidence,
        _positive_ratio(daily),
        _icir(daily),
        _bucket_monotonicity(ordered),
        top_gross,
        top_cost,
        top_net,
        _turnover(top_sets),
        _drawdown(_daily_top_returns(ordered, experiment.hypothesis.top_k)),
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
    observations: tuple[ExternalValidationObservation, ...],
) -> dict[date, tuple[ExternalValidationObservation, ...]]:
    result: dict[date, list[ExternalValidationObservation]] = {}
    for item in observations:
        result.setdefault(item.session, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: (-item.score, item.symbol)))
        for key, values in sorted(result.items())
    }


def _daily_rank_ic_with_dates(
    observations: tuple[ExternalValidationObservation, ...],
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
    observations: tuple[ExternalValidationObservation, ...],
) -> tuple[Decimal, ...]:
    return tuple(value for _session, value in _daily_rank_ic_with_dates(observations))


def _top_k_metrics(
    observations: tuple[ExternalValidationObservation, ...], top_k: int
) -> tuple[tuple[frozenset[str], ...], Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    selections: list[frozenset[str]] = []
    gross: list[Decimal] = []
    costs: list[Decimal] = []
    net: list[Decimal] = []
    capacities: list[Decimal] = []
    for values in _groups(observations).values():
        selected = values[: min(top_k, len(values))]
        if not selected:
            continue
        selections.append(frozenset(item.symbol for item in selected))
        gross.append(_mean(tuple(item.gross_return for item in selected)) or Decimal("0"))
        costs.append(_mean(tuple(item.cost_return for item in selected)) or Decimal("0"))
        net.append(_mean(tuple(item.gross_return - item.cost_return for item in selected)) or Decimal("0"))
        capacities.extend(item.capacity for item in selected if item.capacity is not None)
    return (
        tuple(selections),
        _mean(tuple(gross)),
        _mean(tuple(costs)),
        _mean(tuple(net)),
        _mean(tuple(capacities)),
    )


def _bucket_monotonicity(
    observations: tuple[ExternalValidationObservation, ...],
) -> Decimal | None:
    bucket_scores: list[Decimal] = []
    bucket_returns: list[Decimal] = []
    for values in _groups(observations).values():
        count = len(values)
        if count < 3:
            continue
        for index, item in enumerate(values):
            bucket_scores.append(Decimal(count - index))
            bucket_returns.append(item.target_return)
    return _correlation(_ranks(tuple(bucket_scores)), _ranks(tuple(bucket_returns)))


def _daily_top_returns(
    observations: tuple[ExternalValidationObservation, ...], top_k: int
) -> tuple[Decimal, ...]:
    return tuple(
        _mean(tuple(item.gross_return - item.cost_return for item in values[:top_k])) or Decimal("0")
        for values in _groups(observations).values()
        if values
    )


def _turnover(selections: tuple[frozenset[str], ...]) -> Decimal | None:
    if len(selections) < 2:
        return None
    return _mean(
        tuple(
            Decimal(len(current.symmetric_difference(previous)))
            / Decimal(max(1, len(current | previous)))
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
