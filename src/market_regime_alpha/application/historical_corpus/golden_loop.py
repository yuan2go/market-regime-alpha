"""Frozen V2 Golden Loop research-correctness identities."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_validation.ablation import (
    AblationVariant,
    AblationVariantKind,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    composite_percentile_scores,
    fractional_boundary_weights,
    rank_percentiles,
)


GOLDEN_LOOP_SCORING_CONTRACT = (
    "WITHIN_SESSION_TIE_AWARE_EXACT_RATIONAL_FACTOR_PERCENTILE_MEAN_V2"
)
GOLDEN_LOOP_SELECTION_POLICY = "FRACTIONAL_BOUNDARY_WEIGHT_V1"
GOLDEN_LOOP_MISSING_POLICY = "FIXED_DENOMINATOR_NEUTRAL_0_5_V1"
GOLDEN_LOOP_TIE_POLICY = "ARITHMETIC_MIDRANK_V1"
GOLDEN_LOOP_CONSTANT_POLICY = "NEUTRAL_0_5_NO_RANKING_INFORMATION_V1"
GOLDEN_LOOP_TOP_K = 10

_SEQUENCE = (
    AblationVariantKind.PRICE_ONLY,
    AblationVariantKind.PRICE_VOLUME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME,
    AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL,
    AblationVariantKind.THROUGH_DYNAMIC_POOL,
    AblationVariantKind.THROUGH_CANDIDATE_RANKING,
    AblationVariantKind.THROUGH_SIGNAL,
    AblationVariantKind.THROUGH_FORECAST,
)
_FACTOR_MAP = {
    "price": FactorFamily.PRICE,
    "volume": FactorFamily.VOLUME,
    "market_regime": FactorFamily.MARKET_REGIME,
    "etf": FactorFamily.ETF,
    "theme": FactorFamily.THEME,
    "capital": FactorFamily.CAPITAL,
    "dynamic_pool": FactorFamily.DYNAMIC_POOL,
    "candidate": FactorFamily.CANDIDATE,
    "signal": FactorFamily.SIGNAL,
    "forecast": FactorFamily.FORECAST,
}


@dataclass(frozen=True, slots=True)
class GoldenLoopScoringContract:
    """Content-addressed freeze of V2 ranking and selection correctness."""

    contract_id: ArtifactId
    contract_hash: str
    scoring_contract: str
    selection_policy: str
    missing_policy: str
    tie_policy: str
    constant_policy: str
    top_k: int
    schema_version: str = "golden-loop-scoring-contract/v1"

    def __post_init__(self) -> None:
        require_sha256("contract_hash", self.contract_hash)
        for label in (
            "scoring_contract",
            "selection_policy",
            "missing_policy",
            "tie_policy",
            "constant_policy",
        ):
            require_text(label, str(getattr(self, label)))
        if self.schema_version != "golden-loop-scoring-contract/v1":
            raise ValueError("unsupported Golden Loop scoring contract schema")
        if self.top_k != GOLDEN_LOOP_TOP_K:
            raise ValueError("Golden Loop V2 top-k policy drifted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.contract_hash:
            raise ValueError("Golden Loop scoring contract hash mismatch")
        if self.contract_id != ArtifactId(f"golden-loop-scoring-contract:{digest[7:]}"):
            raise ValueError("Golden Loop scoring contract identifier mismatch")

    @classmethod
    def create_v2(cls) -> GoldenLoopScoringContract:
        values = {
            "scoring_contract": GOLDEN_LOOP_SCORING_CONTRACT,
            "selection_policy": GOLDEN_LOOP_SELECTION_POLICY,
            "missing_policy": GOLDEN_LOOP_MISSING_POLICY,
            "tie_policy": GOLDEN_LOOP_TIE_POLICY,
            "constant_policy": GOLDEN_LOOP_CONSTANT_POLICY,
            "top_k": GOLDEN_LOOP_TOP_K,
            "schema_version": "golden-loop-scoring-contract/v1",
        }
        digest = canonical_hash(values)
        return cls(
            contract_id=ArtifactId(f"golden-loop-scoring-contract:{digest[7:]}"),
            contract_hash=digest,
            **values,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "GOLDEN_LOOP_SCORING_CONTRACT",
            self.contract_id,
            self.contract_hash,
        )

    def identity_payload(self) -> dict[str, str | int]:
        return {
            "scoring_contract": self.scoring_contract,
            "selection_policy": self.selection_policy,
            "missing_policy": self.missing_policy,
            "tie_policy": self.tie_policy,
            "constant_policy": self.constant_policy,
            "top_k": self.top_k,
            "schema_version": self.schema_version,
        }

    def to_canonical_dict(self) -> dict[str, str | int]:
        return {
            "contract_id": str(self.contract_id),
            "contract_hash": self.contract_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> GoldenLoopScoringContract:
        return cls(
            contract_id=ArtifactId(str(payload["contract_id"])),
            contract_hash=str(payload["contract_hash"]),
            scoring_contract=str(payload["scoring_contract"]),
            selection_policy=str(payload["selection_policy"]),
            missing_policy=str(payload["missing_policy"]),
            tie_policy=str(payload["tie_policy"]),
            constant_policy=str(payload["constant_policy"]),
            top_k=int(payload["top_k"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class GoldenLoopSessionEvaluation:
    """Typed payload persisted by the canonical historical Runtime."""

    scoring_contract: GoldenLoopScoringContract
    source_references: tuple[ValidationArtifactReference, ...]
    portfolio_status: str
    portfolio_line_count: int
    target_observation_count: int
    missing_target_count: int
    layer_diagnostics: Mapping[str, Mapping[str, Any]]
    variants: tuple[Mapping[str, Any], ...]
    schema_version: str = "golden-loop-session-evaluation/v1"

    def __post_init__(self) -> None:
        required = {
            "HISTORICAL_RESEARCH_PANEL",
            "HISTORICAL_OUTCOME",
            "MULTI_STRATEGY_CYCLE",
            "CROSS_STRATEGY_PORTFOLIO",
            "RESEARCH_EXPERIMENT_DEFINITION",
            "GOLDEN_LOOP_SCORING_CONTRACT",
        }
        kinds = {item.artifact_kind for item in self.source_references}
        if not required.issubset(kinds):
            raise ValueError("Golden Loop evaluation omits a canonical source owner")
        if self.source_references != _references(self.source_references):
            raise ValueError("Golden Loop evaluation sources must be unique and sorted")
        require_text("portfolio_status", self.portfolio_status)
        if min(
            self.portfolio_line_count,
            self.target_observation_count,
            self.missing_target_count,
        ) < 0:
            raise ValueError("Golden Loop evaluation counts must be non-negative")
        if tuple(item.get("variant_id") for item in self.variants) != tuple(
            item.value.lower() for item in _SEQUENCE
        ):
            raise ValueError("Golden Loop evaluation variant sequence drifted")
        if self.schema_version != "golden-loop-session-evaluation/v1":
            raise ValueError("unsupported Golden Loop session evaluation schema")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scoring_contract": self.scoring_contract.to_canonical_dict(),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "portfolio_status": self.portfolio_status,
            "portfolio_line_count": self.portfolio_line_count,
            "target_observation_count": self.target_observation_count,
            "missing_target_count": self.missing_target_count,
            "layer_diagnostics": {
                key: dict(value) for key, value in sorted(self.layer_diagnostics.items())
            },
            "variants": [dict(item) for item in self.variants],
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> GoldenLoopSessionEvaluation:
        diagnostics = _mapping(payload["layer_diagnostics"], "layer diagnostics")
        variants = _object_tuple(payload["variants"], "variant evaluations")
        return cls(
            scoring_contract=GoldenLoopScoringContract.from_canonical_dict(
                _mapping(payload["scoring_contract"], "scoring contract")
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(item)
                for item in _object_tuple(payload["source_references"], "source references")
            ),
            portfolio_status=str(payload["portfolio_status"]),
            portfolio_line_count=int(payload["portfolio_line_count"]),
            target_observation_count=int(payload["target_observation_count"]),
            missing_target_count=int(payload["missing_target_count"]),
            layer_diagnostics=MappingProxyType(
                {
                    str(key): MappingProxyType(dict(_mapping(value, str(key))))
                    for key, value in diagnostics.items()
                }
            ),
            variants=tuple(MappingProxyType(dict(item)) for item in variants),
            schema_version=str(payload["schema_version"]),
        )


def evaluate_golden_loop_session(
    *,
    panel: HistoricalSessionComponent,
    outcome: HistoricalSessionComponent,
    experiment_reference: ValidationArtifactReference,
    cycle_reference: ValidationArtifactReference,
    portfolio_reference: ValidationArtifactReference,
    portfolio_status: str,
    portfolio_line_count: int,
    attribution_references: tuple[ValidationArtifactReference, ...] = (),
    additional_source_references: tuple[ValidationArtifactReference, ...] = (),
    scoring_contract: GoldenLoopScoringContract | None = None,
) -> GoldenLoopSessionEvaluation:
    """Score one owner-resolved session without creating Strategy or Portfolio."""

    if panel.component_kind is not HistoricalComponentKind.RESEARCH_PANEL:
        raise ValueError("Golden Loop evaluation requires a Research Panel owner")
    if outcome.component_kind is not HistoricalComponentKind.OUTCOME:
        raise ValueError("Golden Loop evaluation requires an Outcome owner")
    if (panel.run_id, panel.session_id, panel.trading_date) != (
        outcome.run_id,
        outcome.session_id,
        outcome.trading_date,
    ):
        raise ValueError("Golden Loop Panel and Outcome owners must identify one session")
    for reference, expected in (
        (experiment_reference, "RESEARCH_EXPERIMENT_DEFINITION"),
        (cycle_reference, "MULTI_STRATEGY_CYCLE"),
        (portfolio_reference, "CROSS_STRATEGY_PORTFOLIO"),
    ):
        if reference.artifact_kind != expected:
            raise ValueError(f"Golden Loop evaluation requires {expected}")
    contract = scoring_contract or GoldenLoopScoringContract.create_v2()
    rows = _object_tuple(panel.payload.get("rows"), "Research Panel rows")
    observed_rows = tuple(
        (row, realized)
        for row in rows
        if (realized := _optional_decimal(row.get("target_return"))) is not None
    )
    if not observed_rows:
        raise ValueError("Golden Loop evaluation has no estimable Target observations")
    observation_ids = tuple(
        f"{panel.component_id}:{str(row['symbol'])}:t-plus-one-1030"
        for row, _realized in observed_rows
    )
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("Golden Loop session symbols must be unique")
    rows_by_id = {
        observation_id: row
        for observation_id, (row, _realized) in zip(
            observation_ids,
            observed_rows,
            strict=True,
        )
    }
    returns_by_id = {
        observation_id: realized
        for observation_id, (_row, realized) in zip(
            observation_ids,
            observed_rows,
            strict=True,
        )
    }
    factor_values: dict[str, dict[str, Decimal | None]] = {
        name: {} for name in _FACTOR_MAP
    }
    for observation_id, row in rows_by_id.items():
        raw_factors = _mapping(row.get("factor_values"), "factor values")
        for name in _FACTOR_MAP:
            factor_values[name][observation_id] = _optional_decimal(
                raw_factors.get(name)
            )
    layer_diagnostics: dict[str, Mapping[str, Any]] = {}
    for name, values in factor_values.items():
        ranked = rank_percentiles(
            {key: value for key, value in values.items() if value is not None},
            higher_is_better=True,
        )
        layer_diagnostics[name] = MappingProxyType(
            {
                "status": ranked.status.value,
                "observed_count": ranked.observed_count,
                "missing_count": len(observation_ids) - ranked.observed_count,
                "distinct_count": ranked.distinct_count,
            }
        )
    variants: list[Mapping[str, Any]] = []
    for kind in _SEQUENCE:
        variant = AblationVariant.standard(kind)
        included = tuple(
            name
            for name, family in _FACTOR_MAP.items()
            if variant.includes(family, name)
        )
        factors = tuple(
            FactorCrossSection(
                factor_id=name,
                values=factor_values[name],
                higher_is_better=True,
                weight=Decimal("1"),
            )
            for name in included
        )
        result = composite_percentile_scores(factors, entities=observation_ids)
        top = fractional_boundary_weights(
            result.scores,
            slots=contract.top_k,
            higher_is_better=True,
        )
        bottom_candidates = {
            key: score
            for key, score in result.scores.items()
            if top.weights[key] == 0
        }
        bottom = fractional_boundary_weights(
            bottom_candidates,
            slots=contract.top_k,
            higher_is_better=False,
        )
        evaluated_rows = tuple(
            {
                "observation_id": observation_id,
                "symbol": str(rows_by_id[observation_id]["symbol"]),
                "score": str(result.scores[observation_id]),
                "realized_return": str(returns_by_id[observation_id]),
                "cost_return": str(
                    _optional_decimal(rows_by_id[observation_id].get("cost_return"))
                    or Decimal("0.0021")
                ),
                "mfe": _decimal_text(
                    _optional_decimal(rows_by_id[observation_id].get("mfe"))
                ),
                "mae": _decimal_text(
                    _optional_decimal(rows_by_id[observation_id].get("mae"))
                ),
                "top_weight": str(top.weights[observation_id]),
                "bottom_weight": str(
                    bottom.weights.get(observation_id, Decimal("0"))
                ),
                "selected": bool(rows_by_id[observation_id].get("selected")),
                "slices": _slice_payload(rows_by_id[observation_id], panel),
            }
            for observation_id in observation_ids
        )
        variants.append(
            MappingProxyType(
                {
                    "variant_id": variant.variant_id,
                    "included_factors": list(included),
                    "top_boundary": _boundary_payload(top),
                    "bottom_boundary": _boundary_payload(bottom),
                    "rows": list(evaluated_rows),
                }
            )
        )
    sources = _references(
        (
            panel.reference,
            outcome.reference,
            experiment_reference,
            cycle_reference,
            portfolio_reference,
            contract.reference,
            *attribution_references,
            *additional_source_references,
        )
    )
    return GoldenLoopSessionEvaluation(
        scoring_contract=contract,
        source_references=sources,
        portfolio_status=portfolio_status,
        portfolio_line_count=portfolio_line_count,
        target_observation_count=len(observed_rows),
        missing_target_count=len(rows) - len(observed_rows),
        layer_diagnostics=MappingProxyType(layer_diagnostics),
        variants=tuple(variants),
    )


def _boundary_payload(value: Any) -> dict[str, Any]:
    return {
        "boundary_score": _decimal_text(value.boundary_score),
        "strict_count": value.strict_count,
        "boundary_group_size": value.boundary_group_size,
        "boundary_weight": str(value.boundary_weight),
    }


def _slice_payload(
    row: Mapping[str, Any],
    panel: HistoricalSessionComponent,
) -> dict[str, str]:
    quarter = ((panel.trading_date.month - 1) // 3) + 1
    return {
        "industry": str(row.get("industry", "NOT_ESTIMABLE")),
        "liquidity": str(row.get("liquidity_bucket", "NOT_ESTIMABLE")),
        "market_cap": str(row.get("market_cap_bucket", "NOT_ESTIMABLE")),
        "market_regime": str(row.get("market_regime", "NOT_ESTIMABLE")),
        "month": panel.trading_date.strftime("%Y-%m"),
        "quarter": f"{panel.trading_date.year}-Q{quarter}",
        "theme": str(row.get("theme", "NOT_ESTIMABLE")),
        "volatility": str(row.get("volatility_bucket", "NOT_ESTIMABLE")),
        "year": str(panel.trading_date.year),
    }


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Golden Loop numeric input must be finite")
    return result


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Golden Loop {label} must be an object")
    return value


def _object_tuple(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"Golden Loop {label} must be an object array")
    return tuple(value)


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in values
    }
    return tuple(keyed[key] for key in sorted(keyed))


__all__ = [
    "GOLDEN_LOOP_CONSTANT_POLICY",
    "GOLDEN_LOOP_MISSING_POLICY",
    "GOLDEN_LOOP_SCORING_CONTRACT",
    "GOLDEN_LOOP_SELECTION_POLICY",
    "GOLDEN_LOOP_TIE_POLICY",
    "GOLDEN_LOOP_TOP_K",
    "GoldenLoopScoringContract",
    "GoldenLoopSessionEvaluation",
    "evaluate_golden_loop_session",
]
