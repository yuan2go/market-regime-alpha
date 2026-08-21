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
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.research.cross_sectional_ranking import (
    competition_ranks,
    fractional_boundary_weights,
    rank_percentiles,
)


class CandidatePolicyRole(str, Enum):
    INCUMBENT = "INCUMBENT"
    CHALLENGER = "CHALLENGER"


@dataclass(frozen=True, slots=True)
class ValidatedFactorDefinition:
    factor_id: str
    direction: str
    weight: Decimal
    external_validation_evidence: HistoricalResearchEvidence

    def __post_init__(self) -> None:
        if not self.factor_id.strip() or self.direction not in {
            "HIGHER_IS_BETTER",
            "LOWER_IS_BETTER",
        }:
            raise ValueError("validated Candidate factor definition is invalid")
        if self.weight <= 0:
            raise ValueError("validated Candidate factor weight must be positive")
        self.external_validation_evidence.verify_identity()
        if (
            self.external_validation_evidence.evidence_kind
            is not HistoricalEvidenceKind.EXTERNAL_VALIDATION
            or self.external_validation_evidence.payload.get("qualification_status")
            != "SUPPORTED"
        ):
            raise ValueError("Candidate factor requires supported External Validation Evidence")
        validated = {
            (str(item[0]), str(item[1]))
            for item in self.external_validation_evidence.payload.get(
                "validated_factors", ()
            )
            if isinstance(item, (list, tuple)) and len(item) == 2
        }
        if (self.factor_id, self.direction) not in validated:
            raise ValueError("Candidate factor is outside External Validation Evidence")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "direction": self.direction,
            "weight": str(self.weight),
            "external_validation_evidence": self.external_validation_evidence.reference.to_canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class ContextAdjustmentDefinition:
    context_id: str
    weight: Decimal
    mode: str
    context_evidence: HistoricalResearchEvidence

    def __post_init__(self) -> None:
        if self.mode not in {
            "SCORE_ADJUSTMENT",
            "CONFIDENCE_ADJUSTMENT",
            "RISK_CONDITION",
        }:
            raise ValueError("unsupported Candidate Context adjustment")
        self.context_evidence.verify_identity()
        if (
            self.context_evidence.evidence_kind
            is not HistoricalEvidenceKind.CONTEXT_CONDITIONAL
            or self.evidence_status not in {"AMPLIFIER", "SUPPRESSOR"}
        ):
            raise ValueError("Candidate Context requires stable supporting evidence")
        if not self.weight.is_finite():
            raise ValueError("Candidate Context weight must be finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "weight": str(self.weight),
            "mode": self.mode,
            "context_evidence": self.context_evidence.reference.to_canonical_dict(),
            "evidence_status": self.evidence_status,
        }

    @property
    def evidence_status(self) -> str:
        return str(self.context_evidence.payload.get("status", "NOT_ESTIMABLE"))


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
    dataset_reference: ValidationArtifactReference
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
        dataset_reference: ValidationArtifactReference,
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
            "dataset_reference": dataset_reference.to_canonical_dict(),
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
            dataset_reference,
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
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
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
    incumbent_hard_integrity_eligible: bool
    incumbent_hard_gate_failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.liquidity.is_finite() or self.liquidity < 0:
            raise ValueError("Candidate Policy input identity/liquidity is invalid")
        for label, values in (
            ("Factor", self.factor_values.values()),
            ("Context", self.context_values.values()),
            ("incumbent contribution", self.incumbent_factor_contributions.values()),
        ):
            if any(value is not None and not value.is_finite() for value in values):
                raise ValueError(f"Candidate {label} value must be finite")
        if self.incumbent_score is not None and not self.incumbent_score.is_finite():
            raise ValueError("Candidate incumbent score must be finite")
        if self.incumbent_hard_gate_failure_reasons != tuple(
            sorted(set(self.incumbent_hard_gate_failure_reasons))
        ):
            raise ValueError("Candidate incumbent hard-gate reasons must be unique and sorted")
        if self.incumbent_hard_integrity_eligible == bool(
            self.incumbent_hard_gate_failure_reasons
        ):
            raise ValueError("Candidate incumbent integrity status/reasons disagree")
        if self.incumbent_selected and (
            not self.incumbent_hard_integrity_eligible or self.incumbent_score is None
        ):
            raise ValueError("Candidate incumbent selection requires eligible scored input")


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
    confidence_adjustments: Mapping[str, Decimal]
    risk_conditions: tuple[str, ...]
    final_score: Decimal | None
    rank: int | None
    selection_status: str
    selection_weight: Decimal
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not Decimal("0") <= self.selection_weight <= Decimal("1"):
            raise ValueError("Candidate record identity/selection weight is invalid")
        if self.rank is not None and self.rank <= 0:
            raise ValueError("Candidate rank must be positive")
        if self.selection_status == "SELECTED" and self.selection_weight <= 0:
            raise ValueError("selected Candidate requires positive selection weight")
        if self.selection_status != "SELECTED" and self.selection_weight != 0:
            raise ValueError("non-selected Candidate cannot carry selection weight")
        if self.hard_integrity_eligible == bool(self.hard_gate_failure_reasons):
            raise ValueError("Candidate record integrity status/reasons disagree")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Candidate reason codes must be unique and sorted")

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
            "confidence_adjustments": {
                key: str(value) for key, value in self.confidence_adjustments.items()
            },
            "risk_conditions": list(self.risk_conditions),
            "final_score": None if self.final_score is None else str(self.final_score),
            "rank": self.rank,
            "selection_status": self.selection_status,
            "selection_weight": str(self.selection_weight),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicyEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    policy_reference: ValidationArtifactReference
    dataset_reference: ValidationArtifactReference
    records: tuple[CandidatePolicyRecord, ...]

    def __post_init__(self) -> None:
        require_sha256("evaluation_hash", self.evaluation_hash)
        keys = tuple((item.session, item.symbol) for item in self.records)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Candidate evaluation records must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.evaluation_hash or self.evaluation_id != ArtifactId(
            f"candidate-policy-evaluation:{digest[7:]}"
        ):
            raise ValueError("Candidate Policy Evaluation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
            "records": [item.to_canonical_dict() for item in self.records],
        }

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CANDIDATE_POLICY_EVALUATION",
            self.evaluation_id,
            self.evaluation_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": str(self.evaluation_id),
            "evaluation_hash": self.evaluation_hash,
            **self.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class CandidatePolicyComparison:
    comparison_id: ArtifactId
    comparison_hash: str
    incumbent_reference: ValidationArtifactReference
    challenger_reference: ValidationArtifactReference
    dataset_reference: ValidationArtifactReference
    protocol_reference: ValidationArtifactReference
    realized_return_set_hash: str
    incumbent_coverage: Decimal
    challenger_coverage: Decimal
    incumbent_selection_count: int
    challenger_selection_count: int
    incumbent_rank_ic: Decimal | None
    challenger_rank_ic: Decimal | None
    incumbent_top_k: Decimal | None
    challenger_top_k: Decimal | None
    incumbent_net: Decimal | None
    challenger_net: Decimal | None
    incumbent_drawdown: Decimal | None
    challenger_drawdown: Decimal | None
    selection_turnover: Decimal | None
    stability: str

    def __post_init__(self) -> None:
        require_sha256("comparison_hash", self.comparison_hash)
        require_sha256("realized_return_set_hash", self.realized_return_set_hash)
        digest = canonical_hash(self.identity_payload())
        if digest != self.comparison_hash or self.comparison_id != ArtifactId(
            f"candidate-policy-comparison:{digest[7:]}"
        ):
            raise ValueError("Candidate Policy Comparison identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "incumbent_reference": self.incumbent_reference.to_canonical_dict(),
            "challenger_reference": self.challenger_reference.to_canonical_dict(),
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
            "comparison_protocol_reference": self.protocol_reference.to_canonical_dict(),
            "realized_return_set_hash": self.realized_return_set_hash,
            "incumbent_coverage": str(self.incumbent_coverage),
            "challenger_coverage": str(self.challenger_coverage),
            "incumbent_selection_count": self.incumbent_selection_count,
            "challenger_selection_count": self.challenger_selection_count,
            "incumbent_rank_ic": _text(self.incumbent_rank_ic),
            "challenger_rank_ic": _text(self.challenger_rank_ic),
            "incumbent_top_k": _text(self.incumbent_top_k),
            "challenger_top_k": _text(self.challenger_top_k),
            "incumbent_net": _text(self.incumbent_net),
            "challenger_net": _text(self.challenger_net),
            "incumbent_drawdown": _text(self.incumbent_drawdown),
            "challenger_drawdown": _text(self.challenger_drawdown),
            "selection_turnover": _text(self.selection_turnover),
            "stability": self.stability,
        }

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CANDIDATE_POLICY_COMPARISON",
            self.comparison_id,
            self.comparison_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": str(self.comparison_id),
            "comparison_hash": self.comparison_hash,
            **self.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class CandidateComparisonProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    dataset_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference
    cost_assumption: Decimal

    def __post_init__(self) -> None:
        require_sha256("protocol_hash", self.protocol_hash)
        if not Decimal("0") <= self.cost_assumption < Decimal("1"):
            raise ValueError("Candidate comparison cost is invalid")
        digest = canonical_hash(self.identity_payload())
        if digest != self.protocol_hash or self.protocol_id != ArtifactId(
            f"candidate-comparison-protocol:{digest[7:]}"
        ):
            raise ValueError("Candidate comparison protocol identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        dataset_reference: ValidationArtifactReference,
        target_reference: ValidationArtifactReference,
        cost_assumption: Decimal,
    ) -> CandidateComparisonProtocol:
        if not Decimal("0") <= cost_assumption < Decimal("1"):
            raise ValueError("Candidate comparison cost is invalid")
        payload = {
            "schema_version": "candidate-comparison-protocol/v1",
            "dataset_reference": dataset_reference.to_canonical_dict(),
            "target_reference": target_reference.to_canonical_dict(),
            "cost_assumption": str(cost_assumption),
        }
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"candidate-comparison-protocol:{digest[7:]}"),
            digest,
            dataset_reference,
            target_reference,
            cost_assumption,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CANDIDATE_COMPARISON_PROTOCOL", self.protocol_id, self.protocol_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "candidate-comparison-protocol/v1",
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
            "target_reference": self.target_reference.to_canonical_dict(),
            "cost_assumption": str(self.cost_assumption),
        }


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
        integrity = {
            item.symbol: (
                item.incumbent_hard_gate_failure_reasons
                if policy.role is CandidatePolicyRole.INCUMBENT
                else _hard_integrity(policy, item)
            )
            for item in session_inputs
        }
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
            hard_eligible = (
                item.incumbent_hard_integrity_eligible
                if policy.role is CandidatePolicyRole.INCUMBENT
                else not hard_reasons
            )
            if hard_eligible == bool(hard_reasons):
                raise ValueError("Candidate hard integrity status/reasons disagree")
            context: Mapping[str, Decimal]
            confidence: Mapping[str, Decimal]
            risk_conditions: tuple[str, ...]
            reasons: tuple[str, ...]
            if policy.role is CandidatePolicyRole.INCUMBENT:
                available = item.incumbent_score is not None
                factor_values = MappingProxyType(dict(sorted(item.factor_values.items())))
                alpha_score = item.incumbent_score if hard_eligible else None
                context = MappingProxyType({})
                confidence = MappingProxyType({})
                risk_conditions = ()
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
                context, confidence, risk_conditions = (
                    _context_conditioning(policy, item)
                    if alpha_score is not None
                    else (MappingProxyType({}), MappingProxyType({}), ())
                )
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
                        session=session,
                        symbol=item.symbol,
                        hard_integrity_eligible=hard_eligible,
                        hard_gate_failure_reasons=hard_reasons,
                        factor_available=available,
                        factor_values=factor_values,
                        factor_contributions=(
                            contributions[item.symbol]
                            if alpha_score is not None
                            else MappingProxyType({})
                        ),
                        alpha_score=alpha_score,
                        context_adjustments=context,
                        confidence_adjustments=confidence,
                        risk_conditions=risk_conditions,
                        final_score=final,
                        rank=None,
                        selection_status=status,
                        selection_weight=(
                            Decimal("1")
                            if policy.role is CandidatePolicyRole.INCUMBENT
                            and item.incumbent_selected
                            else Decimal("0")
                        ),
                        reason_codes=tuple(sorted({*hard_reasons, *reasons})),
                    ),
                )
            )
        score_by_symbol = {
            record.symbol: record.final_score
            for _item, record in provisional
            if record.final_score is not None
        }
        typed_scores = {
            symbol: score
            for symbol, score in score_by_symbol.items()
            if score is not None
        }
        ranks = competition_ranks(typed_scores, higher_is_better=True)
        boundary = (
            fractional_boundary_weights(
                typed_scores,
                slots=min(policy.top_k, len(typed_scores)),
                higher_is_better=True,
            )
            if typed_scores and policy.role is CandidatePolicyRole.CHALLENGER
            else None
        )
        for item, record in provisional:
            rank = ranks.get(record.symbol)
            selection_weight = (
                record.selection_weight
                if policy.role is CandidatePolicyRole.INCUMBENT
                else Decimal("0")
                if boundary is None
                else boundary.weights.get(record.symbol, Decimal("0"))
            )
            selected = selection_weight > 0
            reason_codes = set(record.reason_codes)
            if Decimal("0") < selection_weight < Decimal("1"):
                reason_codes.add("TOP_K_BOUNDARY_FRACTIONAL_EXPOSURE")
            records.append(
                CandidatePolicyRecord(
                    session=record.session,
                    symbol=record.symbol,
                    hard_integrity_eligible=record.hard_integrity_eligible,
                    hard_gate_failure_reasons=record.hard_gate_failure_reasons,
                    factor_available=record.factor_available,
                    factor_values=record.factor_values,
                    factor_contributions=record.factor_contributions,
                    alpha_score=record.alpha_score,
                    context_adjustments=record.context_adjustments,
                    confidence_adjustments=record.confidence_adjustments,
                    risk_conditions=record.risk_conditions,
                    final_score=record.final_score,
                    rank=rank,
                    selection_status=(
                        "SELECTED" if selected else record.selection_status
                    ),
                    selection_weight=selection_weight,
                    reason_codes=tuple(sorted(reason_codes)),
                )
            )
    result = tuple(sorted(records, key=lambda item: (item.session, item.symbol)))
    payload = {
        "policy_reference": policy.reference.to_canonical_dict(),
        "dataset_reference": policy.dataset_reference.to_canonical_dict(),
        "records": [item.to_canonical_dict() for item in result],
    }
    digest = canonical_hash(payload)
    return CandidatePolicyEvaluation(
        ArtifactId(f"candidate-policy-evaluation:{digest[7:]}"),
        digest,
        policy.reference,
        policy.dataset_reference,
        result,
    )


