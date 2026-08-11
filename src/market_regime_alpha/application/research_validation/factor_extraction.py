"""Canonical-source factor extraction and Research Panel enrichment.

The extractor only copies already materialized owner values.  It never computes
an alternative technical factor from market bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping
from pathlib import Path

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json, require_sha256, require_text
from market_regime_alpha.application.canonical_lifecycle._immutable_io import publish_immutable_text
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.forecasting.contracts import PathForecast
from market_regime_alpha.market_data import Timeframe, VerifiedMarketDataDataset
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.signals.v3 import SignalRunArtifactV3
from market_regime_alpha.signals.research_semantics import (
    project_signal_research_measures,
)


class FactorFamily(str, Enum):
    PRICE = "PRICE"
    PRICE_ACTION = "PRICE_ACTION"
    VOLUME = "VOLUME"
    AMOUNT = "AMOUNT"
    MA_EMA = "MA_EMA"
    MACD = "MACD"
    VWAP = "VWAP"
    VOLATILITY = "VOLATILITY"
    MOMENTUM_TREND = "MOMENTUM_TREND"
    LIQUIDITY = "LIQUIDITY"
    MARKET_REGIME = "MARKET_REGIME"
    ETF = "ETF"
    THEME = "THEME"
    CAPITAL = "CAPITAL"
    DYNAMIC_POOL = "DYNAMIC_POOL"
    CANDIDATE = "CANDIDATE"
    INTRADAY = "INTRADAY"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"


@dataclass(frozen=True, slots=True)
class CanonicalStateFactorSource:
    family: FactorFamily
    reference: ValidationArtifactReference
    values: Mapping[str, Decimal | int | str | bool | None]
    symbol: str | None = None
    available_at: datetime | None = None
    gate_result: str | None = None
    missingness: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.family not in {
            FactorFamily.MARKET_REGIME,
            FactorFamily.ETF,
            FactorFamily.THEME,
            FactorFamily.CAPITAL,
        }:
            raise ValueError("state source requires a canonical State factor family")
        if not self.values:
            raise ValueError("state source requires copied canonical values")


@dataclass(frozen=True, slots=True)
class ResearchFactorExposure:
    symbol: str
    family: FactorFamily
    factor_id: str
    timeframe: str | None
    raw_numeric: Decimal | None
    raw_text: str | None
    normalized_exposure: Decimal | None
    model_contribution: Decimal | None
    gate_result: str | None
    missingness: tuple[str, ...]
    available_at: datetime | None
    source_reference: ValidationArtifactReference
    source_value_path: str

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("factor_id", self.factor_id)
        require_text("source_value_path", self.source_value_path)
        if (self.raw_numeric is None) == (self.raw_text is None) and not self.missingness:
            raise ValueError("factor exposure requires exactly one raw value or missingness")
        if self.missingness != tuple(sorted(set(self.missingness))):
            raise ValueError("factor missingness must be unique and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "family": self.family.value,
            "factor_id": self.factor_id,
            "timeframe": self.timeframe,
            "raw_numeric": decimal_text(self.raw_numeric),
            "raw_text": self.raw_text,
            "normalized_exposure": decimal_text(self.normalized_exposure),
            "model_contribution": decimal_text(self.model_contribution),
            "gate_result": self.gate_result,
            "missingness": list(self.missingness),
            "available_at": None if self.available_at is None else timestamp(self.available_at),
            "source_reference": self.source_reference.to_canonical_dict(),
            "source_value_path": self.source_value_path,
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> ResearchFactorExposure:
        expected = {
            "symbol",
            "family",
            "factor_id",
            "timeframe",
            "raw_numeric",
            "raw_text",
            "normalized_exposure",
            "model_contribution",
            "gate_result",
            "missingness",
            "available_at",
            "source_reference",
            "source_value_path",
        }
        if set(value) != expected or not isinstance(value["missingness"], list):
            raise ValueError("Research Factor Exposure fields mismatch")

        def optional_decimal(name: str) -> Decimal | None:
            raw = value[name]
            return None if raw is None else Decimal(str(raw))

        available = value["available_at"]
        return cls(
            symbol=str(value["symbol"]),
            family=FactorFamily(str(value["family"])),
            factor_id=str(value["factor_id"]),
            timeframe=(
                None if value["timeframe"] is None else str(value["timeframe"])
            ),
            raw_numeric=optional_decimal("raw_numeric"),
            raw_text=(
                None if value["raw_text"] is None else str(value["raw_text"])
            ),
            normalized_exposure=optional_decimal("normalized_exposure"),
            model_contribution=optional_decimal("model_contribution"),
            gate_result=(
                None if value["gate_result"] is None else str(value["gate_result"])
            ),
            missingness=tuple(str(item) for item in value["missingness"]),
            available_at=(
                None if available is None else datetime.fromisoformat(str(available))
            ),
            source_reference=ValidationArtifactReference.from_canonical_dict(
                value["source_reference"]
            ),
            source_value_path=str(value["source_value_path"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchPanelEnrichment:
    enrichment_id: ArtifactId
    enrichment_hash: str
    panel_reference: ValidationArtifactReference
    exposures: tuple[ResearchFactorExposure, ...]
    extracted_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "research-panel-enrichment/v1"

    def __post_init__(self) -> None:
        require_sha256("enrichment_hash", self.enrichment_hash)
        ordered = tuple(sorted(self.exposures, key=_exposure_key))
        if not self.exposures or self.exposures != ordered:
            raise ValueError("enrichment exposures must be non-empty, unique, and sorted")
        if len({_exposure_key(item) for item in self.exposures}) != len(self.exposures):
            raise ValueError("enrichment exposures must be unique")
        if tuple(sorted(set(self.limitations))) != self.limitations:
            raise ValueError("enrichment limitations must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.enrichment_hash:
            raise ValueError("Research Panel enrichment hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        panel_reference: ValidationArtifactReference,
        exposures: Iterable[ResearchFactorExposure],
        extracted_at: datetime,
    ) -> ResearchPanelEnrichment:
        ordered = tuple(sorted(exposures, key=_exposure_key))
        values = {
            "panel_reference": panel_reference.to_canonical_dict(),
            "exposures": [item.to_canonical_dict() for item in ordered],
            "extracted_at": timestamp(extracted_at),
            "limitations": list(ENGINEERING_LIMITATIONS),
            "schema_version": "research-panel-enrichment/v1",
        }
        artifact_id, digest = content_identity("research-panel-enrichment", values)
        return cls(
            enrichment_id=artifact_id,
            enrichment_hash=digest,
            panel_reference=panel_reference,
            exposures=ordered,
            extracted_at=extracted_at,
            limitations=ENGINEERING_LIMITATIONS,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "panel_reference": self.panel_reference.to_canonical_dict(),
            "exposures": [item.to_canonical_dict() for item in self.exposures],
            "extracted_at": timestamp(self.extracted_at),
            "limitations": list(self.limitations),
            "schema_version": self.schema_version,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "enrichment_id": str(self.enrichment_id),
            "enrichment_hash": self.enrichment_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> ResearchPanelEnrichment:
        expected = {
            "enrichment_id",
            "enrichment_hash",
            "panel_reference",
            "exposures",
            "extracted_at",
            "limitations",
            "schema_version",
        }
        if set(value) != expected:
            raise ValueError("Panel Enrichment fields mismatch")
        exposures = value["exposures"]
        limitations = value["limitations"]
        if not isinstance(exposures, list) or not isinstance(limitations, list):
            raise ValueError("Panel Enrichment arrays are invalid")
        return cls(
            enrichment_id=ArtifactId(str(value["enrichment_id"])),
            enrichment_hash=str(value["enrichment_hash"]),
            panel_reference=ValidationArtifactReference.from_canonical_dict(
                value["panel_reference"]
            ),
            exposures=tuple(
                ResearchFactorExposure.from_canonical_dict(item)
                for item in exposures
            ),
            extracted_at=datetime.fromisoformat(str(value["extracted_at"])),
            limitations=tuple(str(item) for item in limitations),
            schema_version=str(value["schema_version"]),
        )


def extract_canonical_factors(
    *,
    panel_reference: ValidationArtifactReference,
    symbols: tuple[str, ...],
    dataset: VerifiedMarketDataDataset,
    feature_bundle: VerifiedFeatureBundleV2,
    dynamic_pool: DynamicStockPoolVersion | None,
    candidate_set: CandidateSet | None,
    signal_run: SignalRunArtifactV3 | None,
    forecasts: tuple[PathForecast, ...],
    state_sources: tuple[CanonicalStateFactorSource, ...],
    decision_time: datetime,
    extracted_at: datetime,
) -> ResearchPanelEnrichment:
    """Copy canonical values into a lineage-complete panel sidecar."""

    expected = tuple(sorted(set(symbols)))
    if not expected:
        raise ValueError("factor extraction requires an evaluated symbol universe")
    if extracted_at < decision_time:
        raise ValueError("Panel enrichment cannot predate DecisionTime")
    if (
        feature_bundle.artifact.dataset_id != dataset.artifact.dataset_id
        or feature_bundle.artifact.dataset_hash != dataset.artifact.content_hash
        or feature_bundle.artifact.decision_time != decision_time
    ):
        raise ValueError("Feature Bundle does not bind the Panel Dataset/DecisionTime")
    if dynamic_pool is not None and (dynamic_pool.decision_time != decision_time or dynamic_pool.available_at > decision_time):
        raise ValueError("Dynamic Pool is not available at Panel DecisionTime")
    if any(source.available_at is not None and source.available_at > decision_time for source in state_sources):
        raise ValueError("State factor source is not available at Panel DecisionTime")
    if signal_run is not None:
        mismatches = tuple(
            label
            for label, matches in (
                (
                    "DATASET_ID",
                    str(signal_run.market_data_dataset_id)
                    == str(dataset.artifact.dataset_id),
                ),
                (
                    "DATASET_HASH",
                    signal_run.market_data_dataset_hash
                    == dataset.artifact.content_hash,
                ),
                (
                    "FEATURE_BUNDLE_ID",
                    signal_run.feature_bundle_id
                    == feature_bundle.artifact.bundle_id,
                ),
                (
                    "FEATURE_BUNDLE_HASH",
                    signal_run.feature_bundle_hash
                    == feature_bundle.artifact.content_hash,
                ),
                ("CANDIDATE_SET", candidate_set is not None),
                (
                    "CANDIDATE_ID",
                    candidate_set is not None
                    and signal_run.candidate_set.envelope.artifact_id
                    == candidate_set.envelope.artifact_id,
                ),
                (
                    "CANDIDATE_HASH",
                    candidate_set is not None
                    and signal_run.candidate_set.envelope.content_hash
                    == candidate_set.envelope.content_hash,
                ),
            )
            if not matches
        )
        if mismatches:
            raise ValueError(
                "Signal does not bind the supplied Dataset/Feature Bundle/Candidate Set: "
                + ",".join(mismatches)
            )
    exposures: list[ResearchFactorExposure] = []
    exposures.extend(_market_bar_exposures(expected, dataset, decision_time))
    exposures.extend(_feature_exposures(expected, feature_bundle, decision_time))
    exposures.extend(_state_exposures(expected, state_sources))
    exposures.extend(_pool_exposures(expected, dynamic_pool))
    exposures.extend(_candidate_exposures(expected, candidate_set))
    exposures.extend(_signal_exposures(expected, signal_run))
    exposures.extend(_forecast_exposures(expected, forecasts))
    existing = {(item.symbol, item.family) for item in exposures}
    for symbol in expected:
        for family in FactorFamily:
            if (symbol, family) not in existing:
                exposures.append(
                    ResearchFactorExposure(
                        symbol=symbol,
                        family=family,
                        factor_id=f"missing.{family.value.lower()}",
                        timeframe=None,
                        raw_numeric=None,
                        raw_text=None,
                        normalized_exposure=None,
                        model_contribution=None,
                        gate_result="MISSING",
                        missingness=("CANONICAL_FACTOR_FAMILY_NOT_AVAILABLE",),
                        available_at=None,
                        source_reference=panel_reference,
                        source_value_path=f"panel.missing.{family.value.lower()}",
                    )
                )
    return ResearchPanelEnrichment.create(
        panel_reference=panel_reference,
        exposures=exposures,
        extracted_at=extracted_at,
    )


def publish_research_panel_enrichment(*, root: Path, enrichment: ResearchPanelEnrichment) -> Path:
    path = root / f"{enrichment.enrichment_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(enrichment.to_canonical_dict()) + "\n",
        collision_message="Research Panel enrichment identity conflict",
    )
    return path


def _market_bar_exposures(
    symbols: tuple[str, ...], dataset: VerifiedMarketDataDataset, decision_time: datetime
) -> list[ResearchFactorExposure]:
    result: list[ResearchFactorExposure] = []
    reference = ValidationArtifactReference(
        "MARKET_DATA_DATASET",
        ArtifactId(str(dataset.artifact.dataset_id)),
        dataset.artifact.content_hash,
    )
    for symbol in symbols:
        bars = [
            item
            for item in dataset.bars
            if item.symbol == symbol and item.event_end <= decision_time and item.available_at <= decision_time
        ]
        latest_by_timeframe: dict[Timeframe, Any] = {}
        for bar in bars:
            current = latest_by_timeframe.get(bar.timeframe)
            if current is None or bar.event_end > current.event_end:
                latest_by_timeframe[bar.timeframe] = bar
        for timeframe, bar in sorted(latest_by_timeframe.items(), key=lambda item: item[0].value):
            family = FactorFamily.INTRADAY if timeframe is Timeframe.MINUTE_1 else FactorFamily.PRICE
            for name in ("open", "high", "low", "close", "previous_close"):
                result.append(
                    _numeric_exposure(
                        symbol,
                        family,
                        f"bar.{name}",
                        getattr(bar, name),
                        reference,
                        f"bars[{bar.bar_id}].{name}",
                        timeframe.value,
                        bar.available_at,
                    )
                )
            for name, value, value_family in (
                ("volume", bar.volume, FactorFamily.VOLUME),
                ("amount", bar.amount, FactorFamily.AMOUNT),
                ("turnover_rate", bar.turnover_rate, FactorFamily.LIQUIDITY),
            ):
                result.append(
                    _numeric_exposure(
                        symbol,
                        value_family,
                        f"bar.{name}",
                        value,
                        reference,
                        f"bars[{bar.bar_id}].{name}",
                        timeframe.value,
                        bar.available_at,
                    )
                )
            result.append(
                _text_exposure(
                    symbol,
                    FactorFamily.LIQUIDITY,
                    "bar.trading_status",
                    bar.trading_status.value,
                    reference,
                    f"bars[{bar.bar_id}].trading_status",
                    timeframe.value,
                    bar.available_at,
                )
            )
            result.append(
                _text_exposure(
                    symbol,
                    FactorFamily.LIQUIDITY,
                    "bar.price_limit_state",
                    bar.price_limit_state.value,
                    reference,
                    f"bars[{bar.bar_id}].price_limit_state",
                    timeframe.value,
                    bar.available_at,
                )
            )
    return result


def _feature_exposures(symbols: tuple[str, ...], bundle: VerifiedFeatureBundleV2, decision_time: datetime) -> list[ResearchFactorExposure]:
    result: list[ResearchFactorExposure] = []
    allowed = set(symbols)
    for verified in bundle.artifacts:
        artifact = verified.artifact
        if artifact.symbol not in allowed:
            continue
        reference = ValidationArtifactReference("FEATURE_ARTIFACT_V2", artifact.artifact_id, artifact.content_hash)
        for value in artifact.values:
            if value.available_at > decision_time:
                continue
            family = _feature_family(artifact.feature_id, value.output_id, artifact.timeframe)
            missing = value.missing_reason_codes if value.state is FeatureValueState.MISSING else ()
            numeric, text = _split_scalar(value.value)
            result.append(
                ResearchFactorExposure(
                    symbol=artifact.symbol,
                    family=family,
                    factor_id=f"{artifact.feature_id}.{value.output_id}",
                    timeframe=artifact.timeframe.value,
                    raw_numeric=numeric,
                    raw_text=text,
                    normalized_exposure=None,
                    model_contribution=None,
                    gate_result=artifact.state.value,
                    missingness=tuple(sorted(set(missing))),
                    available_at=value.available_at,
                    source_reference=reference,
                    source_value_path=f"values.{value.output_id}",
                )
            )
    return result


def _state_exposures(symbols: tuple[str, ...], sources: tuple[CanonicalStateFactorSource, ...]) -> list[ResearchFactorExposure]:
    result: list[ResearchFactorExposure] = []
    for source in sources:
        scoped = symbols if source.symbol is None else (source.symbol,)
        for symbol in scoped:
            if symbol not in symbols:
                continue
            for name, value in sorted(source.values.items()):
                numeric, text = _split_scalar(value)
                result.append(
                    ResearchFactorExposure(
                        symbol=symbol,
                        family=source.family,
                        factor_id=f"state.{source.family.value.lower()}.{name}",
                        timeframe=None,
                        raw_numeric=numeric,
                        raw_text=text,
                        normalized_exposure=None,
                        model_contribution=None,
                        gate_result=source.gate_result,
                        missingness=tuple(sorted(set(source.missingness))),
                        available_at=source.available_at,
                        source_reference=source.reference,
                        source_value_path=f"values.{name}",
                    )
                )
    return result


def _pool_exposures(symbols: tuple[str, ...], pool: DynamicStockPoolVersion | None) -> list[ResearchFactorExposure]:
    if pool is None:
        return []
    reference = ValidationArtifactReference("DYNAMIC_STOCK_POOL", pool.pool_id, pool.pool_hash)
    members = {item.symbol: item for item in pool.members}
    result: list[ResearchFactorExposure] = []
    for symbol in symbols:
        item = members.get(symbol)
        if item is None:
            continue
        for name, value in (
            ("score", item.score),
            ("rank", item.rank),
            ("liquidity", item.liquidity),
            ("data_coverage", item.data_coverage),
            ("listing_age_days", item.listing_age_days),
            ("included", item.included),
            ("eligible", item.eligibility),
            ("suspended", item.suspended),
        ):
            numeric, text = _split_scalar(value)
            result.append(
                ResearchFactorExposure(
                    symbol,
                    FactorFamily.DYNAMIC_POOL,
                    f"dynamic_pool.{name}",
                    None,
                    numeric,
                    text,
                    None,
                    None,
                    item.gate_result,
                    tuple(sorted(set(item.missing_evidence))),
                    pool.available_at,
                    reference,
                    f"members.{symbol}.{name}",
                )
            )
    return result


def _candidate_exposures(symbols: tuple[str, ...], candidates: CandidateSet | None) -> list[ResearchFactorExposure]:
    if candidates is None:
        return []
    reference = ValidationArtifactReference("CANDIDATE_SET", candidates.envelope.artifact_id, candidates.envelope.content_hash)
    records = {item.symbol: item for item in candidates.records}
    result: list[ResearchFactorExposure] = []
    families = {
        "candidate_discovery_score": FactorFamily.CANDIDATE,
        "market_regime_score": FactorFamily.MARKET_REGIME,
        "theme_score": FactorFamily.THEME,
        "capital_evolution_score": FactorFamily.CAPITAL,
        "rank": FactorFamily.CANDIDATE,
    }
    for symbol in symbols:
        item = records.get(symbol)
        if item is None:
            continue
        for name, family in families.items():
            numeric, text = _split_scalar(getattr(item, name))
            result.append(
                ResearchFactorExposure(
                    symbol,
                    family,
                    f"candidate.{name}",
                    None,
                    numeric,
                    text,
                    None,
                    None,
                    item.selection_status.value,
                    (),
                    None,
                    reference,
                    f"records.{symbol}.{name}",
                )
            )
    return result


def _signal_exposures(symbols: tuple[str, ...], signal: SignalRunArtifactV3 | None) -> list[ResearchFactorExposure]:
    if signal is None:
        return []
    reference = ValidationArtifactReference("CANONICAL_SIGNAL_RUN_V3", signal.artifact_id, signal.envelope.content_hash)
    result: list[ResearchFactorExposure] = []
    for observation in signal.observations:
        if observation.symbol not in symbols:
            continue
        for factor in observation.factors:
            result.append(
                ResearchFactorExposure(
                    observation.symbol,
                    FactorFamily.SIGNAL,
                    f"signal.input.{factor.factor_name.value.lower()}",
                    factor.timeframe.value,
                    factor.value,
                    None,
                    None,
                    None,
                    factor.freshness_state.value,
                    factor.missing_reason_codes,
                    factor.source_available_at,
                    reference,
                    f"observations.{observation.observation_id}.factors.{factor.factor_name.value}",
                )
            )
    for snapshot in signal.snapshots:
        if snapshot.symbol not in symbols:
            continue
        measures = project_signal_research_measures(snapshot)
        for name, value in (
            ("signal_strength", measures.signal_strength),
            ("data_completeness", measures.data_completeness),
            ("confirmation_count", snapshot.confirmation_count),
        ):
            numeric, text = _split_scalar(value)
            result.append(
                ResearchFactorExposure(
                    snapshot.symbol,
                    FactorFamily.SIGNAL,
                    f"signal.output.{name}",
                    None,
                    numeric,
                    text,
                    None,
                    None,
                    snapshot.signal_state.value,
                    (),
                    None,
                    reference,
                    (
                        f"snapshots.{snapshot.artifact_id}.confidence"
                        if name == "data_completeness"
                        else f"snapshots.{snapshot.artifact_id}.{name}"
                    ),
                )
            )
    return result


def _forecast_exposures(symbols: tuple[str, ...], forecasts: tuple[PathForecast, ...]) -> list[ResearchFactorExposure]:
    result: list[ResearchFactorExposure] = []
    for forecast in forecasts:
        if forecast.symbol not in symbols:
            continue
        reference = ValidationArtifactReference("PATH_FORECAST", forecast.envelope.artifact_id, forecast.envelope.content_hash)
        values = (
            ("target_id", str(forecast.target_id)),
            ("expected_mfe", forecast.expected_mfe),
            ("expected_mae", forecast.expected_mae),
            ("usable_sample_count", forecast.usable_sample_count),
            ("excluded_sample_count", forecast.excluded_sample_count),
        )
        for name, value in values:
            numeric, text = _split_scalar(value)
            result.append(
                ResearchFactorExposure(
                    forecast.symbol,
                    FactorFamily.FORECAST,
                    f"forecast.{name}",
                    forecast.forecast_horizon,
                    numeric,
                    text,
                    None,
                    None,
                    forecast.forecast_status.value,
                    forecast.reason_codes if value is None else (),
                    None,
                    reference,
                    name,
                )
            )
        for quantile in forecast.return_quantiles:
            result.append(
                _numeric_exposure(
                    forecast.symbol,
                    FactorFamily.FORECAST,
                    f"forecast.return_quantile.{quantile.probability}",
                    Decimal(str(quantile.return_value)),
                    reference,
                    f"return_quantiles.{quantile.probability}",
                    forecast.forecast_horizon,
                    None,
                )
            )
    return result


def _feature_family(feature_id: str, output_id: str, timeframe: Timeframe) -> FactorFamily:
    value = f"{feature_id}.{output_id}".lower()
    if timeframe is Timeframe.MINUTE_1 or "intraday" in value:
        return FactorFamily.INTRADAY
    for needle, family in (
        ("macd", FactorFamily.MACD),
        ("vwap", FactorFamily.VWAP),
        ("volume", FactorFamily.VOLUME),
        ("amount", FactorFamily.AMOUNT),
        ("volatil", FactorFamily.VOLATILITY),
        ("momentum", FactorFamily.MOMENTUM_TREND),
        ("trend", FactorFamily.MOMENTUM_TREND),
        ("moving_average", FactorFamily.MA_EMA),
        ("ema", FactorFamily.MA_EMA),
        ("ma_", FactorFamily.MA_EMA),
        ("liquid", FactorFamily.LIQUIDITY),
        ("price_action", FactorFamily.PRICE_ACTION),
    ):
        if needle in value:
            return family
    return FactorFamily.PRICE_ACTION


def _split_scalar(value: object) -> tuple[Decimal | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "true" if value else "false"
    if isinstance(value, (Decimal, int, float)):
        return Decimal(str(value)), None
    return None, str(value)


def _numeric_exposure(
    symbol: str,
    family: FactorFamily,
    factor_id: str,
    value: object,
    reference: ValidationArtifactReference,
    path: str,
    timeframe: str | None,
    available_at: datetime | None,
) -> ResearchFactorExposure:
    numeric, text = _split_scalar(value)
    return ResearchFactorExposure(
        symbol,
        family,
        factor_id,
        timeframe,
        numeric,
        text,
        None,
        None,
        None,
        ("CANONICAL_VALUE_MISSING",) if value is None else (),
        available_at,
        reference,
        path,
    )


def _text_exposure(
    symbol: str,
    family: FactorFamily,
    factor_id: str,
    value: str,
    reference: ValidationArtifactReference,
    path: str,
    timeframe: str | None,
    available_at: datetime | None,
) -> ResearchFactorExposure:
    return ResearchFactorExposure(symbol, family, factor_id, timeframe, None, value, None, None, None, (), available_at, reference, path)


def _exposure_key(item: ResearchFactorExposure) -> tuple[str, str, str, str, str]:
    return (item.symbol, item.family.value, item.factor_id, item.timeframe or "", item.source_value_path)
