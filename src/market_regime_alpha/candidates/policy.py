"""Explainable incumbent/challenger Candidate Policy research evaluation.

Layer A answers legality only.  Layer B ranks externally validated factors.
Layer C applies only evidence-supported Context adjustments.  This module is a
research evaluator over frozen inputs and does not replace the Candidate owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


class CandidatePolicyRole(str, Enum):
    INCUMBENT = "INCUMBENT"
    CHALLENGER = "CHALLENGER"


@dataclass(frozen=True, slots=True)
class ValidatedFactorDefinition:
    factor_id: str
    direction: str
    weight: Decimal
    external_validation_evidence: ValidationArtifactReference
    externally_validated: bool

    def __post_init__(self) -> None:
        if not self.factor_id.strip() or self.direction not in {
            "HIGHER_IS_BETTER",
            "LOWER_IS_BETTER",
        }:
            raise ValueError("validated Candidate factor definition is invalid")
        if self.weight <= 0:
            raise ValueError("validated Candidate factor weight must be positive")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "direction": self.direction,
            "weight": str(self.weight),
            "external_validation_evidence": self.external_validation_evidence.to_canonical_dict(),
            "externally_validated": self.externally_validated,
        }


@dataclass(frozen=True, slots=True)
class ContextAdjustmentDefinition:
    context_id: str
    weight: Decimal
    mode: str
    context_evidence: ValidationArtifactReference
    evidence_status: str

    def __post_init__(self) -> None:
        if self.mode not in {
            "SCORE_ADJUSTMENT",
            "CONFIDENCE_ADJUSTMENT",
            "RISK_CONDITION",
        }:
            raise ValueError("unsupported Candidate Context adjustment")
        if self.evidence_status not in {"AMPLIFIER", "SUPPRESSOR"}:
            raise ValueError("Candidate Context requires stable supporting evidence")
        if not self.weight.is_finite():
            raise ValueError("Candidate Context weight must be finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "weight": str(self.weight),
            "mode": self.mode,
            "context_evidence": self.context_evidence.to_canonical_dict(),
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicyDefinition:
    policy_id: ArtifactId
    policy_hash: str
    role: CandidatePolicyRole
    policy_version: str
    validated_factors: tuple[ValidatedFactorDefinition, ...]
    context_adjustments: tuple[ContextAdjustmentDefinition, ...]
    top_k: int
    minimum_liquidity: Decimal
    schema_version: str = "candidate-policy-definition/v2"

    def __post_init__(self) -> None:
        factor_ids = tuple(item.factor_id for item in self.validated_factors)
        context_ids = tuple(item.context_id for item in self.context_adjustments)
        if factor_ids != tuple(sorted(set(factor_ids))):
            raise ValueError("Candidate factors must be unique and sorted")
        if context_ids != tuple(sorted(set(context_ids))):
            raise ValueError("Candidate Context definitions must be unique and sorted")
        if self.role is CandidatePolicyRole.CHALLENGER and (
            not self.validated_factors
            or any(not item.externally_validated for item in self.validated_factors)
        ):
            raise ValueError("Challenger only admits externally validated factors")
        if self.role is CandidatePolicyRole.INCUMBENT and (
            self.validated_factors or self.context_adjustments
        ):
            raise ValueError("Incumbent is projected unchanged, not reconstructed")
        if self.top_k <= 0 or self.minimum_liquidity < 0:
            raise ValueError("Candidate policy thresholds are invalid")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Candidate Policy hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        role: CandidatePolicyRole,
        policy_version: str,
        validated_factors: tuple[ValidatedFactorDefinition, ...],
        context_adjustments: tuple[ContextAdjustmentDefinition, ...],
        top_k: int,
        minimum_liquidity: Decimal,
    ) -> CandidatePolicyDefinition:
        factors = tuple(sorted(validated_factors, key=lambda item: item.factor_id))
        contexts = tuple(sorted(context_adjustments, key=lambda item: item.context_id))
        values = {
            "schema_version": "candidate-policy-definition/v2",
            "role": role.value,
            "policy_version": policy_version,
            "validated_factors": [item.to_canonical_dict() for item in factors],
            "context_adjustments": [item.to_canonical_dict() for item in contexts],
            "top_k": top_k,
            "minimum_liquidity": str(minimum_liquidity),
        }
        digest = canonical_hash(values)
        return cls(
            ArtifactId(f"candidate-policy:{digest[7:]}"),
            digest,
            role,
            policy_version,
            factors,
            contexts,
            top_k,
            minimum_liquidity,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            f"{self.role.value}_CANDIDATE_POLICY", self.policy_id, self.policy_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role.value,
            "policy_version": self.policy_version,
            "validated_factors": [item.to_canonical_dict() for item in self.validated_factors],
            "context_adjustments": [item.to_canonical_dict() for item in self.context_adjustments],
            "top_k": self.top_k,
            "minimum_liquidity": str(self.minimum_liquidity),
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicyInput:
    session: date
    symbol: str
    universe_eligible: bool
    tradable: bool
    suspended: bool
    data_integrity: bool
    required_history: bool
    pit_correct: bool
    liquidity: Decimal
    trading_restrictions_satisfied: bool
    factor_values: Mapping[str, Decimal | None]
    context_values: Mapping[str, Decimal | None]
    incumbent_score: Decimal | None
    incumbent_selected: bool
    incumbent_factor_contributions: Mapping[str, Decimal]


@dataclass(frozen=True, slots=True)
class CandidatePolicyRecord:
    session: date
    symbol: str
    hard_integrity_eligible: bool
    hard_gate_failure_reasons: tuple[str, ...]
    factor_available: bool
    factor_values: Mapping[str, Decimal | None]
    factor_contributions: Mapping[str, Decimal]
    alpha_score: Decimal | None
    context_adjustments: Mapping[str, Decimal]
    final_score: Decimal | None
    rank: int | None
    selection_status: str
    reason_codes: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.isoformat(),
            "symbol": self.symbol,
            "hard_integrity_eligible": self.hard_integrity_eligible,
            "hard_gate_failure_reasons": list(self.hard_gate_failure_reasons),
            "factor_available": self.factor_available,
            "factor_values": {
                key: None if value is None else str(value)
                for key, value in self.factor_values.items()
            },
            "factor_contributions": {
                key: str(value) for key, value in self.factor_contributions.items()
            },
            "alpha_score": None if self.alpha_score is None else str(self.alpha_score),
            "context_adjustments": {
                key: str(value) for key, value in self.context_adjustments.items()
            },
            "final_score": None if self.final_score is None else str(self.final_score),
            "rank": self.rank,
            "selection_status": self.selection_status,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicyEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    policy_reference: ValidationArtifactReference
    records: tuple[CandidatePolicyRecord, ...]


@dataclass(frozen=True, slots=True)
class CandidatePolicyComparison:
    comparison_id: ArtifactId
    comparison_hash: str
    incumbent_reference: ValidationArtifactReference
    challenger_reference: ValidationArtifactReference
    incumbent_coverage: Decimal
    challenger_coverage: Decimal
    incumbent_selection_count: int
    challenger_selection_count: int
    incumbent_rank_ic: Decimal | None
    challenger_rank_ic: Decimal | None
    incumbent_top_k: Decimal | None
    challenger_top_k: Decimal | None
    selection_turnover: Decimal | None
    stability: str


def evaluate_candidate_policy(
    policy: CandidatePolicyDefinition,
    inputs: tuple[CandidatePolicyInput, ...],
) -> CandidatePolicyEvaluation:
    ordered = tuple(sorted(inputs, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("Candidate Policy inputs must be unique")
    records: list[CandidatePolicyRecord] = []
    for session, session_inputs in _input_groups(ordered).items():
        integrity = {item.symbol: _hard_integrity(policy, item) for item in session_inputs}
        if policy.role is CandidatePolicyRole.INCUMBENT:
            contributions = {
                item.symbol: _mapping_decimal(item.incumbent_factor_contributions)
                for item in session_inputs
            }
        else:
            contributions = _factor_contributions(policy, session_inputs, integrity)
        provisional: list[tuple[CandidatePolicyInput, CandidatePolicyRecord]] = []
        for item in session_inputs:
            hard_reasons = integrity[item.symbol]
            hard_eligible = not hard_reasons
            if policy.role is CandidatePolicyRole.INCUMBENT:
                available = item.incumbent_score is not None
                factor_values = MappingProxyType(dict(sorted(item.factor_values.items())))
                alpha_score = item.incumbent_score if hard_eligible else None
                context = MappingProxyType({})
                final = alpha_score
                status = (
                    "HARD_INELIGIBLE"
                    if not hard_eligible
                    else "FACTOR_UNAVAILABLE"
                    if not available
                    else "SELECTED"
                    if item.incumbent_selected
                    else "ELIGIBLE_NOT_SELECTED"
                )
                reasons = ()
            else:
                missing = tuple(
                    definition.factor_id
                    for definition in policy.validated_factors
                    if item.factor_values.get(definition.factor_id) is None
                )
                available = not missing
                factor_values = MappingProxyType(
                    {
                        definition.factor_id: item.factor_values.get(definition.factor_id)
                        for definition in policy.validated_factors
                    }
                )
                alpha_score = (
                    sum(contributions[item.symbol].values(), Decimal("0"))
                    if hard_eligible and available
                    else None
                )
                context = _context_adjustments(policy, item) if alpha_score is not None else MappingProxyType({})
                final = None if alpha_score is None else alpha_score + sum(context.values(), Decimal("0"))
                status = (
                    "HARD_INELIGIBLE"
                    if not hard_eligible
                    else "FACTOR_UNAVAILABLE"
                    if not available
                    else "ELIGIBLE_NOT_SELECTED"
                )
                reasons = tuple(f"FACTOR_MISSING:{factor_id}" for factor_id in missing)
            provisional.append(
                (
                    item,
                    CandidatePolicyRecord(
                        session,
                        item.symbol,
                        hard_eligible,
                        hard_reasons,
                        available,
                        factor_values,
                        contributions[item.symbol] if alpha_score is not None else MappingProxyType({}),
                        alpha_score,
                        context,
                        final,
                        None,
                        status,
                        tuple(sorted({*hard_reasons, *reasons})),
                    ),
                )
            )
        ranked = sorted(
            (record for _item, record in provisional if record.final_score is not None),
            key=lambda record: (-record.final_score, record.symbol),
        )
        ranks = {record.symbol: index for index, record in enumerate(ranked, 1)}
        for item, record in provisional:
            rank = ranks.get(record.symbol)
            selected = (
                record.selection_status == "SELECTED"
                if policy.role is CandidatePolicyRole.INCUMBENT
                else rank is not None and rank <= policy.top_k
            )
            records.append(
                CandidatePolicyRecord(
                    record.session,
                    record.symbol,
                    record.hard_integrity_eligible,
                    record.hard_gate_failure_reasons,
                    record.factor_available,
                    record.factor_values,
                    record.factor_contributions,
                    record.alpha_score,
                    record.context_adjustments,
                    record.final_score,
                    rank,
                    "SELECTED" if selected else record.selection_status,
                    record.reason_codes,
                )
            )
    result = tuple(sorted(records, key=lambda item: (item.session, item.symbol)))
    payload = {
        "policy_reference": policy.reference.to_canonical_dict(),
        "records": [item.to_canonical_dict() for item in result],
    }
    digest = canonical_hash(payload)
    return CandidatePolicyEvaluation(
        ArtifactId(f"candidate-policy-evaluation:{digest[7:]}"),
        digest,
        policy.reference,
        result,
    )


def compare_candidate_policies(
    incumbent: CandidatePolicyEvaluation,
    challenger: CandidatePolicyEvaluation,
    *,
    realized_returns: Mapping[tuple[date, str], Decimal],
) -> CandidatePolicyComparison:
    if incumbent.policy_reference.artifact_kind != "INCUMBENT_CANDIDATE_POLICY":
        raise ValueError("Candidate comparison requires incumbent first")
    if challenger.policy_reference.artifact_kind != "CHALLENGER_CANDIDATE_POLICY":
        raise ValueError("Candidate comparison requires challenger second")
    incumbent_keys = {(item.session, item.symbol) for item in incumbent.records}
    challenger_keys = {(item.session, item.symbol) for item in challenger.records}
    if incumbent_keys != challenger_keys or not incumbent_keys:
        raise ValueError("Candidate comparison requires the same frozen dataset")
    if not incumbent_keys.issubset(realized_returns):
        raise ValueError("Candidate comparison target coverage is incomplete")
    incumbent_coverage = _coverage(incumbent.records)
    challenger_coverage = _coverage(challenger.records)
    incumbent_ic = _rank_ic(incumbent.records, realized_returns)
    challenger_ic = _rank_ic(challenger.records, realized_returns)
    incumbent_top = _selected_return(incumbent.records, realized_returns)
    challenger_top = _selected_return(challenger.records, realized_returns)
    incumbent_selected = _selected_sets(incumbent.records)
    challenger_selected = _selected_sets(challenger.records)
    shared_sessions = tuple(sorted(incumbent_selected.keys() & challenger_selected.keys()))
    turnover_values = tuple(
        Decimal(len(incumbent_selected[session] ^ challenger_selected[session]))
        / Decimal(max(1, len(incumbent_selected[session] | challenger_selected[session])))
        for session in shared_sessions
    )
    stability = _comparison_stability(challenger.records, realized_returns)
    values = {
        "incumbent_reference": incumbent.policy_reference.to_canonical_dict(),
        "challenger_reference": challenger.policy_reference.to_canonical_dict(),
        "incumbent_coverage": str(incumbent_coverage),
        "challenger_coverage": str(challenger_coverage),
        "incumbent_selection_count": sum(item.selection_status == "SELECTED" for item in incumbent.records),
        "challenger_selection_count": sum(item.selection_status == "SELECTED" for item in challenger.records),
        "incumbent_rank_ic": _text(incumbent_ic),
        "challenger_rank_ic": _text(challenger_ic),
        "incumbent_top_k": _text(incumbent_top),
        "challenger_top_k": _text(challenger_top),
        "selection_turnover": _text(_mean(turnover_values)),
        "stability": stability,
    }
    digest = canonical_hash(values)
    return CandidatePolicyComparison(
        ArtifactId(f"candidate-policy-comparison:{digest[7:]}"),
        digest,
        incumbent.policy_reference,
        challenger.policy_reference,
        incumbent_coverage,
        challenger_coverage,
        int(values["incumbent_selection_count"]),
        int(values["challenger_selection_count"]),
        incumbent_ic,
        challenger_ic,
        incumbent_top,
        challenger_top,
        _mean(turnover_values),
        stability,
    )


def _hard_integrity(
    policy: CandidatePolicyDefinition, item: CandidatePolicyInput
) -> tuple[str, ...]:
    reasons = set()
    if not item.universe_eligible:
        reasons.add("UNIVERSE_INELIGIBLE")
    if not item.tradable:
        reasons.add("NOT_TRADABLE")
    if item.suspended:
        reasons.add("SUSPENDED")
    if not item.data_integrity:
        reasons.add("DATA_INTEGRITY_FAILED")
    if not item.required_history:
        reasons.add("REQUIRED_HISTORY_MISSING")
    if not item.pit_correct:
        reasons.add("PIT_CORRECTNESS_FAILED")
    if item.liquidity < policy.minimum_liquidity:
        reasons.add("MINIMUM_LIQUIDITY_FAILED")
    if not item.trading_restrictions_satisfied:
        reasons.add("A_SHARE_TRADING_RESTRICTION_FAILED")
    return tuple(sorted(reasons))


def _factor_contributions(
    policy: CandidatePolicyDefinition,
    inputs: tuple[CandidatePolicyInput, ...],
    integrity: Mapping[str, tuple[str, ...]],
) -> dict[str, Mapping[str, Decimal]]:
    result: dict[str, dict[str, Decimal]] = {item.symbol: {} for item in inputs}
    for definition in policy.validated_factors:
        available = tuple(
            (item.symbol, value)
            for item in inputs
            if not integrity[item.symbol]
            and (value := item.factor_values.get(definition.factor_id)) is not None
        )
        percentiles = _percentiles(
            {symbol: value for symbol, value in available},
            higher=definition.direction == "HIGHER_IS_BETTER",
        )
        for symbol, percentile in percentiles.items():
            result[symbol][definition.factor_id] = percentile * definition.weight
    return {
        symbol: MappingProxyType(dict(sorted(values.items())))
        for symbol, values in result.items()
    }


def _context_adjustments(
    policy: CandidatePolicyDefinition, item: CandidatePolicyInput
) -> Mapping[str, Decimal]:
    values = {
        definition.context_id: value * definition.weight
        for definition in policy.context_adjustments
        if definition.mode == "SCORE_ADJUSTMENT"
        and (value := item.context_values.get(definition.context_id)) is not None
    }
    return MappingProxyType(dict(sorted(values.items())))


def _percentiles(values: Mapping[str, Decimal], *, higher: bool) -> dict[str, Decimal]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    result: dict[str, Decimal] = {}
    position = 0
    denominator = Decimal(max(1, len(ordered) - 1))
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        percentile = (Decimal(position) + Decimal(end - 1)) / Decimal("2") / denominator
        if not higher:
            percentile = Decimal("1") - percentile
        for symbol, _value in ordered[position:end]:
            result[symbol] = percentile
        position = end
    return result


def _input_groups(
    inputs: tuple[CandidatePolicyInput, ...],
) -> dict[date, tuple[CandidatePolicyInput, ...]]:
    groups: dict[date, list[CandidatePolicyInput]] = {}
    for item in inputs:
        groups.setdefault(item.session, []).append(item)
    return {
        session: tuple(sorted(values, key=lambda item: item.symbol))
        for session, values in sorted(groups.items())
    }


def _record_groups(
    records: tuple[CandidatePolicyRecord, ...],
) -> dict[date, tuple[CandidatePolicyRecord, ...]]:
    groups: dict[date, list[CandidatePolicyRecord]] = {}
    for item in records:
        groups.setdefault(item.session, []).append(item)
    return {
        session: tuple(sorted(values, key=lambda item: item.symbol))
        for session, values in sorted(groups.items())
    }


def _coverage(records: tuple[CandidatePolicyRecord, ...]) -> Decimal:
    usable = sum(
        item.hard_integrity_eligible and item.factor_available for item in records
    )
    return Decimal(usable) / Decimal(len(records))


def _rank_ic(
    records: tuple[CandidatePolicyRecord, ...],
    returns: Mapping[tuple[date, str], Decimal],
) -> Decimal | None:
    daily: list[Decimal] = []
    for session, values in _record_groups(records).items():
        estimable = tuple(item for item in values if item.final_score is not None)
        correlation = _correlation(
            tuple(item.final_score for item in estimable if item.final_score is not None),
            tuple(returns[(session, item.symbol)] for item in estimable),
        )
        if correlation is not None:
            daily.append(correlation)
    return _mean(tuple(daily))


def _selected_return(
    records: tuple[CandidatePolicyRecord, ...],
    returns: Mapping[tuple[date, str], Decimal],
) -> Decimal | None:
    daily = tuple(
        _mean(
            tuple(
                returns[(session, item.symbol)]
                for item in values
                if item.selection_status == "SELECTED"
            )
        )
        for session, values in _record_groups(records).items()
    )
    return _mean(tuple(item for item in daily if item is not None))


def _selected_sets(
    records: tuple[CandidatePolicyRecord, ...],
) -> dict[date, frozenset[str]]:
    return {
        session: frozenset(
            item.symbol for item in values if item.selection_status == "SELECTED"
        )
        for session, values in _record_groups(records).items()
    }


def _comparison_stability(
    records: tuple[CandidatePolicyRecord, ...],
    returns: Mapping[tuple[date, str], Decimal],
) -> str:
    sessions = tuple(_record_groups(records))
    if len(sessions) < 2:
        return "NOT_ESTIMABLE"
    midpoint = len(sessions) // 2
    first = _rank_ic(
        tuple(item for item in records if item.session in set(sessions[:midpoint])),
        returns,
    )
    second = _rank_ic(
        tuple(item for item in records if item.session in set(sessions[midpoint:])),
        returns,
    )
    if first is None or second is None:
        return "NOT_ESTIMABLE"
    return "STABLE" if first == 0 or second == 0 or (first > 0) == (second > 0) else "UNSTABLE"


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
        return covariance / Decimal(str(sqrt(float(variance_x * variance_y))))


def _mean(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _mapping_decimal(value: Mapping[str, Decimal]) -> Mapping[str, Decimal]:
    return MappingProxyType(dict(sorted(value.items())))


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "CandidatePolicyComparison",
    "CandidatePolicyDefinition",
    "CandidatePolicyEvaluation",
    "CandidatePolicyInput",
    "CandidatePolicyRecord",
    "CandidatePolicyRole",
    "ContextAdjustmentDefinition",
    "ValidatedFactorDefinition",
    "compare_candidate_policies",
    "evaluate_candidate_policy",
]
