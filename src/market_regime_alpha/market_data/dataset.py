"""Content-addressed canonical market-data dataset contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_unique_text,
)
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    CanonicalMarketBar,
    Timeframe,
    parse_utc_second,
    require_utc_second,
)


MARKET_DATA_PARTITION_SCHEMA = "canonical-market-data-partition-v1"
MARKET_DATA_DATASET_SCHEMA = "canonical-market-data-dataset-v1"


class FormalPitStatus(str, Enum):
    FORMAL_PIT_NOT_ESTABLISHED = "FORMAL_PIT_NOT_ESTABLISHED"
    PIT_CORRECT_FOR_DECLARED_SCOPE = "PIT_CORRECT_FOR_DECLARED_SCOPE"


class DatasetCoverageState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True, slots=True)
class MarketDataCoverage:
    state: DatasetCoverageState
    expected_symbols: tuple[str, ...]
    observed_symbols: tuple[str, ...]
    expected_timeframes: tuple[Timeframe, ...]
    observed_timeframes: tuple[Timeframe, ...]
    missing_symbol_timeframes: tuple[str, ...]
    missing_field_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for label, values in (
            ("expected_symbols", self.expected_symbols),
            ("observed_symbols", self.observed_symbols),
            ("missing_symbol_timeframes", self.missing_symbol_timeframes),
        ):
            require_unique_text(label, values)
            if values != tuple(sorted(values)):
                raise ValueError(f"{label} must be sorted")
        for label, values in (
            ("expected_timeframes", self.expected_timeframes),
            ("observed_timeframes", self.observed_timeframes),
        ):
            if values != tuple(sorted(set(values), key=lambda item: item.value)):
                raise ValueError(f"{label} must be unique and sorted")
        if not self.expected_symbols or not self.expected_timeframes:
            raise ValueError("coverage expectations must not be empty")
        if not set(self.observed_symbols).issubset(self.expected_symbols):
            raise ValueError("observed symbols exceed declared coverage scope")
        if not set(self.observed_timeframes).issubset(self.expected_timeframes):
            raise ValueError("observed timeframes exceed declared coverage scope")
        keys = tuple(name for name, _ in self.missing_field_counts)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("missing field counts must be unique and sorted")
        if any(count <= 0 for _, count in self.missing_field_counts):
            raise ValueError("missing field counts must be positive")
        expected_state = (
            DatasetCoverageState.PARTIAL
            if self.missing_symbol_timeframes
            else DatasetCoverageState.COMPLETE
        )
        if self.state is not expected_state:
            raise ValueError("coverage state does not match missing combinations")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "expected_symbols": list(self.expected_symbols),
            "observed_symbols": list(self.observed_symbols),
            "expected_timeframes": [item.value for item in self.expected_timeframes],
            "observed_timeframes": [item.value for item in self.observed_timeframes],
            "missing_symbol_timeframes": list(self.missing_symbol_timeframes),
            "missing_field_counts": [
                {"field": name, "count": count}
                for name, count in self.missing_field_counts
            ],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MarketDataCoverage:
        expected = {
            "state",
            "expected_symbols",
            "observed_symbols",
            "expected_timeframes",
            "observed_timeframes",
            "missing_symbol_timeframes",
            "missing_field_counts",
        }
        if set(payload) != expected:
            raise ValueError("Market Data Coverage fields mismatch")
        raw_missing = payload["missing_field_counts"]
        if not isinstance(raw_missing, list) or any(
            not isinstance(item, dict) or set(item) != {"field", "count"}
            for item in raw_missing
        ):
            raise ValueError("missing_field_counts must be canonical objects")
        return cls(
            state=DatasetCoverageState(str(payload["state"])),
            expected_symbols=_string_tuple(payload["expected_symbols"], "expected_symbols"),
            observed_symbols=_string_tuple(payload["observed_symbols"], "observed_symbols"),
            expected_timeframes=tuple(
                Timeframe(item)
                for item in _string_tuple(
                    payload["expected_timeframes"], "expected_timeframes"
                )
            ),
            observed_timeframes=tuple(
                Timeframe(item)
                for item in _string_tuple(
                    payload["observed_timeframes"], "observed_timeframes"
                )
            ),
            missing_symbol_timeframes=_string_tuple(
                payload["missing_symbol_timeframes"], "missing_symbol_timeframes"
            ),
            missing_field_counts=tuple(
                (str(item["field"]), _positive_int(item["count"], "missing count"))
                for item in raw_missing
            ),
        )


@dataclass(frozen=True, slots=True)
class MarketDataPartition:
    schema_version: str
    partition_id: ArtifactId
    content_hash: str
    symbol: str
    timeframe: Timeframe
    first_market_date: date
    last_market_date: date
    bar_count: int
    relative_path: str
    bars: tuple[CanonicalMarketBar, ...]

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_DATA_PARTITION_SCHEMA:
            raise ValueError("unsupported Market Data Partition schema")
        require_sha256("content_hash", self.content_hash)
        if self.bar_count != len(self.bars) or self.bar_count <= 0:
            raise ValueError("partition bar_count mismatch")
        if self.relative_path != f"partitions/{self.symbol}/{self.timeframe.value}.json":
            raise ValueError("partition relative path mismatch")
        sort_keys = tuple((item.event_start, str(item.bar_id)) for item in self.bars)
        if sort_keys != tuple(sorted(sort_keys)):
            raise ValueError("partition bars must be sorted")
        if any(
            item.symbol != self.symbol or item.timeframe is not self.timeframe
            for item in self.bars
        ):
            raise ValueError("partition scope mismatch")
        if self.first_market_date != self.bars[0].market_date:
            raise ValueError("partition first market date mismatch")
        if self.last_market_date != self.bars[-1].market_date:
            raise ValueError("partition last market date mismatch")
        for bar in self.bars:
            bar.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        timeframe: Timeframe,
        bars: tuple[CanonicalMarketBar, ...],
    ) -> MarketDataPartition:
        ordered = tuple(sorted(bars, key=lambda item: (item.event_start, str(item.bar_id))))
        if not ordered:
            raise ValueError("Market Data Partition requires bars")
        payload = {
            "schema_version": MARKET_DATA_PARTITION_SCHEMA,
            "symbol": symbol,
            "timeframe": timeframe.value,
            "bars": [item.to_canonical_dict() for item in ordered],
        }
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=MARKET_DATA_PARTITION_SCHEMA,
            partition_id=ArtifactId(
                f"market-data-partition-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            symbol=symbol,
            timeframe=timeframe,
            first_market_date=ordered[0].market_date,
            last_market_date=ordered[-1].market_date,
            bar_count=len(ordered),
            relative_path=f"partitions/{symbol}/{timeframe.value}.json",
            bars=ordered,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "bars": [item.to_canonical_dict() for item in self.bars],
        }

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Market Data Partition payload hash mismatch")
        expected_id = f"market-data-partition-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.partition_id) != expected_id:
            raise ValueError("Market Data Partition identity mismatch")

    def reference_dict(self) -> dict[str, Any]:
        return {
            "partition_id": str(self.partition_id),
            "content_hash": self.content_hash,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "first_market_date": self.first_market_date.isoformat(),
            "last_market_date": self.last_market_date.isoformat(),
            "bar_count": self.bar_count,
            "relative_path": self.relative_path,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "partition_id": str(self.partition_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MarketDataPartition:
        expected = {
            "partition_id",
            "content_hash",
            "schema_version",
            "symbol",
            "timeframe",
            "bars",
        }
        if set(payload) != expected:
            raise ValueError("Market Data Partition fields mismatch")
        raw_bars = payload["bars"]
        if not isinstance(raw_bars, list) or not all(
            isinstance(item, dict) for item in raw_bars
        ):
            raise ValueError("partition bars must be an array of objects")
        result = cls.create(
            symbol=str(payload["symbol"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            bars=tuple(CanonicalMarketBar.from_canonical_dict(item) for item in raw_bars),
        )
        if (
            str(result.partition_id) != str(payload["partition_id"])
            or result.content_hash != str(payload["content_hash"])
        ):
            raise ValueError("Market Data Partition stored identity mismatch")
        return result


@dataclass(frozen=True, slots=True)
class MarketDataDatasetArtifact:
    schema_version: str
    dataset_id: DatasetId
    content_hash: str
    decision_time: datetime
    created_at: datetime
    partitions: tuple[MarketDataPartition, ...]
    bar_count: int
    first_market_date: date
    last_market_date: date
    adjustment_policy: PriceAdjustmentPolicy
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    data_eligibility: DataEligibility
    formal_pit_status: FormalPitStatus
    coverage: MarketDataCoverage
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != MARKET_DATA_DATASET_SCHEMA:
            raise ValueError("unsupported Market Data Dataset schema")
        require_sha256("content_hash", self.content_hash)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("created_at", self.created_at)
        if self.created_at < self.decision_time:
            raise ValueError("created_at cannot precede DecisionTime")
        if not self.partitions:
            raise ValueError("Market Data Dataset requires at least one partition")
        partition_keys = tuple((item.symbol, item.timeframe.value) for item in self.partitions)
        if partition_keys != tuple(sorted(set(partition_keys))):
            raise ValueError("dataset partitions must be unique and sorted")
        if self.bar_count != sum(item.bar_count for item in self.partitions):
            raise ValueError("dataset bar_count mismatch")
        bars = tuple(self.iter_bars())
        if self.first_market_date != min(item.market_date for item in bars):
            raise ValueError("dataset first market date mismatch")
        if self.last_market_date != max(item.market_date for item in bars):
            raise ValueError("dataset last market date mismatch")
        if any(item.available_at > self.decision_time for item in bars):
            raise ValueError("market bar became available after DecisionTime")
        self.adjustment_policy.verify_identity()
        if any(item.adjustment_mode is not self.adjustment_policy.mode for item in bars):
            raise ValueError("market bar adjustment mode differs from dataset policy")
        if self.adjustment_policy.mode is not AdjustmentMode.RAW:
            for bar in bars:
                factor = self.adjustment_policy.factor_for(
                    symbol=bar.symbol,
                    market_date=bar.market_date,
                    decision_time=self.decision_time,
                )
                if (
                    bar.adjustment_factor_id != factor.factor_id
                    or bar.adjustment_factor_hash != factor.content_hash
                    or bar.adjustment_factor != factor.factor
                ):
                    raise ValueError(
                        "adjusted market bar does not bind the applicable factor evidence"
                    )
        references = tuple((str(item_id), item_hash) for item_id, item_hash in self.source_manifest_references)
        if not references:
            raise ValueError("Market Data Dataset requires source manifest authority")
        if references != tuple(sorted(set(references))):
            raise ValueError("source manifest references must be unique and sorted")
        for _, item_hash in self.source_manifest_references:
            require_sha256("source_manifest_hash", item_hash)
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("limitations must be sorted")
        if (
            self.adjustment_policy.mode is AdjustmentMode.RESEARCH_BACK_ADJUSTED
            and self.formal_pit_status is not FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED
        ):
            raise ValueError("research back-adjusted data cannot establish formal PIT")
        if (
            self.data_eligibility is DataEligibility.FORMAL_RESEARCH
            and self.formal_pit_status is not FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE
        ):
            raise ValueError("FORMAL_RESEARCH market data requires PIT evidence")

    @classmethod
    def create(
        cls,
        *,
        decision_time: datetime,
        created_at: datetime,
        bars: tuple[CanonicalMarketBar, ...],
        expected_symbols: tuple[str, ...],
        expected_timeframes: tuple[Timeframe, ...],
        adjustment_policy: PriceAdjustmentPolicy,
        source_manifest_references: tuple[tuple[ArtifactId, str], ...],
        data_eligibility: DataEligibility,
        formal_pit_status: FormalPitStatus,
        limitations: tuple[str, ...],
    ) -> MarketDataDatasetArtifact:
        require_utc_second("decision_time", decision_time)
        require_utc_second("created_at", created_at)
        expected_symbols = tuple(sorted(expected_symbols))
        expected_timeframes = tuple(sorted(expected_timeframes, key=lambda item: item.value))
        ordered_bars = tuple(
            sorted(
                bars,
                key=lambda item: (
                    item.symbol,
                    item.timeframe.value,
                    item.event_start,
                    str(item.bar_id),
                ),
            )
        )
        if not ordered_bars:
            raise ValueError("Market Data Dataset requires bars")
        duplicate_keys: set[tuple[str, Timeframe, datetime]] = set()
        for bar in ordered_bars:
            key = (bar.symbol, bar.timeframe, bar.event_start)
            if key in duplicate_keys:
                raise ValueError("duplicate market bar for symbol/timeframe/event time")
            duplicate_keys.add(key)
        grouped: dict[tuple[str, Timeframe], list[CanonicalMarketBar]] = {}
        for bar in ordered_bars:
            grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
        partitions = tuple(
            MarketDataPartition.create(symbol=symbol, timeframe=timeframe, bars=tuple(items))
            for (symbol, timeframe), items in sorted(
                grouped.items(), key=lambda item: (item[0][0], item[0][1].value)
            )
        )
        coverage = _build_coverage(
            bars=ordered_bars,
            expected_symbols=expected_symbols,
            expected_timeframes=expected_timeframes,
        )
        ordered_sources = tuple(
            sorted(source_manifest_references, key=lambda item: (str(item[0]), item[1]))
        )
        ordered_limitations = tuple(sorted(limitations))
        semantic = _dataset_payload(
            decision_time=decision_time,
            created_at=created_at,
            partitions=partitions,
            bar_count=len(ordered_bars),
            first_market_date=min(item.market_date for item in ordered_bars),
            last_market_date=max(item.market_date for item in ordered_bars),
            adjustment_policy=adjustment_policy,
            source_manifest_references=ordered_sources,
            data_eligibility=data_eligibility,
            formal_pit_status=formal_pit_status,
            coverage=coverage,
            limitations=ordered_limitations,
        )
        content_hash = canonical_hash(semantic)
        result = cls(
            schema_version=MARKET_DATA_DATASET_SCHEMA,
            dataset_id=DatasetId(
                f"market-data-dataset-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            decision_time=decision_time,
            created_at=created_at,
            partitions=partitions,
            bar_count=len(ordered_bars),
            first_market_date=min(item.market_date for item in ordered_bars),
            last_market_date=max(item.market_date for item in ordered_bars),
            adjustment_policy=adjustment_policy,
            source_manifest_references=ordered_sources,
            data_eligibility=data_eligibility,
            formal_pit_status=formal_pit_status,
            coverage=coverage,
            limitations=ordered_limitations,
        )
        result.verify_identity()
        return result

    def iter_bars(self) -> Iterable[CanonicalMarketBar]:
        for partition in self.partitions:
            yield from partition.bars

    def semantic_payload(self) -> dict[str, Any]:
        return _dataset_payload(
            decision_time=self.decision_time,
            created_at=self.created_at,
            partitions=self.partitions,
            bar_count=self.bar_count,
            first_market_date=self.first_market_date,
            last_market_date=self.last_market_date,
            adjustment_policy=self.adjustment_policy,
            source_manifest_references=self.source_manifest_references,
            data_eligibility=self.data_eligibility,
            formal_pit_status=self.formal_pit_status,
            coverage=self.coverage,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        for partition in self.partitions:
            partition.verify_identity()
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Market Data Dataset payload hash mismatch")
        expected_id = f"market-data-dataset-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.dataset_id) != expected_id:
            raise ValueError("Market Data Dataset identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": str(self.dataset_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        partitions: tuple[MarketDataPartition, ...],
        adjustment_policy: PriceAdjustmentPolicy,
    ) -> MarketDataDatasetArtifact:
        expected = {
            "dataset_id",
            "content_hash",
            "schema_version",
            "decision_time",
            "created_at",
            "partitions",
            "bar_count",
            "first_market_date",
            "last_market_date",
            "adjustment_policy_id",
            "adjustment_policy_hash",
            "source_manifest_references",
            "data_eligibility",
            "formal_pit_status",
            "coverage",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Market Data Dataset fields mismatch")
        raw_references = payload["source_manifest_references"]
        if not isinstance(raw_references, list) or any(
            not isinstance(item, dict) or set(item) != {"artifact_id", "content_hash"}
            for item in raw_references
        ):
            raise ValueError("source manifest references must be canonical objects")
        raw_partition_refs = payload["partitions"]
        if not isinstance(raw_partition_refs, list) or any(
            not isinstance(item, dict) for item in raw_partition_refs
        ):
            raise ValueError("partition references must be canonical objects")
        if [item.reference_dict() for item in partitions] != raw_partition_refs:
            raise ValueError("Market Data Dataset partition projection mismatch")
        if (
            str(adjustment_policy.policy_id) != payload["adjustment_policy_id"]
            or adjustment_policy.policy_hash != payload["adjustment_policy_hash"]
        ):
            raise ValueError("Market Data Dataset adjustment policy mismatch")
        raw_coverage = payload["coverage"]
        if not isinstance(raw_coverage, dict):
            raise ValueError("coverage must be an object")
        raw_limitations = payload["limitations"]
        if not isinstance(raw_limitations, list) or any(
            not isinstance(item, str) for item in raw_limitations
        ):
            raise ValueError("limitations must be an array of strings")
        result = cls(
            schema_version=str(payload["schema_version"]),
            dataset_id=DatasetId(str(payload["dataset_id"])),
            content_hash=str(payload["content_hash"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            partitions=partitions,
            bar_count=_positive_int(payload["bar_count"], "bar_count"),
            first_market_date=date.fromisoformat(str(payload["first_market_date"])),
            last_market_date=date.fromisoformat(str(payload["last_market_date"])),
            adjustment_policy=adjustment_policy,
            source_manifest_references=tuple(
                (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
                for item in raw_references
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            formal_pit_status=FormalPitStatus(str(payload["formal_pit_status"])),
            coverage=MarketDataCoverage.from_canonical_dict(raw_coverage),
            limitations=tuple(raw_limitations),
        )
        result.verify_identity()
        return result


def _dataset_payload(
    *,
    decision_time: datetime,
    created_at: datetime,
    partitions: tuple[MarketDataPartition, ...],
    bar_count: int,
    first_market_date: date,
    last_market_date: date,
    adjustment_policy: PriceAdjustmentPolicy,
    source_manifest_references: tuple[tuple[ArtifactId, str], ...],
    data_eligibility: DataEligibility,
    formal_pit_status: FormalPitStatus,
    coverage: MarketDataCoverage,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": MARKET_DATA_DATASET_SCHEMA,
        "decision_time": canonical_datetime(decision_time),
        "created_at": canonical_datetime(created_at),
        "partitions": [item.reference_dict() for item in partitions],
        "bar_count": bar_count,
        "first_market_date": first_market_date.isoformat(),
        "last_market_date": last_market_date.isoformat(),
        "adjustment_policy_id": str(adjustment_policy.policy_id),
        "adjustment_policy_hash": adjustment_policy.policy_hash,
        "source_manifest_references": [
            {"artifact_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in source_manifest_references
        ],
        "data_eligibility": data_eligibility.value,
        "formal_pit_status": formal_pit_status.value,
        "coverage": coverage.to_canonical_dict(),
        "limitations": list(limitations),
    }


def _build_coverage(
    *,
    bars: tuple[CanonicalMarketBar, ...],
    expected_symbols: tuple[str, ...],
    expected_timeframes: tuple[Timeframe, ...],
) -> MarketDataCoverage:
    observed_combinations = {(item.symbol, item.timeframe) for item in bars}
    missing = tuple(
        sorted(
            f"{symbol}|{timeframe.value}"
            for symbol in expected_symbols
            for timeframe in expected_timeframes
            if (symbol, timeframe) not in observed_combinations
        )
    )
    missing_fields = {
        "amount": sum(item.amount is None for item in bars),
        "previous_close": sum(item.previous_close is None for item in bars),
        "turnover_rate": sum(item.turnover_rate is None for item in bars),
    }
    return MarketDataCoverage(
        state=(DatasetCoverageState.PARTIAL if missing else DatasetCoverageState.COMPLETE),
        expected_symbols=expected_symbols,
        observed_symbols=tuple(sorted({item.symbol for item in bars})),
        expected_timeframes=expected_timeframes,
        observed_timeframes=tuple(sorted({item.timeframe for item in bars}, key=lambda item: item.value)),
        missing_symbol_timeframes=missing,
        missing_field_counts=tuple(
            (name, count) for name, count in sorted(missing_fields.items()) if count
        ),
    )


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
