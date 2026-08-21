"""Context-conditional Alpha evaluation over canonical Research Panel projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from typing import Any

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
    fractional_boundary_weights,
)


class ContextKind(str, Enum):
    SESSION_LEVEL_CONTEXT = "SESSION_LEVEL_CONTEXT"
    CROSS_SECTIONAL_CONTEXT = "CROSS_SECTIONAL_CONTEXT"


class ContextResearchRole(str, Enum):
    CONDITIONAL_PERFORMANCE = "CONDITIONAL_PERFORMANCE"
    INTERACTION = "INTERACTION"


@dataclass(frozen=True, slots=True)
class ContextDefinition:
    definition_id: ArtifactId
    definition_hash: str
    context_id: str
    kind: ContextKind
    role: ContextResearchRole
    public_observable_proxy: bool
    alpha_evidence: HistoricalResearchEvidence
    schema_version: str = "alpha-context-definition/v1"

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("Context identity must be non-empty")
        if (
            self.kind is ContextKind.SESSION_LEVEL_CONTEXT
            and self.role is not ContextResearchRole.CONDITIONAL_PERFORMANCE
        ):
            raise ValueError("session Context can only own conditional performance")
        self.alpha_evidence.verify_identity()
        if (
            self.alpha_evidence.evidence_kind
            is not HistoricalEvidenceKind.EXTERNAL_VALIDATION
            or self.alpha_evidence.payload.get("qualification_status") != "SUPPORTED"
        ):
            raise ValueError("Context research requires supported External Validation Evidence")
        if canonical_hash(self.identity_payload()) != self.definition_hash:
            raise ValueError("Context definition hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        context_id: str,
        kind: ContextKind,
        role: ContextResearchRole,
        public_observable_proxy: bool,
        alpha_evidence: HistoricalResearchEvidence,
    ) -> ContextDefinition:
        payload = {
            "schema_version": "alpha-context-definition/v1",
            "context_id": context_id,
            "kind": kind.value,
            "role": role.value,
            "public_observable_proxy": public_observable_proxy,
            "alpha_evidence_reference": alpha_evidence.reference.to_canonical_dict(),
        }
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"alpha-context-definition:{digest[7:]}"),
            digest,
            context_id,
            kind,
            role,
            public_observable_proxy,
            alpha_evidence,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_CONTEXT_DEFINITION", self.definition_id, self.definition_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "kind": self.kind.value,
            "role": self.role.value,
            "public_observable_proxy": self.public_observable_proxy,
            "alpha_evidence_reference": self.alpha_evidence.reference.to_canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class ContextObservation:
    session: date
    symbol: str
    alpha_score: Decimal
    target_return: Decimal
    context_label: str
    context_value: Decimal | None
    source_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.context_label.strip():
            raise ValueError("Context observation identity is incomplete")
        if not self.alpha_score.is_finite() or not self.target_return.is_finite():
            raise ValueError("Context observation values must be finite")
        if self.context_value is not None and not self.context_value.is_finite():
            raise ValueError("Context value must be finite")
        if self.source_reference.artifact_kind not in {
            "RESEARCH_PANEL",
            "HISTORICAL_RESEARCH_PANEL",
        }:
            raise ValueError("Context observation requires Research Panel lineage")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.isoformat(),
            "symbol": self.symbol,
            "alpha_score": str(self.alpha_score),
            "target_return": str(self.target_return),
            "context_label": self.context_label,
            "context_value": (
                None if self.context_value is None else str(self.context_value)
            ),
            "source_reference": self.source_reference.to_canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class ConditionalContextSlice:
    context_value: str
    sample_count: int
    coverage: Decimal
    conditional_rank_ic: Decimal | None
    conditional_top_k: Decimal | None
    temporal_stability: str
    confidence: str


@dataclass(frozen=True, slots=True)
class ContextConditionalEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    definition_reference: ValidationArtifactReference
    observation_set_hash: str
    sample_count: int
    coverage: Decimal
    unconditional_rank_ic: Decimal | None
    slices: tuple[ConditionalContextSlice, ...]
    interaction_effect: Decimal | None
    incremental_information: Decimal | None
    temporal_stability: str
    confidence: str
    status: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("evaluation_hash", self.evaluation_hash)
        require_sha256("observation_set_hash", self.observation_set_hash)
        if self.sample_count < 0 or not Decimal("0") <= self.coverage <= Decimal("1"):
            raise ValueError("Context evaluation coverage is invalid")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Context evaluation limitations must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.evaluation_hash or self.evaluation_id != ArtifactId(
            f"context-conditional-evaluation:{digest[7:]}"
        ):
            raise ValueError("Context evaluation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "definition_reference": self.definition_reference.to_canonical_dict(),
            "observation_set_hash": self.observation_set_hash,
            "sample_count": self.sample_count,
            "coverage": str(self.coverage),
            "unconditional_rank_ic": _text(self.unconditional_rank_ic),
            "slices": [_slice_payload(item) for item in self.slices],
            "interaction_effect": _text(self.interaction_effect),
            "incremental_information": _text(self.incremental_information),
            "temporal_stability": self.temporal_stability,
            "confidence": self.confidence,
            "status": self.status,
            "limitations": list(self.limitations),
        }

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "CONTEXT_CONDITIONAL_EVALUATION",
            self.evaluation_id,
            self.evaluation_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": str(self.evaluation_id),
            "evaluation_hash": self.evaluation_hash,
            **self.identity_payload(),
        }


def evaluate_context_conditioning(
    definition: ContextDefinition,
    *,
    observations: tuple[ContextObservation, ...],
    top_k: int,
    expected_population: int,
) -> ContextConditionalEvaluation:
    if top_k <= 0 or expected_population <= 0:
        raise ValueError("Context Top-K must be positive")
    ordered = tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("Context observations must be unique")
    sessions = _groups(ordered)
    if definition.kind is ContextKind.SESSION_LEVEL_CONTEXT and any(
        len({item.context_label for item in values}) != 1
        for values in sessions.values()
    ):
        raise ValueError("session-level Context must be constant within each session")
    has_cross_sectional_variation = any(
        len({item.context_label for item in values}) > 1
        for values in sessions.values()
    )
    if (
        definition.kind is ContextKind.CROSS_SECTIONAL_CONTEXT
        and not has_cross_sectional_variation
    ):
        return _not_estimable(definition, ordered, expected_population=expected_population)

    daily = _daily_rank_ic(ordered)
    unconditional = _mean(tuple(value for _session, value in daily))
    by_label: dict[str, list[ContextObservation]] = {}
    for item in ordered:
        by_label.setdefault(item.context_label, []).append(item)
    slices = tuple(
        _slice(label, tuple(values), total=expected_population, top_k=top_k)
        for label, values in sorted(by_label.items())
    )

    interaction: Decimal | None = None
    incremental: Decimal | None = None
    if definition.kind is ContextKind.CROSS_SECTIONAL_CONTEXT:
        complete = tuple(item for item in ordered if item.context_value is not None)
        if len(complete) == len(ordered):
            interaction_daily: list[Decimal] = []
            for values in _groups(complete).values():
                correlation = _correlation(
                    _ranks(
                        tuple(
                            item.alpha_score * (item.context_value or Decimal("0"))
                            for item in values
                        )
                    ),
                    _ranks(tuple(item.target_return for item in values)),
                )
                if correlation is not None:
                    interaction_daily.append(correlation)
            interaction = _mean(tuple(interaction_daily))
            if interaction is not None and unconditional is not None:
                incremental = interaction - unconditional
    elif len(slices) >= 2:
        estimates = tuple(
            item.conditional_rank_ic
            for item in slices
            if item.conditional_rank_ic is not None
        )
        if len(estimates) >= 2:
            interaction = max(estimates) - min(estimates)

    stability = _stability(tuple(value for _session, value in daily))
    confidence = _confidence(len(daily), stability)
    status = _classify(
        definition.kind,
        slices=slices,
        incremental=incremental,
        unconditional=unconditional,
        stability=stability,
    )
    limitations = tuple(
        sorted(
            {
                "CONTEXT_HAS_NO_TRADING_AUTHORITY",
                "EXPLORATORY",
                "FORMAL_OOS_FALSE",
                *(
                    ("PUBLIC_PROXY_NOT_HIDDEN_INSTITUTIONAL_INTENT",)
                    if definition.public_observable_proxy
                    else ()
                ),
                *(
                    ("SESSION_CONTEXT_NOT_WITHIN_SESSION_GATE",)
                    if definition.kind is ContextKind.SESSION_LEVEL_CONTEXT
                    else ()
                ),
            }
        )
    )
    coverage = Decimal(len(ordered)) / Decimal(expected_population)
    if coverage > Decimal("1"):
        raise ValueError("Context observations exceed the frozen expected population")
    observation_set_hash = canonical_hash(
        {"observations": [item.to_canonical_dict() for item in ordered]}
    )
    payload = {
        "definition_reference": definition.reference.to_canonical_dict(),
        "observation_set_hash": observation_set_hash,
        "sample_count": len(ordered),
        "coverage": str(coverage),
        "unconditional_rank_ic": _text(unconditional),
        "slices": [_slice_payload(item) for item in slices],
        "interaction_effect": _text(interaction),
        "incremental_information": _text(incremental),
        "temporal_stability": stability,
        "confidence": confidence,
        "status": status,
        "limitations": list(limitations),
    }
    digest = canonical_hash(payload)
    return ContextConditionalEvaluation(
        ArtifactId(f"context-conditional-evaluation:{digest[7:]}"),
        digest,
        definition.reference,
        observation_set_hash,
        len(ordered),
        coverage,
        unconditional,
        slices,
        interaction,
        incremental,
        stability,
        confidence,
        status,
        limitations,
    )


def _not_estimable(
    definition: ContextDefinition,
    observations: tuple[ContextObservation, ...],
    *,
    expected_population: int,
) -> ContextConditionalEvaluation:
    limitations = (
        "CONTEXT_HAS_NO_TRADING_AUTHORITY",
        "FORMAL_OOS_FALSE",
        "WITHIN_SESSION_CONTEXT_VARIATION_REQUIRED",
    )
    coverage = Decimal(len(observations)) / Decimal(expected_population)
    if coverage > Decimal("1"):
        raise ValueError("Context observations exceed the frozen expected population")
    observation_set_hash = canonical_hash(
        {"observations": [item.to_canonical_dict() for item in observations]}
    )
    payload = {
        "definition_reference": definition.reference.to_canonical_dict(),
        "observation_set_hash": observation_set_hash,
        "sample_count": len(observations),
        "coverage": str(coverage),
        "unconditional_rank_ic": None,
        "slices": [],
        "interaction_effect": None,
        "incremental_information": None,
        "temporal_stability": "NOT_ESTIMABLE",
        "confidence": "NOT_ESTIMABLE",
        "status": "NOT_ESTIMABLE",
        "limitations": list(limitations),
    }
    digest = canonical_hash(payload)
    return ContextConditionalEvaluation(
        ArtifactId(f"context-conditional-evaluation:{digest[7:]}"),
        digest,
        definition.reference,
        observation_set_hash,
        len(observations),
        coverage,
        None,
        (),
        None,
        None,
        "NOT_ESTIMABLE",
        "NOT_ESTIMABLE",
        "NOT_ESTIMABLE",
        limitations,
    )


def _slice(
    label: str,
    observations: tuple[ContextObservation, ...],
    *,
    total: int,
    top_k: int,
) -> ConditionalContextSlice:
    daily = _daily_rank_ic(observations)
    values = tuple(value for _session, value in daily)
    top_returns: list[Decimal] = []
    for rows in _groups(observations).values():
        if not rows:
            continue
        selection = fractional_boundary_weights(
            {item.symbol: item.alpha_score for item in rows},
            slots=min(top_k, len(rows)),
            higher_is_better=True,
        )
        denominator = sum(selection.weights.values(), Decimal("0"))
        top_returns.append(
            sum(
                (
                    item.target_return * selection.weights[item.symbol]
                    for item in rows
                ),
                Decimal("0"),
            )
            / denominator
        )
    stability = _stability(values)
    return ConditionalContextSlice(
        label,
        len(observations),
        Decimal(len(observations)) / Decimal(total),
        _mean(values),
        _mean(tuple(top_returns)),
        stability,
        _confidence(len(daily), stability),
    )


def _classify(
    kind: ContextKind,
    *,
    slices: tuple[ConditionalContextSlice, ...],
    incremental: Decimal | None,
    unconditional: Decimal | None,
    stability: str,
) -> str:
    if stability == "UNSTABLE":
        return "UNSTABLE"
    if kind is ContextKind.CROSS_SECTIONAL_CONTEXT:
        if incremental is None:
            return "NOT_ESTIMABLE"
        if incremental > Decimal("0.02"):
            return "AMPLIFIER"
        if incremental < Decimal("-0.02"):
            return "SUPPRESSOR"
        return "NEUTRAL"
    estimates = tuple(
        item.conditional_rank_ic
        for item in slices
        if item.conditional_rank_ic is not None
    )
    if len(estimates) < 2 or unconditional is None:
        return "NOT_ESTIMABLE"
    spread = max(estimates) - min(estimates)
    if spread <= Decimal("0.02"):
        return "NEUTRAL"
    deltas = tuple(item - unconditional for item in estimates)
    if any(item > 0 for item in estimates) and any(item < 0 for item in estimates):
        return "UNSTABLE"
    if max(deltas) > Decimal("0.02") and min(deltas) >= Decimal("-0.02"):
        return "AMPLIFIER"
    if min(deltas) < Decimal("-0.02") and max(deltas) <= Decimal("0.02"):
        return "SUPPRESSOR"
    return "UNSTABLE"


def _groups(
    observations: tuple[ContextObservation, ...],
) -> dict[date, tuple[ContextObservation, ...]]:
    result: dict[date, list[ContextObservation]] = {}
    for item in observations:
        result.setdefault(item.session, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.symbol))
        for key, values in sorted(result.items())
    }


def _daily_rank_ic(
    observations: tuple[ContextObservation, ...],
) -> tuple[tuple[date, Decimal], ...]:
    result: list[tuple[date, Decimal]] = []
    for session, values in _groups(observations).items():
        value = _correlation(
            _ranks(tuple(item.alpha_score for item in values)),
            _ranks(tuple(item.target_return for item in values)),
        )
        if value is not None:
            result.append((session, value))
    return tuple(result)


def _stability(values: tuple[Decimal, ...]) -> str:
    if len(values) < 2:
        return "NOT_ESTIMABLE"
    midpoint = len(values) // 2
    first = _mean(values[:midpoint])
    second = _mean(values[midpoint:])
    assert first is not None and second is not None
    return "STABLE" if first == 0 or second == 0 or (first > 0) == (second > 0) else "UNSTABLE"


def _confidence(session_count: int, stability: str) -> str:
    if session_count < 2:
        return "NOT_ESTIMABLE"
    if session_count < 20:
        return "LOW"
    return "MEDIUM" if stability == "UNSTABLE" else "HIGH"


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


def _slice_payload(item: ConditionalContextSlice) -> dict[str, Any]:
    return {
        "context_value": item.context_value,
        "sample_count": item.sample_count,
        "coverage": str(item.coverage),
        "conditional_rank_ic": _text(item.conditional_rank_ic),
        "conditional_top_k": _text(item.conditional_top_k),
        "temporal_stability": item.temporal_stability,
        "confidence": item.confidence,
    }


__all__ = [
    "ConditionalContextSlice",
    "ContextConditionalEvaluation",
    "ContextDefinition",
    "ContextKind",
    "ContextObservation",
    "ContextResearchRole",
    "evaluate_context_conditioning",
]
