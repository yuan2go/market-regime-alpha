"""Pre-registered WP-ALPHA-RESEARCH-01 Factor, Gate and Candidate evaluation.

The module consumes owner-projected Research Panel rows.  It never computes a
technical Feature and never creates Strategy or Portfolio authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import erfc, sqrt
from statistics import pstdev
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.spine import FeatureSetConfiguration, ValueType
from market_regime_alpha.application.research_validation.formal_evaluation import (
    MultipleTestingMethod,
    adjust_multiple_testing,
)
from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    composite_percentile_scores,
    fractional_boundary_weights,
    rank_percentiles,
)


ALPHA_DISCOVERY_SCHEMA = "alpha-discovery-session-evaluation/v1"
ALPHA_DISCOVERY_TOP_K = (1, 3, 5, 10)
ALPHA_DISCOVERY_FACTOR_FAMILIES = (
    "PRICE_RETURN",
    "VOLUME_AMOUNT_TURNOVER",
    "TREND",
    "VOLATILITY_EXTENSION",
)
ALPHA_DISCOVERY_GATE_IDS = (
    "MARKET_REGIME",
    "THEME",
    "CAPITAL",
    "DYNAMIC_POOL",
)
ALPHA_DISCOVERY_CONTRACT_KIND = "ALPHA_DISCOVERY_EVALUATION_CONTRACT"


class AlphaFactorRole(str, Enum):
    NUMERIC_RANKED = "NUMERIC_RANKED"
    CATEGORICAL_DIAGNOSTIC = "CATEGORICAL_DIAGNOSTIC"
    RAW_LEVEL_DIAGNOSTIC = "RAW_LEVEL_DIAGNOSTIC"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class AlphaFactorDefinition:
    feature_id: str
    output_id: str
    family: str
    role: AlphaFactorRole
    higher_is_better: bool

    @property
    def factor_id(self) -> str:
        return f"{self.feature_id}:{self.output_id}"

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "feature_id": self.feature_id,
            "output_id": self.output_id,
            "family": self.family,
            "role": self.role.value,
            "higher_is_better": self.higher_is_better,
        }


@dataclass(frozen=True, slots=True)
class AlphaDiscoverySessionEvaluation:
    integrity_population_count: int
    target_observation_count: int
    session_slices: Mapping[str, str]
    factor_results: tuple[Mapping[str, Any], ...]
    gate_results: tuple[Mapping[str, Any], ...]
    policy_results: tuple[Mapping[str, Any], ...]
    schema_version: str = ALPHA_DISCOVERY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != ALPHA_DISCOVERY_SCHEMA:
            raise ValueError("unsupported Alpha Discovery session evaluation schema")
        if min(self.integrity_population_count, self.target_observation_count) < 0:
            raise ValueError("Alpha Discovery counts must be non-negative")
        for values, identity in (
            (self.factor_results, "factor_id"),
            (self.gate_results, "variant_id"),
            (self.policy_results, "variant_id"),
        ):
            keys = tuple(str(item[identity]) for item in values)
            if keys != tuple(sorted(set(keys))):
                raise ValueError("Alpha Discovery results must be unique and sorted")
        if self.session_slices != MappingProxyType(dict(sorted(self.session_slices.items()))):
            raise ValueError("Alpha Discovery session slices must be sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "integrity_population_count": self.integrity_population_count,
            "target_observation_count": self.target_observation_count,
            "session_slices": dict(self.session_slices),
            "factor_results": [dict(item) for item in self.factor_results],
            "gate_results": [dict(item) for item in self.gate_results],
            "policy_results": [dict(item) for item in self.policy_results],
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> AlphaDiscoverySessionEvaluation:
        return cls(
            integrity_population_count=int(payload["integrity_population_count"]),
            target_observation_count=int(payload["target_observation_count"]),
            session_slices=MappingProxyType(
                {
                    str(key): str(value)
                    for key, value in sorted(
                        _mapping(payload["session_slices"], "session slices").items()
                    )
                }
            ),
            factor_results=_frozen_objects(payload["factor_results"]),
            gate_results=_frozen_objects(payload["gate_results"]),
            policy_results=_frozen_objects(payload["policy_results"]),
            schema_version=str(payload["schema_version"]),
        )


def canonical_alpha_factor_registry(
    owner: FeatureSetConfiguration,
) -> tuple[AlphaFactorDefinition, ...]:
    """Classify every canonical Feature output before outcomes are inspected."""

    result: list[AlphaFactorDefinition] = []
    for definition in owner.definitions:
        for output in definition.output_schema:
            role = _factor_role(output.output_id, output.value_type)
            result.append(
                AlphaFactorDefinition(
                    feature_id=definition.feature_id,
                    output_id=output.output_id,
                    family=_factor_family(definition.feature_id, output.output_id),
                    role=role,
                    higher_is_better=True,
                )
            )
    return tuple(sorted(result, key=lambda item: item.factor_id))


def alpha_factor_registry_payload(
    owner: FeatureSetConfiguration,
) -> tuple[dict[str, Any], ...]:
    return tuple(item.to_canonical_dict() for item in canonical_alpha_factor_registry(owner))


def alpha_discovery_evaluation_contract_reference(
    owner: FeatureSetConfiguration,
) -> ValidationArtifactReference:
    """Bind the pre-registered evaluator without creating another Runtime owner."""

    payload = {
        "schema_version": "alpha-discovery-evaluation-contract/v2",
        "feature_set_reference": {
            "artifact_id": str(owner.feature_set_id),
            "content_hash": owner.content_hash,
        },
        "factor_registry": list(alpha_factor_registry_payload(owner)),
        "gate_ids": list(ALPHA_DISCOVERY_GATE_IDS),
        "gate_variants": [
            "CURRENT_HARD_GATE",
            "NO_PREDICTIVE_GATE",
            "SOFT_FEATURE",
        ],
        "candidate_policies": [
            "CURRENT_HARD_CHAIN",
            "HARD_INTEGRITY_PRICE_RETURN",
            "HARD_INTEGRITY_PRICE_VOLUME_TREND",
            "NO_PREDICTIVE_GATES",
            "SOFT_CONTEXT_CANDIDATE",
        ],
        "top_k": list(ALPHA_DISCOVERY_TOP_K),
        "ranking_contract": "GOLDEN_LOOP_V2_UNCHANGED",
        "multiple_testing": "BENJAMINI_HOCHBERG_FDR",
        "gate_incremental_effect_contract": (
            "MATCHED_SESSION_ONLY_REQUIRE_WITHIN_SESSION_ACCEPTED_AND_REJECTED"
        ),
    }
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        ALPHA_DISCOVERY_CONTRACT_KIND,
        ArtifactId(f"alpha-discovery-evaluation-contract:{digest[7:]}"),
        digest,
    )


def evaluate_alpha_discovery_session(
    *,
    panel: HistoricalSessionComponent,
    feature_owner: FeatureSetConfiguration | None = None,
) -> AlphaDiscoverySessionEvaluation:
    """Evaluate one session through the existing tie-aware ranking kernels."""

    if panel.component_kind is not HistoricalComponentKind.RESEARCH_PANEL:
        raise ValueError("Alpha Discovery requires a canonical Research Panel")
    rows = _objects(panel.payload.get("rows"), "Research Panel rows")
    observed = tuple(row for row in rows if _decimal(row.get("target_return")) is not None)
    integrity = tuple(row for row in observed if _integrity_passed(row))
    if feature_owner is None:
        # The frozen owner is imported lazily to avoid a module cycle.
        from market_regime_alpha.application.historical_corpus.frozen_experiment import (
            create_phase_e3_feature_configuration,
        )

        feature_owner = create_phase_e3_feature_configuration()
    registry = canonical_alpha_factor_registry(feature_owner)
    feature_values = {str(row["symbol"]): _feature_values(row) for row in integrity}

    factor_results = []
    numeric_by_family: dict[str, list[FactorCrossSection[str]]] = {
        family: [] for family in ALPHA_DISCOVERY_FACTOR_FAMILIES
    }
    numeric_by_id: dict[str, FactorCrossSection[str]] = {}
    entities = tuple(str(row["symbol"]) for row in integrity)
    for factor in registry:
        if factor.role is not AlphaFactorRole.NUMERIC_RANKED:
            continue
        values = {
            symbol: _decimal(feature_values[symbol].get((factor.feature_id, factor.output_id)))
            for symbol in entities
        }
        section = FactorCrossSection(
            factor_id=factor.factor_id,
            values=values,
            higher_is_better=factor.higher_is_better,
            weight=Decimal("1"),
        )
        numeric_by_family.setdefault(factor.family, []).append(section)
        numeric_by_id[factor.output_id] = section
        factor_results.append(
            _evaluate_variant(
                variant_id=factor.factor_id,
                family=factor.family,
                rows=integrity,
                raw_scores=values,
                before_count=len(integrity),
                factor_directions=(
                    (
                        factor.factor_id,
                        "HIGHER_IS_BETTER"
                        if factor.higher_is_better
                        else "LOWER_IS_BETTER",
                    ),
                ),
            )
        )

    family_scores = {
        family: _composite_scores(tuple(factors), entities)
        for family, factors in numeric_by_family.items()
    }
    technical_scores = _combine_named_scores(
        entities,
        {
            family: family_scores.get(family, {})
            for family in (
                "PRICE_RETURN",
                "VOLUME_AMOUNT_TURNOVER",
                "TREND",
            )
        },
    )
    price_scores = family_scores.get("PRICE_RETURN", {})
    price_directions = _factor_directions(
        tuple(numeric_by_family.get("PRICE_RETURN", ()))
    )
    technical_sections = tuple(
        section
        for family in ("PRICE_RETURN", "VOLUME_AMOUNT_TURNOVER", "TREND")
        for section in numeric_by_family.get(family, ())
    )
    technical_directions = _factor_directions(technical_sections)
    intraday_factor_ids = (
        "intraday_return_to_decision_time",
        "price_vs_vwap_return",
        "vwap_slope",
    )
    intraday_sections = tuple(
        numeric_by_id[factor_id]
        for factor_id in intraday_factor_ids
        if factor_id in numeric_by_id
    )
    intraday_scores = (
        _composite_scores(intraday_sections, entities)
        if len(intraday_sections) == len(intraday_factor_ids)
        else {}
    )
    intraday_directions = tuple(
        sorted(
            (
                item.factor_id.rsplit(":", 1)[-1],
                "HIGHER_IS_BETTER"
                if item.higher_is_better
                else "LOWER_IS_BETTER",
            )
            for item in intraday_sections
        )
    )
    context_scores = {
        "MARKET_REGIME": _gate_scores(integrity, "market_regime"),
        "THEME": _gate_scores(integrity, "theme"),
        "CAPITAL": _gate_scores(integrity, "capital"),
        "DYNAMIC_POOL": _gate_scores(integrity, "dynamic_pool"),
    }

    gate_results: list[Mapping[str, Any]] = []
    for gate_id in ALPHA_DISCOVERY_GATE_IDS:
        gate_name = gate_id.lower()
        passed = tuple(row for row in integrity if _predictive_gate_passed(row, gate_name))
        passed_entities = tuple(str(row["symbol"]) for row in passed)
        hard_scores = {symbol: technical_scores[symbol] for symbol in passed_entities}
        gate_results.extend(
            (
                _evaluate_variant(
                    variant_id=f"{gate_id}:CURRENT_HARD_GATE",
                    family=gate_id,
                    rows=passed,
                    raw_scores=hard_scores,
                    before_count=len(integrity),
                    gate_id=gate_id,
                    mode="CURRENT_HARD_GATE",
                    confounded=(gate_id == "DYNAMIC_POOL"),
                    factor_directions=technical_directions,
                ),
                _evaluate_variant(
                    variant_id=f"{gate_id}:NO_PREDICTIVE_GATE",
                    family=gate_id,
                    rows=integrity,
                    raw_scores=technical_scores,
                    before_count=len(integrity),
                    gate_id=gate_id,
                    mode="NO_PREDICTIVE_GATE",
                    confounded=(gate_id == "DYNAMIC_POOL"),
                    factor_directions=technical_directions,
                ),
                _evaluate_variant(
                    variant_id=f"{gate_id}:SOFT_FEATURE",
                    family=gate_id,
                    rows=integrity,
                    raw_scores=_combine_named_scores(
                        entities,
                        {"technical": technical_scores, "gate": context_scores[gate_id]},
                    ),
                    before_count=len(integrity),
                    gate_id=gate_id,
                    mode="SOFT_FEATURE",
                    confounded=(gate_id == "DYNAMIC_POOL"),
                ),
            )
        )

    candidate_rows = tuple(row for row in integrity if _candidate_chain_passed(row))
    candidate_scores = {
        str(row["symbol"]): _decimal(_candidate(row).get("score"))
        for row in candidate_rows
    }
    soft_context = _combine_named_scores(
        entities,
        {
            "technical": technical_scores,
            **{key.lower(): value for key, value in context_scores.items()},
        },
    )
    policy_specs = (
        ("CURRENT_HARD_CHAIN", candidate_rows, candidate_scores, ()),
        (
            "INTRADAY_CORRECTNESS_CHALLENGER",
            integrity,
            intraday_scores,
            intraday_directions,
        ),
        ("HARD_INTEGRITY_PRICE_RETURN", integrity, price_scores, price_directions),
        (
            "HARD_INTEGRITY_PRICE_VOLUME_TREND",
            integrity,
            technical_scores,
            technical_directions,
        ),
        ("NO_PREDICTIVE_GATES", integrity, technical_scores, technical_directions),
        ("SOFT_CONTEXT_CANDIDATE", integrity, soft_context, ()),
    )
    policy_results = tuple(
        _evaluate_variant(
            variant_id=variant_id,
            family="CANDIDATE_POLICY",
            rows=variant_rows,
            raw_scores=scores,
            before_count=len(integrity),
            factor_directions=factor_directions,
        )
        for variant_id, variant_rows, scores, factor_directions in policy_specs
    )
    return AlphaDiscoverySessionEvaluation(
        integrity_population_count=len(integrity),
        target_observation_count=len(observed),
        session_slices=MappingProxyType(
            {
                "market_regime": (
                    "NOT_ESTIMABLE"
                    if not rows
                    else str(rows[0].get("market_regime", "NOT_ESTIMABLE"))
                ),
                "volatility": (
                    "NOT_ESTIMABLE"
                    if not rows
                    else str(rows[0].get("volatility_bucket", "NOT_ESTIMABLE"))
                ),
            }
        ),
        factor_results=tuple(sorted(factor_results, key=lambda item: str(item["factor_id"]))),
        gate_results=tuple(sorted(gate_results, key=lambda item: str(item["variant_id"]))),
        policy_results=tuple(sorted(policy_results, key=lambda item: str(item["variant_id"]))),
    )


def aggregate_alpha_discovery_evaluations(
    values: tuple[tuple[date, AlphaDiscoverySessionEvaluation], ...],
) -> dict[str, Any]:
    """Aggregate canonical session evaluations without recomputing ranks."""

    if not values:
        raise ValueError("Alpha Discovery aggregation requires sessions")
    ordered = tuple(sorted(values, key=lambda item: item[0]))
    factor_results = _aggregate_result_group(
        ordered,
        result_name="factor_results",
        identity="factor_id",
    )
    gate_results = _aggregate_result_group(
        ordered,
        result_name="gate_results",
        identity="variant_id",
    )
    policy_results = _aggregate_result_group(
        ordered,
        result_name="policy_results",
        identity="variant_id",
    )
    _attach_gate_paired_effects(gate_results, ordered)
    tested = tuple(
        item
        for item in (*factor_results, *gate_results, *policy_results)
        if item["rank_ic_p_value"] is not None
    )
    adjusted = adjust_multiple_testing(
        tuple(Decimal(str(item["rank_ic_p_value"])) for item in tested),
        MultipleTestingMethod.BENJAMINI_HOCHBERG,
    )
    adjusted_by_id = {
        str(item["variant_id"]): str(value)
        for item, value in zip(tested, adjusted, strict=True)
    }
    for group in (factor_results, gate_results, policy_results):
        for item in group:
            item["rank_ic_bh_fdr_adjusted_p_value"] = adjusted_by_id.get(
                str(item["variant_id"])
            )
    gate_dispositions = _gate_dispositions(gate_results)
    return {
        "schema_version": "alpha-discovery-aggregate/v2",
        "session_count": len(ordered),
        "target_observation_count": sum(
            item.target_observation_count for _day, item in ordered
        ),
        "integrity_population_count": sum(
            item.integrity_population_count for _day, item in ordered
        ),
        "factor_results": factor_results,
        "gate_results": gate_results,
        "candidate_policy_results": policy_results,
        "gate_dispositions": gate_dispositions,
        "multiple_testing": {
            "family_id": "WP_ALPHA_RESEARCH_01_DISCOVERY_V1",
            "method": "BENJAMINI_HOCHBERG",
            "error_rate": "FDR",
            "hypothesis_count": len(tested),
            "exploratory_only": True,
        },
        "evidence_ceiling": {
            "classification": "EXPLORATORY_PIT_INCOMPLETE_IN_SAMPLE_DISCOVERY",
            "formal_oos": False,
            "calibrated": False,
            "production_qualified": False,
        },
    }


def _aggregate_result_group(
    values: tuple[tuple[date, AlphaDiscoverySessionEvaluation], ...],
    *,
    result_name: str,
    identity: str,
) -> list[dict[str, Any]]:
    by_id: dict[str, list[tuple[date, Mapping[str, Any], Mapping[str, str]]]] = {}
    for trading_date, evaluation in values:
        for item in getattr(evaluation, result_name):
            by_id.setdefault(str(item[identity]), []).append(
                (trading_date, item, evaluation.session_slices)
            )
    return [
        _aggregate_variant(variant_id, tuple(sessions))
        for variant_id, sessions in sorted(by_id.items())
    ]


def _aggregate_variant(
    variant_id: str,
    sessions: tuple[tuple[date, Mapping[str, Any], Mapping[str, str]], ...],
) -> dict[str, Any]:
    first = sessions[0][1]
    factor_directions = first.get("factor_directions", [])
    if any(item.get("factor_directions", []) != factor_directions for _day, item, _slice in sessions):
        raise ValueError("Alpha Discovery Factor definitions drifted across sessions")
    rank_ics = tuple(
        value
        for _day, item, _slices in sessions
        if (value := _decimal(item.get("rank_ic"))) is not None
    )
    ics = tuple(
        value
        for _day, item, _slices in sessions
        if (value := _decimal(item.get("ic"))) is not None
    )
    mean_rank_ic = _mean(rank_ics)
    rank_ic_dispersion = _dispersion(rank_ics)
    temporal: dict[str, Any] = {}
    for period_kind, period_key in (
        ("monthly", lambda day: day.strftime("%Y-%m")),
        ("quarterly", lambda day: f"{day.year}-Q{((day.month - 1) // 3) + 1}"),
    ):
        periods: dict[str, list[Decimal]] = {}
        for day, item, _slices in sessions:
            value = _decimal(item.get("rank_ic"))
            if value is not None:
                periods.setdefault(period_key(day), []).append(value)
        temporal[period_kind] = {
            key: {
                "session_count": len(period_values),
                "mean_rank_ic": _text(_mean(tuple(period_values))),
            }
            for key, period_values in sorted(periods.items())
        }
    conditional: dict[str, Any] = {}
    regimes: dict[str, list[Decimal]] = {}
    for _day, item, slices in sessions:
        value = _decimal(item.get("rank_ic"))
        if value is not None:
            regimes.setdefault(
                str(slices.get("market_regime", "NOT_ESTIMABLE")), []
            ).append(value)
    conditional["market_regime"] = {
        key: {
            "session_count": len(regime_values),
            "mean_rank_ic": _text(_mean(tuple(regime_values))),
        }
        for key, regime_values in sorted(regimes.items())
    }
    top_k = {
        str(k): _aggregate_top_k(sessions, str(k))
        for k in ALPHA_DISCOVERY_TOP_K
    }
    bucket_returns: dict[int, list[Decimal]] = {index: [] for index in range(1, 6)}
    for _day, item, _slices in sessions:
        for bucket in item.get("buckets", []):
            if isinstance(bucket, Mapping):
                value = _decimal(bucket.get("gross_return"))
                if value is not None:
                    bucket_returns[int(bucket["bucket"])].append(value)
    bucket_means = {
        str(index): _text(_mean(tuple(bucket_returns[index])))
        for index in range(1, 6)
    }
    available_bucket_means = tuple(
        (Decimal(index), value)
        for index in range(1, 6)
        if (value := _decimal(bucket_means[str(index)])) is not None
    )
    monotonicity = _correlation(
        tuple(item[0] for item in available_bucket_means),
        tuple(item[1] for item in available_bucket_means),
    )
    total_before = sum(int(item["before_count"]) for _day, item, _slice in sessions)
    total_after = sum(int(item["after_count"]) for _day, item, _slice in sessions)
    p_value = _normal_mean_p_value(rank_ics)
    return {
        "variant_id": variant_id,
        "family": str(first.get("family", "NOT_ESTIMABLE")),
        "factor_directions": factor_directions,
        **(
            {
                "gate_id": str(first["gate_id"]),
                "mode": str(first["mode"]),
                "confounded_with_hard_integrity": bool(
                    first.get("confounded_with_hard_integrity")
                ),
            }
            if "gate_id" in first
            else {}
        ),
        "session_count": len(sessions),
        "estimable_rank_ic_session_count": len(rank_ics),
        "before_count": total_before,
        "after_count": total_after,
        "rejection_rate": (
            None
            if total_before == 0
            else str(Decimal(total_before - total_after) / Decimal(total_before))
        ),
        "mean_ic": _text(_mean(ics)),
        "mean_rank_ic": _text(mean_rank_ic),
        "rank_ic_dispersion": _text(rank_ic_dispersion),
        "rank_ic_ir": _text(
            None
            if mean_rank_ic is None or rank_ic_dispersion in {None, Decimal("0")}
            else mean_rank_ic / rank_ic_dispersion
        ),
        "positive_rank_ic_ratio": _text(
            None
            if not rank_ics
            else Decimal(sum(item > 0 for item in rank_ics)) / Decimal(len(rank_ics))
        ),
        "rank_ic_p_value": _text(p_value),
        "rank_ic_bh_fdr_adjusted_p_value": None,
        "bucket_returns": bucket_means,
        "bucket_monotonicity": _text(monotonicity),
        "top_k": top_k,
        "temporal_stability": temporal,
        "conditional_effect": conditional,
    }


def _aggregate_top_k(
    sessions: tuple[tuple[date, Mapping[str, Any], Mapping[str, str]], ...],
    key: str,
) -> dict[str, Any]:
    metric_names = (
        "gross_return",
        "assumed_cost_return",
        "net_return",
        "hit_rate",
        "spread",
        "mfe",
        "mae",
        "capacity_ceiling",
    )
    metrics: dict[str, list[Decimal]] = {name: [] for name in metric_names}
    selections: list[dict[str, Decimal]] = []
    net_series: list[Decimal] = []
    for _day, item, _slices in sessions:
        top_k = item.get("top_k")
        if not isinstance(top_k, Mapping) or not isinstance(top_k.get(key), Mapping):
            continue
        result = top_k[key]
        assert isinstance(result, Mapping)
        for name in metric_names:
            value = _decimal(result.get(name))
            if value is not None:
                metrics[name].append(value)
                if name == "net_return":
                    net_series.append(value)
        selection = result.get("selection")
        if isinstance(selection, Mapping):
            selections.append(
                {
                    str(symbol): Decimal(str(weight))
                    for symbol, weight in selection.items()
                }
            )
    turnovers = tuple(
        _selection_turnover(previous, current, Decimal(key))
        for previous, current in zip(selections, selections[1:])
    )
    overlaps = tuple(Decimal("1") - item for item in turnovers)
    return {
        **{
            name: _text(_mean(tuple(metric_values)))
            for name, metric_values in metrics.items()
        },
        "turnover": _text(_mean(turnovers)),
        "overlap": _text(_mean(overlaps)),
        "max_drawdown": _text(_max_drawdown(tuple(net_series))),
        "estimable_session_count": len(net_series),
    }


def _selection_turnover(
    previous: Mapping[str, Decimal],
    current: Mapping[str, Decimal],
    slots: Decimal,
) -> Decimal:
    retained = sum(
        (min(previous.get(symbol, Decimal("0")), current.get(symbol, Decimal("0")))
         for symbol in set(previous) | set(current)),
        Decimal("0"),
    )
    return Decimal("1") - retained / slots


def _max_drawdown(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    wealth = Decimal("1")
    peak = wealth
    drawdown = Decimal("0")
    for value in values:
        wealth *= Decimal("1") + value
        peak = max(peak, wealth)
        if peak > 0:
            drawdown = min(drawdown, wealth / peak - Decimal("1"))
    return drawdown


def _attach_gate_paired_effects(
    gate_results: list[dict[str, Any]],
    evaluations: tuple[tuple[date, AlphaDiscoverySessionEvaluation], ...],
) -> None:
    """Attach only same-session Gate lift; temporal subsetting is not incremental evidence."""

    aggregate_by_gate: dict[str, dict[str, dict[str, Any]]] = {}
    for item in gate_results:
        aggregate_by_gate.setdefault(str(item["gate_id"]), {})[
            str(item["mode"])
        ] = item
    for gate_id, aggregate_modes in aggregate_by_gate.items():
        population_counts = {
            "pass_all_session_count": 0,
            "reject_all_session_count": 0,
            "mixed_population_session_count": 0,
        }
        paired: dict[str, dict[str, list[Decimal]]] = {
            "CURRENT_HARD_GATE": {"rank_ic": [], "top5_net": []},
            "SOFT_FEATURE": {"rank_ic": [], "top5_net": []},
        }
        for _trading_date, evaluation in evaluations:
            modes = {
                str(item["mode"]): item
                for item in evaluation.gate_results
                if str(item["gate_id"]) == gate_id
            }
            hard = modes["CURRENT_HARD_GATE"]
            control = modes["NO_PREDICTIVE_GATE"]
            before = int(hard["before_count"])
            after = int(hard["after_count"])
            if after == 0:
                population_counts["reject_all_session_count"] += 1
            elif after == before:
                population_counts["pass_all_session_count"] += 1
            else:
                population_counts["mixed_population_session_count"] += 1
            for mode in ("CURRENT_HARD_GATE", "SOFT_FEATURE"):
                # A hard filter is only causally separable when the same session
                # contains both accepted and rejected entities. Soft scores keep
                # the full population, so every matched session is eligible.
                if mode == "CURRENT_HARD_GATE" and not 0 < after < before:
                    continue
                variant = modes[mode]
                variant_rank = _decimal(variant.get("rank_ic"))
                control_rank = _decimal(control.get("rank_ic"))
                if variant_rank is not None and control_rank is not None:
                    paired[mode]["rank_ic"].append(variant_rank - control_rank)
                variant_net = _session_top_metric(variant, "5", "net_return")
                control_net = _session_top_metric(control, "5", "net_return")
                if variant_net is not None and control_net is not None:
                    paired[mode]["top5_net"].append(variant_net - control_net)
        effect = {
            **population_counts,
            "hard_paired_rank_ic_session_count": len(
                paired["CURRENT_HARD_GATE"]["rank_ic"]
            ),
            "hard_paired_top5_net_session_count": len(
                paired["CURRENT_HARD_GATE"]["top5_net"]
            ),
            "hard_vs_no_rank_ic_lift": _text(
                _mean(tuple(paired["CURRENT_HARD_GATE"]["rank_ic"]))
            ),
            "hard_vs_no_top5_net_lift": _text(
                _mean(tuple(paired["CURRENT_HARD_GATE"]["top5_net"]))
            ),
            "soft_paired_rank_ic_session_count": len(
                paired["SOFT_FEATURE"]["rank_ic"]
            ),
            "soft_paired_top5_net_session_count": len(
                paired["SOFT_FEATURE"]["top5_net"]
            ),
            "soft_vs_no_rank_ic_lift": _text(
                _mean(tuple(paired["SOFT_FEATURE"]["rank_ic"]))
            ),
            "soft_vs_no_top5_net_lift": _text(
                _mean(tuple(paired["SOFT_FEATURE"]["top5_net"]))
            ),
        }
        for item in aggregate_modes.values():
            item["matched_session_incremental_effect"] = effect


def _gate_dispositions(gate_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_gate: dict[str, dict[str, dict[str, Any]]] = {}
    for item in gate_results:
        by_gate.setdefault(str(item["gate_id"]), {})[str(item["mode"])] = item
    dispositions = []
    for gate_id, modes in sorted(by_gate.items()):
        hard = modes["CURRENT_HARD_GATE"]
        effect = _mapping(
            hard.get("matched_session_incremental_effect"),
            "matched Gate effect",
        )
        hard_net_lift = _decimal(effect.get("hard_vs_no_top5_net_lift"))
        soft_net_lift = _decimal(effect.get("soft_vs_no_top5_net_lift"))
        hard_rank_lift = _decimal(effect.get("hard_vs_no_rank_ic_lift"))
        soft_rank_lift = _decimal(effect.get("soft_vs_no_rank_ic_lift"))
        rejection = _decimal(hard.get("rejection_rate"))
        mixed_sessions = int(effect["mixed_population_session_count"])
        paired_sessions = min(
            int(effect["hard_paired_rank_ic_session_count"]),
            int(effect["hard_paired_top5_net_session_count"]),
        )
        if bool(hard.get("confounded_with_hard_integrity")):
            disposition = "RETEST"
            reason = "PREDICTIVE_EFFECT_NOT_SEPARABLE_OR_UNDERPOWERED"
        elif mixed_sessions < 20 or paired_sessions < 20:
            disposition = "RETEST"
            reason = "GATE_EFFECT_NOT_WITHIN_SESSION_SEPARABLE"
        elif None in {
            hard_net_lift,
            soft_net_lift,
            hard_rank_lift,
            soft_rank_lift,
            rejection,
        }:
            disposition = "RETEST"
            reason = "REQUIRED_INCREMENTAL_METRIC_NOT_ESTIMABLE"
        else:
            assert hard_net_lift is not None and soft_net_lift is not None
            assert hard_rank_lift is not None and soft_rank_lift is not None
            assert rejection is not None
            if (
                hard_net_lift > 0
                and hard_rank_lift > 0
                and hard_net_lift >= soft_net_lift
            ):
                disposition = "KEEP_AS_HARD_GATE"
                reason = "HARD_GATE_POSITIVE_INFORMATION_AND_ECONOMIC_LIFT"
            elif rejection >= Decimal("0.05") and soft_net_lift >= hard_net_lift and soft_rank_lift >= hard_rank_lift:
                disposition = "DEMOTE_TO_FACTOR"
                reason = "SOFT_CONSUMPTION_DOMINATES_WITH_MATERIAL_HARD_FILTER_LOSS"
            elif rejection >= Decimal("0.05") and hard_net_lift <= 0 and hard_rank_lift <= 0:
                disposition = "RETIRE"
                reason = "ESTIMABLE_HARD_GATE_HAS_NO_INCREMENTAL_LIFT_AND_FILTERS_MATERIAL_SAMPLE"
            else:
                disposition = "RETEST"
                reason = "MIXED_OR_UNSTABLE_INCREMENTAL_EVIDENCE"
        dispositions.append(
            {
                "gate_id": gate_id,
                "disposition": disposition,
                "reason": reason,
                "hard_vs_no_top5_net_lift": _text(hard_net_lift),
                "soft_vs_no_top5_net_lift": _text(soft_net_lift),
                "hard_vs_no_rank_ic_lift": _text(hard_rank_lift),
                "soft_vs_no_rank_ic_lift": _text(soft_rank_lift),
                "mixed_population_session_count": mixed_sessions,
                "matched_session_incremental_effect": effect,
            }
        )
    return dispositions


def _session_top_metric(
    item: Mapping[str, Any],
    key: str,
    metric: str,
) -> Decimal | None:
    top_k = item.get("top_k")
    if not isinstance(top_k, Mapping):
        return None
    result = top_k.get(key)
    if not isinstance(result, Mapping):
        return None
    return _decimal(result.get(metric))


def _normal_mean_p_value(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 3:
        return None
    mean = _mean(values)
    dispersion = _dispersion(values)
    if mean is None or dispersion in {None, Decimal("0")}:
        return None
    statistic = abs(float(mean / (dispersion / Decimal(str(sqrt(len(values)))))))
    return Decimal(str(erfc(statistic / sqrt(2))))


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _dispersion(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if len(values) < 2 else Decimal(str(pstdev(float(item) for item in values)))


def _evaluate_variant(
    *,
    variant_id: str,
    family: str,
    rows: tuple[Mapping[str, Any], ...],
    raw_scores: Mapping[str, Decimal | None],
    before_count: int,
    gate_id: str | None = None,
    mode: str | None = None,
    confounded: bool = False,
    factor_directions: tuple[tuple[str, str], ...] = (),
) -> Mapping[str, Any]:
    rows_by_symbol = {str(row["symbol"]): row for row in rows}
    scores = {
        symbol: value
        for symbol, value in raw_scores.items()
        if symbol in rows_by_symbol and value is not None
    }
    ranked = rank_percentiles(scores, higher_is_better=True)
    returns = {
        symbol: value
        for symbol, row in rows_by_symbol.items()
        if (value := _decimal(row.get("target_return"))) is not None
    }
    common = tuple(sorted(set(ranked.percentiles) & set(returns)))
    ic = _correlation(
        tuple(scores[symbol] for symbol in common),
        tuple(returns[symbol] for symbol in common),
    )
    return_ranks = rank_percentiles(
        {symbol: returns[symbol] for symbol in common},
        higher_is_better=True,
    )
    rank_ic = _correlation(
        tuple(ranked.percentiles[symbol] for symbol in common),
        tuple(return_ranks.percentiles[symbol] for symbol in common),
    )
    top_k = {
        str(k): _top_k_payload(
            rows_by_symbol,
            ranked.percentiles,
            slots=k,
        )
        for k in ALPHA_DISCOVERY_TOP_K
    }
    payload: dict[str, Any] = {
        "variant_id": variant_id,
        "factor_id": variant_id,
        "family": family,
        "status": ranked.status.value,
        "before_count": before_count,
        "after_count": len(rows),
        "observed_count": len(common),
        "missing_count": len(rows) - len(common),
        "rejection_rate": (
            None
            if before_count == 0
            else str(Decimal(before_count - len(rows)) / Decimal(before_count))
        ),
        "ic": _text(ic),
        "rank_ic": _text(rank_ic),
        "buckets": _bucket_payload(rows_by_symbol, ranked.percentiles),
        "top_k": top_k,
        "symbols": list(sorted(rows_by_symbol)),
        "factor_directions": [list(item) for item in factor_directions],
    }
    if gate_id is not None and mode is not None:
        payload.update(
            {
                "gate_id": gate_id,
                "mode": mode,
                "confounded_with_hard_integrity": confounded,
            }
        )
    return MappingProxyType(payload)


def _top_k_payload(
    rows: Mapping[str, Mapping[str, Any]],
    scores: Mapping[str, Decimal],
    *,
    slots: int,
) -> dict[str, Any]:
    selection = fractional_boundary_weights(
        scores,
        slots=slots,
        higher_is_better=True,
    )
    bottom = fractional_boundary_weights(
        scores,
        slots=slots,
        higher_is_better=False,
    )
    gross = _weighted(rows, selection.weights, "target_return")
    cost = _weighted(rows, selection.weights, "cost_return")
    net = None if gross is None or cost is None else gross - cost
    bottom_gross = _weighted(rows, bottom.weights, "target_return")
    hit = _weighted_indicator(rows, selection.weights, "target_return")
    return {
        "gross_return": _text(gross),
        "assumed_cost_return": _text(cost),
        "net_return": _text(net),
        "hit_rate": _text(hit),
        "spread": _text(None if gross is None or bottom_gross is None else gross - bottom_gross),
        "mfe": _text(_weighted(rows, selection.weights, "mfe")),
        "mae": _text(_weighted(rows, selection.weights, "mae")),
        "capacity_ceiling": _text(_weighted(rows, selection.weights, "capacity_ceiling")),
        "selection": {
            symbol: str(weight)
            for symbol, weight in sorted(selection.weights.items())
            if weight > 0
        },
    }


def _bucket_payload(
    rows: Mapping[str, Mapping[str, Any]],
    scores: Mapping[str, Decimal],
) -> list[dict[str, Any]]:
    if not scores:
        return []
    weights = _tie_aware_equal_count_bucket_weights(scores, bucket_count=5)
    result = []
    for bucket, bucket_weights in enumerate(weights, 1):
        gross = _weighted(rows, bucket_weights, "target_return")
        effective_count = sum(bucket_weights.values(), Decimal("0"))
        result.append(
            {
                "bucket": bucket,
                "observation_count": sum(weight > 0 for weight in bucket_weights.values()),
                "effective_count": str(effective_count),
                "gross_return": _text(gross),
            }
        )
    return result


def _tie_aware_equal_count_bucket_weights(
    scores: Mapping[str, Decimal],
    *,
    bucket_count: int,
) -> tuple[Mapping[str, Decimal], ...]:
    """Split score ties fractionally; entity identity never chooses a bucket."""

    if bucket_count <= 0:
        raise ValueError("Alpha Discovery bucket count must be positive")
    target = Decimal(len(scores)) / Decimal(bucket_count)
    result = [dict.fromkeys(scores, Decimal("0")) for _ in range(bucket_count)]
    grouped: dict[Decimal, list[str]] = {}
    for symbol, score in scores.items():
        grouped.setdefault(score, []).append(symbol)
    bucket = 0
    remaining_capacity = target
    for score in sorted(grouped, reverse=True):
        symbols = grouped[score]
        remaining_group = Decimal(len(symbols))
        while remaining_group > 0 and bucket < bucket_count:
            allocated = min(remaining_group, remaining_capacity)
            per_symbol = allocated / Decimal(len(symbols))
            for symbol in symbols:
                result[bucket][symbol] += per_symbol
            remaining_group -= allocated
            remaining_capacity -= allocated
            if remaining_capacity == 0:
                bucket += 1
                remaining_capacity = target
    return tuple(MappingProxyType(item) for item in result)


def _composite_scores(
    factors: tuple[FactorCrossSection[str], ...],
    entities: tuple[str, ...],
) -> Mapping[str, Decimal]:
    if not factors or not entities:
        return MappingProxyType({})
    return composite_percentile_scores(factors, entities=entities).scores


def _factor_directions(
    factors: tuple[FactorCrossSection[str], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                item.factor_id,
                "HIGHER_IS_BETTER"
                if item.higher_is_better
                else "LOWER_IS_BETTER",
            )
            for item in factors
        )
    )


def _combine_named_scores(
    entities: tuple[str, ...],
    values: Mapping[str, Mapping[str, Decimal]],
) -> Mapping[str, Decimal]:
    factors = tuple(
        FactorCrossSection(
            factor_id=name,
            values={entity: scores.get(entity) for entity in entities},
            higher_is_better=True,
            weight=Decimal("1"),
        )
        for name, scores in sorted(values.items())
        if scores
    )
    return _composite_scores(factors, entities)


def _gate_scores(
    rows: tuple[Mapping[str, Any], ...],
    gate_name: str,
) -> Mapping[str, Decimal]:
    values = {
        str(row["symbol"]): _decimal(
            _mapping(_mapping(row.get("gate_diagnostics"), "gate diagnostics").get("predictive"), "predictive gates")
            .get(gate_name, {})
            .get("score")
        )
        for row in rows
    }
    return rank_percentiles(
        {symbol: value for symbol, value in values.items() if value is not None},
        higher_is_better=True,
    ).percentiles


def _feature_values(row: Mapping[str, Any]) -> dict[tuple[str, str], object]:
    return {
        (str(item["feature_id"]), str(item["output_id"])): item.get("value")
        for item in _objects(row.get("research_features", []), "research features")
        if item.get("state") == "AVAILABLE"
    }


def _integrity_passed(row: Mapping[str, Any]) -> bool:
    diagnostics = _mapping(row.get("gate_diagnostics"), "gate diagnostics")
    return bool(_mapping(diagnostics.get("hard_integrity"), "hard integrity").get("passed"))


def _predictive_gate_passed(row: Mapping[str, Any], name: str) -> bool:
    diagnostics = _mapping(row.get("gate_diagnostics"), "gate diagnostics")
    predictive = _mapping(diagnostics.get("predictive"), "predictive gates")
    return bool(_mapping(predictive.get(name), name).get("passed"))


def _candidate(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(row.get("candidate_diagnostic"), "candidate diagnostic")


def _candidate_chain_passed(row: Mapping[str, Any]) -> bool:
    candidate = _candidate(row)
    return str(candidate.get("selection_status")) in {"SELECTED", "WATCHLIST"} and _decimal(candidate.get("score")) is not None


def _factor_role(output_id: str, value_type: ValueType) -> AlphaFactorRole:
    if output_id in {
        "ema_5", "ema_10", "ema_12", "ema_20", "ema_26", "ema_60",
        "sma_5", "sma_10", "sma_20", "sma_60", "session_vwap",
    }:
        return AlphaFactorRole.RAW_LEVEL_DIAGNOSTIC
    if value_type is ValueType.TEXT:
        return AlphaFactorRole.CATEGORICAL_DIAGNOSTIC
    return AlphaFactorRole.NUMERIC_RANKED


def _factor_family(feature_id: str, output_id: str) -> str:
    if output_id in {"high_low_range", "range_expansion", "gap_extension", "volume_price_overextension", "consecutive_up_sessions"}:
        return "VOLATILITY_EXTENSION"
    if feature_id in {"technical.price_action.v1", "technical.intraday_price_action.v1"}:
        return "PRICE_RETURN"
    if feature_id == "technical.volume_amount_structure.v1":
        return "VOLUME_AMOUNT_TURNOVER"
    return "TREND"


def _correlation(xs: tuple[Decimal, ...], ys: tuple[Decimal, ...]) -> Decimal | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    with localcontext() as context:
        context.prec = 48
        mean_x = sum(xs, Decimal("0")) / Decimal(len(xs))
        mean_y = sum(ys, Decimal("0")) / Decimal(len(ys))
        covariance = sum(
            ((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)),
            Decimal("0"),
        )
        variance_x = sum(((x - mean_x) ** 2 for x in xs), Decimal("0"))
        variance_y = sum(((y - mean_y) ** 2 for y in ys), Decimal("0"))
        if variance_x == 0 or variance_y == 0:
            return None
        return covariance / Decimal(str(sqrt(float(variance_x * variance_y))))


def _weighted(
    rows: Mapping[str, Mapping[str, Any]],
    weights: Mapping[str, Decimal],
    field: str,
) -> Decimal | None:
    pairs = tuple(
        (weight, value)
        for symbol, weight in weights.items()
        if weight > 0 and (value := _decimal(rows[symbol].get(field))) is not None
    )
    total = sum((weight for weight, _value in pairs), Decimal("0"))
    return None if total == 0 else sum((weight * value for weight, value in pairs), Decimal("0")) / total


def _weighted_indicator(
    rows: Mapping[str, Mapping[str, Any]],
    weights: Mapping[str, Decimal],
    field: str,
) -> Decimal | None:
    pairs = tuple(
        (weight, value)
        for symbol, weight in weights.items()
        if weight > 0 and (value := _decimal(rows[symbol].get(field))) is not None
    )
    total = sum((weight for weight, _value in pairs), Decimal("0"))
    return None if total == 0 else sum((weight for weight, value in pairs if value > 0), Decimal("0")) / total


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except Exception:
        return None
    return result if result.is_finite() else None


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Alpha Discovery {label} must be an object")
    return value


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"Alpha Discovery {label} must be an object array")
    return tuple(value)


def _frozen_objects(value: object) -> tuple[Mapping[str, Any], ...]:
    return tuple(MappingProxyType(dict(item)) for item in _objects(value, "results"))


__all__ = [
    "ALPHA_DISCOVERY_FACTOR_FAMILIES",
    "ALPHA_DISCOVERY_CONTRACT_KIND",
    "ALPHA_DISCOVERY_GATE_IDS",
    "ALPHA_DISCOVERY_SCHEMA",
    "ALPHA_DISCOVERY_TOP_K",
    "AlphaDiscoverySessionEvaluation",
    "AlphaFactorDefinition",
    "AlphaFactorRole",
    "aggregate_alpha_discovery_evaluations",
    "alpha_discovery_evaluation_contract_reference",
    "alpha_factor_registry_payload",
    "canonical_alpha_factor_registry",
    "evaluate_alpha_discovery_session",
]
