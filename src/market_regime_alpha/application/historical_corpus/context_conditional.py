"""Context-conditional Alpha evaluation over canonical Research Panel projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
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
    FactorCrossSection,
    composite_percentile_scores,
    fractional_boundary_weights,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
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
    research_panel_references: tuple[ValidationArtifactReference, ...]
    factor_directions: tuple[tuple[str, str], ...]
    target_reference: ValidationArtifactReference
    top_k: int
    expected_population: int
    effect_threshold: Decimal
    alpha_evidence: HistoricalResearchEvidence
    schema_version: str = "alpha-context-definition/v1"

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("Context identity must be non-empty")
        expected_kind = (
            ContextKind.CROSS_SECTIONAL_CONTEXT
            if self.context_id.upper() == "LIQUIDITY"
            else ContextKind.SESSION_LEVEL_CONTEXT
            if self.context_id.upper()
            in {
                "CAPITAL",
                "CAPITAL_PUBLIC_PROXY",
                "MARKET_REGIME",
                "THEME",
                "VOLATILITY",
                "VOLATILITY_REGIME",
            }
            else None
        )
        if expected_kind is None or self.kind is not expected_kind:
            raise ValueError("current canonical Context owner role is fixed")
        if (
            not self.research_panel_references
            or self.research_panel_references
            != tuple(
                sorted(
                    set(self.research_panel_references),
                    key=lambda item: (
                        item.artifact_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            )
            or any(
                item.artifact_kind
                not in {"RESEARCH_PANEL", "HISTORICAL_RESEARCH_PANEL"}
                for item in self.research_panel_references
            )
        ):
            raise ValueError("Context definition requires a frozen Research Panel owner")
        if self.factor_directions != tuple(sorted(set(self.factor_directions))):
            raise ValueError("Context Alpha factors must be unique and sorted")
        if self.top_k <= 0 or self.expected_population <= 0:
            raise ValueError("Context frozen population dimensions must be positive")
        if not self.effect_threshold.is_finite() or self.effect_threshold <= 0:
            raise ValueError("Context effect threshold must be positive and finite")
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
        research_panel_references: tuple[ValidationArtifactReference, ...],
        top_k: int,
        expected_population: int,
        effect_threshold: Decimal,
        alpha_evidence: HistoricalResearchEvidence,
    ) -> ContextDefinition:
        factor_directions = tuple(
            sorted(
                (str(item[0]), str(item[1]))
                for item in alpha_evidence.payload.get("validated_factors", ())
                if isinstance(item, (list, tuple)) and len(item) == 2
            )
        )
        if not factor_directions:
            raise ValueError("Context definition requires externally validated Factors")
        experiment = alpha_evidence.payload.get("experiment")
        if not isinstance(experiment, Mapping):
            raise ValueError("Context definition requires frozen External Experiment")
        hypothesis = experiment.get("hypothesis")
        if not isinstance(hypothesis, Mapping):
            raise ValueError("Context definition lacks frozen Alpha hypothesis")
        raw_target = hypothesis.get("target_reference")
        if not isinstance(raw_target, Mapping):
            raise ValueError("Context definition lacks frozen Target owner")
        target_reference = ValidationArtifactReference.from_canonical_dict(raw_target)
        panels = tuple(
            sorted(
                research_panel_references,
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        payload = {
            "schema_version": "alpha-context-definition/v1",
            "context_id": context_id,
            "kind": kind.value,
            "role": role.value,
            "public_observable_proxy": public_observable_proxy,
            "research_panel_references": [
                item.to_canonical_dict() for item in panels
            ],
            "factor_directions": [list(item) for item in factor_directions],
            "target_reference": target_reference.to_canonical_dict(),
            "top_k": top_k,
            "expected_population": expected_population,
            "effect_threshold": str(effect_threshold),
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
            panels,
            factor_directions,
            target_reference,
            top_k,
            expected_population,
            effect_threshold,
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
            "research_panel_references": [
                item.to_canonical_dict() for item in self.research_panel_references
            ],
            "factor_directions": [list(item) for item in self.factor_directions],
            "target_reference": self.target_reference.to_canonical_dict(),
            "top_k": self.top_k,
            "expected_population": self.expected_population,
            "effect_threshold": str(self.effect_threshold),
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
    target_reference: ValidationArtifactReference

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
            "target_reference": self.target_reference.to_canonical_dict(),
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

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> ContextConditionalEvaluation:
        raw_slices = payload.get("slices")
        raw_limitations = payload.get("limitations")
        if not isinstance(raw_slices, list) or not isinstance(raw_limitations, list):
            raise ValueError("Context Conditional Evaluation payload is malformed")

        def optional_decimal(value: object) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        slices: list[ConditionalContextSlice] = []
        for item in raw_slices:
            if not isinstance(item, Mapping):
                raise ValueError("Context Conditional slice is malformed")
            slices.append(
                ConditionalContextSlice(
                    context_value=str(item["context_value"]),
                    sample_count=int(item["sample_count"]),
                    coverage=Decimal(str(item["coverage"])),
                    conditional_rank_ic=optional_decimal(
                        item["conditional_rank_ic"]
                    ),
                    conditional_top_k=optional_decimal(
                        item["conditional_top_k"]
                    ),
                    temporal_stability=str(item["temporal_stability"]),
                    confidence=str(item["confidence"]),
                )
            )
        return cls(
            evaluation_id=ArtifactId(str(payload["evaluation_id"])),
            evaluation_hash=str(payload["evaluation_hash"]),
            definition_reference=ValidationArtifactReference.from_canonical_dict(
                payload["definition_reference"]
            ),
            observation_set_hash=str(payload["observation_set_hash"]),
            sample_count=int(payload["sample_count"]),
            coverage=Decimal(str(payload["coverage"])),
            unconditional_rank_ic=optional_decimal(
                payload["unconditional_rank_ic"]
            ),
            slices=tuple(slices),
            interaction_effect=optional_decimal(payload["interaction_effect"]),
            incremental_information=optional_decimal(
                payload["incremental_information"]
            ),
            temporal_stability=str(payload["temporal_stability"]),
            confidence=str(payload["confidence"]),
            status=str(payload["status"]),
            limitations=tuple(str(item) for item in raw_limitations),
        )


def evaluate_context_conditioning(
    definition: ContextDefinition,
    *,
    observations: tuple[ContextObservation, ...],
) -> ContextConditionalEvaluation:
    ordered = tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("Context observations must be unique")
    if any(
        item.source_reference not in definition.research_panel_references
        or item.target_reference != definition.target_reference
        for item in ordered
    ):
        raise ValueError("Context observation is outside the frozen Research Panel owner")
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
        return _not_estimable(
            definition, ordered, expected_population=definition.expected_population
        )

    daily = _daily_rank_ic(ordered)
    unconditional = _mean(tuple(value for _session, value in daily))
    by_label: dict[str, list[ContextObservation]] = {}
    for item in ordered:
        by_label.setdefault(item.context_label, []).append(item)
    slices = tuple(
        _slice(
            label,
            tuple(values),
            total=definition.expected_population,
            top_k=definition.top_k,
        )
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
        threshold=definition.effect_threshold,
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
    coverage = Decimal(len(ordered)) / Decimal(definition.expected_population)
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


def project_context_observations(
    definition: ContextDefinition,
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[ContextObservation, ...]:
    """Derive Alpha and Context values from exact Research Panel owners."""

    by_reference = {panel.reference: panel for panel in panels}
    if set(by_reference) != set(definition.research_panel_references):
        raise ValueError("Context Research Panel owner set drifted")
    if len(by_reference) != len(panels) or any(
        panel.component_kind is not HistoricalComponentKind.RESEARCH_PANEL
        for panel in panels
    ):
        raise ValueError("Context requires unique canonical Research Panel owners")
    expected_role = (
        ContextKind.CROSS_SECTIONAL_CONTEXT
        if definition.context_id.upper() == "LIQUIDITY"
        else ContextKind.SESSION_LEVEL_CONTEXT
    )
    if definition.kind is not expected_role:
        raise ValueError(
            "current canonical Context owner role does not match the definition"
        )
    observations: list[ContextObservation] = []
    for panel in sorted(panels, key=lambda item: item.trading_date):
        rows = panel.payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Context Research Panel rows are unavailable")
        typed_rows = tuple(_panel_row(item) for item in rows)
        eligible = tuple(
            row
            for row in typed_rows
            if row.get("target_return") is not None
            and _context_factor_values(row, definition.factor_directions) is not None
        )
        if not eligible:
            continue
        symbols = tuple(str(row["symbol"]) for row in eligible)
        factor_values: dict[str, dict[str, Decimal]] = {}
        for row in eligible:
            values = _context_factor_values(row, definition.factor_directions)
            if values is None:  # guarded by the eligible projection above
                raise ValueError("Context factor projection changed during evaluation")
            factor_values[str(row["symbol"])] = values
        scores = composite_percentile_scores(
            tuple(
                FactorCrossSection(
                    factor_id,
                    {
                        symbol: factor_values[symbol][factor_id]
                        for symbol in symbols
                    },
                    direction == "HIGHER_IS_BETTER",
                    Decimal("1"),
                )
                for factor_id, direction in definition.factor_directions
            ),
            entities=symbols,
        ).scores
        for row in eligible:
            symbol = str(row["symbol"])
            label, value = _context_projection(definition.context_id, row)
            raw_target = row.get("target_reference")
            if not isinstance(raw_target, Mapping):
                raise ValueError("Context Research Panel Target owner is unavailable")
            target_reference = ValidationArtifactReference.from_canonical_dict(
                raw_target
            )
            if target_reference != definition.target_reference:
                raise ValueError("Context Research Panel Target owner drifted")
            observations.append(
                ContextObservation(
                    panel.trading_date,
                    symbol,
                    scores[symbol],
                    Decimal(str(row["target_return"])),
                    label,
                    value,
                    panel.reference,
                    target_reference,
                )
            )
    return tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))


def _panel_row(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Context Research Panel row is malformed")
    return value


def _context_factor_values(
    row: Mapping[str, Any],
    factor_directions: tuple[tuple[str, str], ...],
) -> dict[str, Decimal] | None:
    raw_features = row.get("research_features")
    if not isinstance(raw_features, list):
        raise ValueError("Context Research Panel Feature projection is malformed")
    values = {
        str(item.get("output_id")): Decimal(str(item["value"]))
        for item in raw_features
        if isinstance(item, Mapping)
        and item.get("state") == "AVAILABLE"
        and item.get("value") is not None
    }
    required = {factor_id for factor_id, _direction in factor_directions}
    return {factor_id: values[factor_id] for factor_id in required} if required.issubset(values) else None


def _context_projection(
    context_id: str,
    row: Mapping[str, Any],
) -> tuple[str, Decimal | None]:
    normalized = context_id.upper()
    if normalized == "MARKET_REGIME":
        return str(row.get("market_regime", "NOT_ESTIMABLE")), None
    if normalized == "THEME":
        return str(row.get("theme_owner_status", "NOT_ESTIMABLE")), None
    if normalized in {"CAPITAL", "CAPITAL_PUBLIC_PROXY"}:
        return str(row.get("capital_owner_status", "NOT_ESTIMABLE")), None
    if normalized in {"VOLATILITY", "VOLATILITY_REGIME"}:
        return str(row.get("volatility_bucket", "NOT_ESTIMABLE")), None
    if normalized == "LIQUIDITY":
        value = row.get("capacity_ceiling")
        return (
            str(row.get("liquidity_bucket", "NOT_ESTIMABLE")),
            None if value is None else Decimal(str(value)),
        )
    raise ValueError("unsupported canonical Context projection")


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
    threshold: Decimal,
) -> str:
    if stability == "UNSTABLE":
        return "UNSTABLE"
    if kind is ContextKind.CROSS_SECTIONAL_CONTEXT:
        if incremental is None:
            return "NOT_ESTIMABLE"
        if incremental > threshold:
            return "AMPLIFIER"
        if incremental < -threshold:
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
    if spread <= threshold:
        return "NEUTRAL"
    deltas = tuple(item - unconditional for item in estimates)
    if any(item > 0 for item in estimates) and any(item < 0 for item in estimates):
        return "UNSTABLE"
    if max(deltas) > threshold and min(deltas) >= -threshold:
        return "AMPLIFIER"
    if min(deltas) < -threshold and max(deltas) <= threshold:
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
    "project_context_observations",
]