def compare_candidate_policies(
    incumbent: CandidatePolicyEvaluation,
    challenger: CandidatePolicyEvaluation,
    *,
    protocol: CandidateComparisonProtocol,
    realized_returns: Mapping[tuple[date, str], Decimal],
) -> CandidatePolicyComparison:
    if incumbent.policy_reference.artifact_kind != "INCUMBENT_CANDIDATE_POLICY":
        raise ValueError("Candidate comparison requires incumbent first")
    if challenger.policy_reference.artifact_kind != "CHALLENGER_CANDIDATE_POLICY":
        raise ValueError("Candidate comparison requires challenger second")
    if (
        incumbent.dataset_reference != protocol.dataset_reference
        or challenger.dataset_reference != protocol.dataset_reference
    ):
        raise ValueError("Candidate comparison requires one frozen dataset owner")
    incumbent_keys = {(item.session, item.symbol) for item in incumbent.records}
    challenger_keys = {(item.session, item.symbol) for item in challenger.records}
    if incumbent_keys != challenger_keys or not incumbent_keys:
        raise ValueError("Candidate comparison requires the same frozen dataset")
    if set(realized_returns) != incumbent_keys:
        raise ValueError("Candidate comparison target population drifted")
    if any(not value.is_finite() for value in realized_returns.values()):
        raise ValueError("Candidate comparison realized returns must be finite")
    realized_return_set_hash = canonical_hash(
        {
            "realized_returns": [
                {
                    "session": session.isoformat(),
                    "symbol": symbol,
                    "return": str(realized_returns[(session, symbol)]),
                }
                for session, symbol in sorted(incumbent_keys)
            ]
        }
    )
    incumbent_coverage = _coverage(incumbent.records)
    challenger_coverage = _coverage(challenger.records)
    incumbent_ic = _rank_ic(incumbent.records, realized_returns)
    challenger_ic = _rank_ic(challenger.records, realized_returns)
    incumbent_top = _selected_return(incumbent.records, realized_returns)
    challenger_top = _selected_return(challenger.records, realized_returns)
    incumbent_selected = _selected_weights(incumbent.records)
    challenger_selected = _selected_weights(challenger.records)
    shared_sessions = tuple(sorted(incumbent_selected.keys() & challenger_selected.keys()))
    turnover_values = tuple(
        sum(
            (
                abs(
                    incumbent_selected[session].get(symbol, Decimal("0"))
                    - challenger_selected[session].get(symbol, Decimal("0"))
                )
                for symbol in (
                    incumbent_selected[session].keys()
                    | challenger_selected[session].keys()
                )
            ),
            Decimal("0"),
        )
        / Decimal("2")
        for session in shared_sessions
    )
    incumbent_daily = _selected_daily_returns(incumbent.records, realized_returns)
    challenger_daily = _selected_daily_returns(challenger.records, realized_returns)
    incumbent_net = (
        None if incumbent_top is None else incumbent_top - protocol.cost_assumption
    )
    challenger_net = (
        None if challenger_top is None else challenger_top - protocol.cost_assumption
    )
    incumbent_drawdown = _drawdown(
        tuple(item - protocol.cost_assumption for item in incumbent_daily)
    )
    challenger_drawdown = _drawdown(
        tuple(item - protocol.cost_assumption for item in challenger_daily)
    )
    stability = _comparison_stability(challenger.records, realized_returns)
    values = {
        "incumbent_reference": incumbent.policy_reference.to_canonical_dict(),
        "challenger_reference": challenger.policy_reference.to_canonical_dict(),
        "dataset_reference": protocol.dataset_reference.to_canonical_dict(),
        "comparison_protocol_reference": protocol.reference.to_canonical_dict(),
        "realized_return_set_hash": realized_return_set_hash,
        "incumbent_coverage": str(incumbent_coverage),
        "challenger_coverage": str(challenger_coverage),
        "incumbent_selection_count": sum(item.selection_status == "SELECTED" for item in incumbent.records),
        "challenger_selection_count": sum(item.selection_status == "SELECTED" for item in challenger.records),
        "incumbent_rank_ic": _text(incumbent_ic),
        "challenger_rank_ic": _text(challenger_ic),
        "incumbent_top_k": _text(incumbent_top),
        "challenger_top_k": _text(challenger_top),
        "incumbent_net": _text(incumbent_net),
        "challenger_net": _text(challenger_net),
        "incumbent_drawdown": _text(incumbent_drawdown),
        "challenger_drawdown": _text(challenger_drawdown),
        "selection_turnover": _text(_mean(turnover_values)),
        "stability": stability,
    }
    digest = canonical_hash(values)
    return CandidatePolicyComparison(
        ArtifactId(f"candidate-policy-comparison:{digest[7:]}"),
        digest,
        incumbent.policy_reference,
        challenger.policy_reference,
        protocol.dataset_reference,
        protocol.reference,
        realized_return_set_hash,
        incumbent_coverage,
        challenger_coverage,
        sum(item.selection_status == "SELECTED" for item in incumbent.records),
        sum(item.selection_status == "SELECTED" for item in challenger.records),
        incumbent_ic,
        challenger_ic,
        incumbent_top,
        challenger_top,
        incumbent_net,
        challenger_net,
        incumbent_drawdown,
        challenger_drawdown,
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


def _context_conditioning(
    policy: CandidatePolicyDefinition, item: CandidatePolicyInput
) -> tuple[Mapping[str, Decimal], Mapping[str, Decimal], tuple[str, ...]]:
    score_values = {
        definition.context_id: value * definition.weight
        for definition in policy.context_adjustments
        if definition.mode == "SCORE_ADJUSTMENT"
        and (value := item.context_values.get(definition.context_id)) is not None
    }
    confidence_values = {
        definition.context_id: value * definition.weight
        for definition in policy.context_adjustments
        if definition.mode == "CONFIDENCE_ADJUSTMENT"
        and (value := item.context_values.get(definition.context_id)) is not None
    }
    risk_conditions = tuple(
        sorted(
            f"{definition.context_id}:{value * definition.weight}"
            for definition in policy.context_adjustments
            if definition.mode == "RISK_CONDITION"
            and (value := item.context_values.get(definition.context_id)) is not None
        )
    )
    return (
        MappingProxyType(dict(sorted(score_values.items()))),
        MappingProxyType(dict(sorted(confidence_values.items()))),
        risk_conditions,
    )


def _percentiles(values: Mapping[str, Decimal], *, higher: bool) -> dict[str, Decimal]:
    return dict(
        rank_percentiles(values, higher_is_better=higher).percentiles
    )


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
    return _mean(_selected_daily_returns(records, returns))


def _selected_daily_returns(
    records: tuple[CandidatePolicyRecord, ...],
    returns: Mapping[tuple[date, str], Decimal],
) -> tuple[Decimal, ...]:
    daily: list[Decimal] = []
    for session, values in _record_groups(records).items():
        selected = tuple(item for item in values if item.selection_weight > 0)
        denominator = sum(
            (item.selection_weight for item in selected), Decimal("0")
        )
        if denominator > 0:
            daily.append(
                sum(
                    (
                        returns[(session, item.symbol)] * item.selection_weight
                        for item in selected
                    ),
                    Decimal("0"),
                )
                / denominator
            )
    return tuple(daily)


def _selected_weights(
    records: tuple[CandidatePolicyRecord, ...],
) -> dict[date, Mapping[str, Decimal]]:
    return {
        session: {
            item.symbol: item.selection_weight
            for item in values
            if item.selection_weight > 0
        }
        for session, values in _record_groups(records).items()
    }


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
    "CandidateComparisonProtocol",
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
