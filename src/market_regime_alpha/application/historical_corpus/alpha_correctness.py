"""Independent correctness checks over Historical normalized source bars.

This module is a checker, not a Feature, Target, Runtime or Evidence authority.
It deliberately recomputes the three WP-ALPHA-RESEARCH-01 intraday values and
the T+1 10:30 target without reading their persisted numerical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    VerifiedHistoricalPackage,
    load_verified_historical_package,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.market_data import Timeframe


_SHANGHAI: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")
_SCALE: Final[Decimal] = Decimal("0.000000000001")
_SUPPORTED_FACTORS: Final[frozenset[str]] = frozenset(
    {
        "intraday_return_to_decision_time",
        "price_vs_vwap_return",
        "vwap_slope",
    }
)


class AlphaCorrectnessStatus(str, Enum):
    CORRECTNESS_SUPPORTED = "CORRECTNESS_SUPPORTED"
    CORRECTNESS_FAILED = "CORRECTNESS_FAILED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    PHYSICAL_REPRODUCTION_NOT_ESTABLISHED = (
        "PHYSICAL_REPRODUCTION_NOT_ESTABLISHED"
    )


@dataclass(frozen=True, slots=True)
class PhysicalSourceVerification:
    """Proof that an independently opened physical package matches its PG owner."""

    normalized_owner_reference: ValidationArtifactReference
    physical_hash: str
    checksums_hash: str
    normalized_bar_bindings: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.normalized_owner_reference.artifact_kind != "NORMALIZED_DATASET":
            raise ValueError("physical verification requires normalized-data owner")
        require_sha256("physical_hash", self.physical_hash)
        require_sha256("checksums_hash", self.checksums_hash)
        if not self.normalized_bar_bindings:
            raise ValueError("physical verification requires normalized bars")
        if self.normalized_bar_bindings != tuple(
            sorted(set(self.normalized_bar_bindings))
        ):
            raise ValueError("physical normalized-bar bindings must be unique and sorted")
        for bar_id, content_hash in self.normalized_bar_bindings:
            if not bar_id:
                raise ValueError("physical normalized-bar binding requires bar identity")
            require_sha256("normalized bar hash", content_hash)

    @classmethod
    def establish(
        cls,
        *,
        physical_package: VerifiedHistoricalPackage,
        postgres_owner_package: VerifiedHistoricalPackage,
    ) -> PhysicalSourceVerification:
        physical_package.owner.verify_identity()
        postgres_owner_package.owner.verify_identity()
        if physical_package.owner != postgres_owner_package.owner:
            raise ValueError("physical package does not match PostgreSQL owner identity")
        if (
            physical_package.physical_hash != postgres_owner_package.physical_hash
            or physical_package.checksums != postgres_owner_package.checksums
        ):
            raise ValueError("physical package checksum projection disagrees with owner")
        return cls(
            normalized_owner_reference=physical_package.owner.reference,
            physical_hash=physical_package.physical_hash,
            checksums_hash=canonical_hash(
                {"checksums": [list(item) for item in physical_package.checksums]}
            ),
            normalized_bar_bindings=tuple(
                sorted(
                    (
                        str(record.bar_id),
                        record.content_hash,
                    )
                    for partition in physical_package.owner.partitions
                    for record in partition.records
                    if isinstance(record, HistoricalNormalizedBar)
                )
            ),
        )


def establish_physical_reproduction(
    *,
    package_path: Path,
    corpus_repository: PostgresHistoricalCorpusRepository,
) -> PhysicalSourceVerification:
    """Open physical bytes independently, then compare with the PG owner reload."""

    physical = load_verified_historical_package(package_path)
    postgres_owner = corpus_repository.load(physical.owner.reference)
    return PhysicalSourceVerification.establish(
        physical_package=physical,
        postgres_owner_package=postgres_owner,
    )


@dataclass(frozen=True, slots=True)
class PersistedFeatureObservation:
    factor_id: str
    value: Decimal
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime

    @classmethod
    def create(
        cls,
        *,
        factor_id: str,
        value: Decimal,
        source_bars: tuple[HistoricalNormalizedBar, ...],
    ) -> PersistedFeatureObservation:
        ordered = _ordered_bars(source_bars)
        if factor_id not in _SUPPORTED_FACTORS:
            raise ValueError("unsupported independent intraday factor")
        if not ordered:
            raise ValueError("persisted Feature observation requires source bars")
        ids, hashes, lineage = _source_lineage(ordered)
        return cls(
            factor_id=factor_id,
            value=value,
            source_bar_ids=ids,
            source_bar_hashes=hashes,
            source_lineage_hash=lineage,
            event_start=ordered[0].event_start,
            event_end=ordered[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class FeatureCorrectnessComparison:
    factor_id: str
    persisted_value: Decimal
    recomputed_value: Decimal
    source_bar_ids: tuple[str, ...]
    source_bar_hashes: tuple[str, ...]
    source_lineage_hash: str
    event_start: datetime
    event_end: datetime
    decision_time: datetime
    discrepancies: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "factor_id": self.factor_id,
            "persisted_value": str(self.persisted_value),
            "recomputed_value": str(self.recomputed_value),
            "source_bar_ids": list(self.source_bar_ids),
            "source_bar_hashes": list(self.source_bar_hashes),
            "source_lineage_hash": self.source_lineage_hash,
            "event_start": self.event_start.isoformat(),
            "event_end": self.event_end.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "discrepancies": list(self.discrepancies),
        }


@dataclass(frozen=True, slots=True)
class FeatureReproductionResult:
    session: date
    symbol: str
    decision_time: datetime
    status: AlphaCorrectnessStatus
    physical_source_reference: ValidationArtifactReference | None
    comparisons: tuple[FeatureCorrectnessComparison, ...]
    discrepancies: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "session": self.session.isoformat(),
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "status": self.status.value,
            "physical_source_reference": (
                None
                if self.physical_source_reference is None
                else self.physical_source_reference.to_canonical_dict()
            ),
            "comparisons": [item.to_canonical_dict() for item in self.comparisons],
            "discrepancies": list(self.discrepancies),
        }


@dataclass(frozen=True, slots=True)
class PersistedTargetObservation:
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    decision_source_hashes: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    target_source_hashes: tuple[str, ...]
    target_session: date
    target_event_end: datetime

    @classmethod
    def create(
        cls,
        *,
        decision_reference_price: Decimal,
        target_price: Decimal,
        target_return: Decimal,
        decision_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_source_bars: tuple[HistoricalNormalizedBar, ...],
        target_session: date,
    ) -> PersistedTargetObservation:
        decision = _ordered_bars(decision_source_bars)
        target = _ordered_bars(target_source_bars)
        if not decision or not target:
            raise ValueError("persisted Target observation requires source bars")
        expected = target_price / decision_reference_price - Decimal("1")
        if target_return != expected:
            raise ValueError("persisted Target return disagrees with its prices")
        decision_ids, decision_hashes, _ = _source_lineage(decision)
        target_ids, target_hashes, _ = _source_lineage(target)
        if set(decision_ids).intersection(target_ids):
            raise ValueError("Feature/Decision and Target lineage must be disjoint")
        return cls(
            decision_reference_price=decision_reference_price,
            target_price=target_price,
            target_return=target_return,
            decision_source_ids=decision_ids,
            decision_source_hashes=decision_hashes,
            target_source_ids=target_ids,
            target_source_hashes=target_hashes,
            target_session=target_session,
            target_event_end=target[-1].event_end,
        )


@dataclass(frozen=True, slots=True)
class TargetReproductionResult:
    symbol: str
    decision_time: datetime
    target_session: date
    target_event_end: datetime
    decision_reference_price: Decimal
    target_price: Decimal
    target_return: Decimal
    decision_source_ids: tuple[str, ...]
    target_source_ids: tuple[str, ...]
    status: AlphaCorrectnessStatus
    physical_source_reference: ValidationArtifactReference | None
    trading_calendar_reference: ValidationArtifactReference
    discrepancies: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "target_session": self.target_session.isoformat(),
            "target_event_end": self.target_event_end.isoformat(),
            "decision_reference_price": str(self.decision_reference_price),
            "target_price": str(self.target_price),
            "target_return": str(self.target_return),
            "decision_source_ids": list(self.decision_source_ids),
            "target_source_ids": list(self.target_source_ids),
            "status": self.status.value,
            "physical_source_reference": (
                None
                if self.physical_source_reference is None
                else self.physical_source_reference.to_canonical_dict()
            ),
            "trading_calendar_reference": self.trading_calendar_reference.to_canonical_dict(),
            "discrepancies": list(self.discrepancies),
        }


@dataclass(frozen=True, slots=True)
class AlphaCorrectnessProof:
    proof_id: ArtifactId
    proof_hash: str
    status: AlphaCorrectnessStatus
    feature_results: tuple[FeatureReproductionResult, ...]
    target_results: tuple[TargetReproductionResult, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("proof_hash", self.proof_hash)
        digest = canonical_hash(self.identity_payload())
        if digest != self.proof_hash or self.proof_id != ArtifactId(
            f"alpha-correctness-proof:{digest[7:]}"
        ):
            raise ValueError("Alpha Correctness proof identity mismatch")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_CORRECTNESS_PROOF", self.proof_id, self.proof_hash
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "feature_results": [
                item.to_canonical_dict() for item in self.feature_results
            ],
            "target_results": [item.to_canonical_dict() for item in self.target_results],
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "proof_id": str(self.proof_id),
            "proof_hash": self.proof_hash,
            **self.identity_payload(),
        }


def build_alpha_correctness_proof(
    *,
    feature_results: tuple[FeatureReproductionResult, ...],
    target_results: tuple[TargetReproductionResult, ...],
) -> AlphaCorrectnessProof:
    features = tuple(
        sorted(feature_results, key=lambda item: (item.session, item.symbol))
    )
    targets = tuple(
        sorted(target_results, key=lambda item: (item.decision_time, item.symbol))
    )
    feature_keys = tuple((item.session, item.symbol) for item in features)
    target_keys = tuple((item.decision_time, item.symbol) for item in targets)
    if (
        not features
        or not targets
        or len(feature_keys) != len(set(feature_keys))
        or len(target_keys) != len(set(target_keys))
    ):
        raise ValueError("Alpha Correctness proof inputs are incomplete or duplicated")
    statuses = tuple(item.status for item in features) + tuple(
        item.status for item in targets
    )
    factor_complete = all(
        {item.factor_id for item in result.comparisons} == _SUPPORTED_FACTORS
        for result in features
    )
    if AlphaCorrectnessStatus.CORRECTNESS_FAILED in statuses:
        status = AlphaCorrectnessStatus.CORRECTNESS_FAILED
    elif not factor_complete or AlphaCorrectnessStatus.PARTIALLY_REPRODUCED in statuses:
        status = AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    elif (
        AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED in statuses
        or any(item.physical_source_reference is None for item in features)
        or any(item.physical_source_reference is None for item in targets)
    ):
        status = AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    elif all(item is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED for item in statuses):
        status = AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    else:
        status = AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    limitations = tuple(
        sorted(
            {
                "ALPHA_PROVEN_FALSE",
                "FORMAL_OOS_FALSE",
                "NO_TRADING_AUTHORITY",
                *(
                    ("PHYSICAL_REPRODUCTION_NOT_ESTABLISHED",)
                    if status
                    is AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
                    else ()
                ),
            }
        )
    )
    payload: dict[str, object] = {
        "status": status.value,
        "feature_results": [item.to_canonical_dict() for item in features],
        "target_results": [item.to_canonical_dict() for item in targets],
        "limitations": list(limitations),
    }
    digest = canonical_hash(payload)
    return AlphaCorrectnessProof(
        ArtifactId(f"alpha-correctness-proof:{digest[7:]}"),
        digest,
        status,
        features,
        targets,
        limitations,
    )


def reproduce_intraday_features(
    *,
    session: date,
    symbol: str,
    decision_time: datetime,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: tuple[PersistedFeatureObservation, ...],
    physical_verification: PhysicalSourceVerification | None,
) -> FeatureReproductionResult:
    """Recompute frozen intraday factors directly from bounded normalized bars."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    if session != decision_session:
        raise ValueError("Feature session must equal DecisionTime session")
    persisted_ids = tuple(item.factor_id for item in persisted)
    if persisted_ids != tuple(sorted(set(persisted_ids))):
        raise ValueError("persisted Feature observations must be unique and sorted")
    selected = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    if not selected:
        return FeatureReproductionResult(
            session=session,
            symbol=symbol,
            decision_time=decision_time,
            status=AlphaCorrectnessStatus.PARTIALLY_REPRODUCED,
            physical_source_reference=(
                None
                if physical_verification is None
                else physical_verification.normalized_owner_reference
            ),
            comparisons=(),
            discrepancies=("DECISION_TIME_SOURCE_BARS_MISSING",),
        )
    if physical_verification is not None:
        physical_bindings = set(physical_verification.normalized_bar_bindings)
        selected_bindings = {
            (str(item.bar_id), item.content_hash) for item in selected
        }
        if not selected_bindings.issubset(physical_bindings):
            raise ValueError("Feature source bars are outside verified physical package")
    if any(item.event_end > decision_time for item in selected):
        raise ValueError("Feature source event_end exceeds DecisionTime")
    recomputed = _intraday_values(selected)
    comparisons: list[FeatureCorrectnessComparison] = []
    all_discrepancies: list[str] = []
    for observation in persisted:
        value, factor_bars = recomputed[observation.factor_id]
        ids, hashes, lineage = _source_lineage(factor_bars)
        discrepancies: list[str] = []
        if observation.value != value:
            discrepancies.append(f"VALUE_MISMATCH:{observation.factor_id}")
        if (
            observation.source_bar_ids != ids
            or observation.source_bar_hashes != hashes
            or observation.source_lineage_hash != lineage
        ):
            discrepancies.append(f"SOURCE_LINEAGE_MISMATCH:{observation.factor_id}")
        if (
            observation.event_start != factor_bars[0].event_start
            or observation.event_end != factor_bars[-1].event_end
        ):
            discrepancies.append(f"EVENT_INTERVAL_MISMATCH:{observation.factor_id}")
        comparison = FeatureCorrectnessComparison(
            factor_id=observation.factor_id,
            persisted_value=observation.value,
            recomputed_value=value,
            source_bar_ids=ids,
            source_bar_hashes=hashes,
            source_lineage_hash=lineage,
            event_start=factor_bars[0].event_start,
            event_end=factor_bars[-1].event_end,
            decision_time=decision_time,
            discrepancies=tuple(discrepancies),
        )
        comparisons.append(comparison)
        all_discrepancies.extend(discrepancies)
    status = _correctness_status(
        discrepancies=tuple(all_discrepancies),
        physical_source_available=physical_verification is not None,
        complete=bool(persisted),
    )
    return FeatureReproductionResult(
        session=session,
        symbol=symbol,
        decision_time=decision_time,
        status=status,
        physical_source_reference=(
            None
            if physical_verification is None
            else physical_verification.normalized_owner_reference
        ),
        comparisons=tuple(comparisons),
        discrepancies=tuple(all_discrepancies),
    )


def reproduce_t_plus_one_1030_target(
    *,
    symbol: str,
    decision_time: datetime,
    next_session: date,
    trading_calendar: TradingCalendarArtifact,
    source_bars: tuple[HistoricalNormalizedBar, ...],
    persisted: PersistedTargetObservation | None,
    physical_verification: PhysicalSourceVerification | None,
) -> TargetReproductionResult:
    """Independently reconstruct the frozen Decision reference and T+1 10:30 return."""

    _require_aware("decision_time", decision_time)
    decision_session = decision_time.astimezone(_SHANGHAI).date()
    resolved_next = trading_calendar.resolve_next_session_date(
        DecisionTime(decision_time)
    )
    if next_session != resolved_next:
        raise ValueError("Target must use the immediate next owner-resolved session")
    decision_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == decision_session
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_end <= decision_time
        )
    )
    if not decision_bars:
        raise ValueError("Decision reference bar is unavailable")
    if decision_bars[-1].event_end != decision_time:
        raise ValueError("Decision reference checkpoint is incomplete")
    checkpoint = datetime.combine(next_session, time(10, 30), _SHANGHAI).astimezone(
        decision_time.tzinfo
    )
    target_bars = _ordered_bars(
        tuple(
            item
            for item in source_bars
            if item.symbol == symbol
            and item.market_date == next_session
            and item.timeframe is Timeframe.MINUTE_5
            and time(9, 30)
            <= item.event_start.astimezone(_SHANGHAI).time().replace(tzinfo=None)
            and item.event_end <= checkpoint
        )
    )
    target_start = datetime.combine(
        next_session, time(9, 30), _SHANGHAI
    ).astimezone(decision_time.tzinfo)
    if (
        not target_bars
        or target_bars[0].event_start != target_start
        or target_bars[-1].event_end != checkpoint
    ):
        raise ValueError("T+1 10:30 checkpoint is incomplete")
    if physical_verification is not None:
        physical_bindings = set(physical_verification.normalized_bar_bindings)
        required_bindings = {
            (str(item.bar_id), item.content_hash)
            for item in (*decision_bars, *target_bars)
        }
        if not required_bindings.issubset(physical_bindings):
            raise ValueError("Target source bars are outside verified physical package")
    if any(left.event_end != right.event_start for left, right in zip(target_bars, target_bars[1:], strict=False)):
        raise ValueError("T+1 checkpoint bars are not contiguous")
    decision_source = (decision_bars[-1],)
    decision_ids, decision_hashes, _ = _source_lineage(decision_source)
    target_ids, target_hashes, _ = _source_lineage(target_bars)
    if set(decision_ids).intersection(target_ids):
        raise ValueError("Feature/Decision and Target lineage must be disjoint")
    decision_price = decision_bars[-1].close
    target_price = target_bars[-1].close
    if decision_price is None or target_price is None or decision_price <= 0:
        raise ValueError("Target reproduction requires positive source prices")
    target_return = target_price / decision_price - Decimal("1")
    discrepancies: list[str] = []
    if persisted is not None:
        if (
            persisted.decision_reference_price != decision_price
            or persisted.target_price != target_price
            or persisted.target_return != target_return
        ):
            discrepancies.append("TARGET_VALUE_MISMATCH")
        if (
            persisted.decision_source_ids != decision_ids
            or persisted.decision_source_hashes != decision_hashes
            or persisted.target_source_ids != target_ids
            or persisted.target_source_hashes != target_hashes
        ):
            discrepancies.append("TARGET_SOURCE_LINEAGE_MISMATCH")
        if (
            persisted.target_session != next_session
            or persisted.target_event_end != checkpoint
        ):
            discrepancies.append("TARGET_TEMPORAL_BOUNDARY_MISMATCH")
    status = _correctness_status(
        discrepancies=tuple(discrepancies),
        physical_source_available=physical_verification is not None,
        complete=persisted is not None,
    )
    return TargetReproductionResult(
        symbol=symbol,
        decision_time=decision_time,
        target_session=next_session,
        target_event_end=checkpoint,
        decision_reference_price=decision_price,
        target_price=target_price,
        target_return=target_return,
        decision_source_ids=decision_ids,
        target_source_ids=target_ids,
        status=status,
        physical_source_reference=(
            None
            if physical_verification is None
            else physical_verification.normalized_owner_reference
        ),
        trading_calendar_reference=ValidationArtifactReference(
            "PIT_TRADING_CALENDAR",
            trading_calendar.artifact_id,
            trading_calendar.content_hash,
        ),
        discrepancies=tuple(discrepancies),
    )


def _intraday_values(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> dict[str, tuple[Decimal, tuple[HistoricalNormalizedBar, ...]]]:
    if any(item.close is None or item.open is None for item in bars):
        raise ValueError("intraday correctness bars require complete prices")
    first, latest = bars[0], bars[-1]
    assert first.open is not None and latest.close is not None
    if first.open <= 0:
        raise ValueError("intraday first open must be positive")
    total_volume = sum((item.volume for item in bars), Decimal("0"))
    if total_volume <= 0 or any(item.amount is None for item in bars):
        raise ValueError("VWAP correctness bars require positive volume and amount")
    total_amount = sum(
        (item.amount for item in bars if item.amount is not None), Decimal("0")
    )
    vwap = total_amount / total_volume
    split = max(1, len(bars) // 2)
    first_bars = bars[:split]
    first_volume = sum((item.volume for item in first_bars), Decimal("0"))
    first_amount = sum(
        (item.amount for item in first_bars if item.amount is not None), Decimal("0")
    )
    if first_volume <= 0 or first_amount <= 0:
        raise ValueError("VWAP slope correctness window is unavailable")
    first_vwap = first_amount / first_volume
    return {
        "intraday_return_to_decision_time": (
            _quantize(latest.close / first.open - Decimal("1")),
            (first, latest) if first is not latest else (first,),
        ),
        "price_vs_vwap_return": (
            _quantize(latest.close / vwap - Decimal("1")),
            bars,
        ),
        "vwap_slope": (
            _quantize(vwap / first_vwap - Decimal("1")),
            bars,
        ),
    }


def _source_lineage(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    ids = tuple(str(item.bar_id) for item in bars)
    hashes = tuple(item.content_hash for item in bars)
    lineage = canonical_hash(
        {
            "normalized_source_bars": [
                {"bar_id": bar_id, "bar_hash": bar_hash}
                for bar_id, bar_hash in zip(ids, hashes, strict=True)
            ]
        }
    )
    return ids, hashes, lineage


def _ordered_bars(
    bars: tuple[HistoricalNormalizedBar, ...],
) -> tuple[HistoricalNormalizedBar, ...]:
    ordered = tuple(
        sorted(bars, key=lambda item: (item.event_start, item.event_end, str(item.bar_id)))
    )
    ids = tuple(str(item.bar_id) for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("correctness source bars must be unique")
    return ordered


def _correctness_status(
    *,
    discrepancies: tuple[str, ...],
    physical_source_available: bool,
    complete: bool,
) -> AlphaCorrectnessStatus:
    if discrepancies:
        return AlphaCorrectnessStatus.CORRECTNESS_FAILED
    if not complete:
        return AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    if not physical_source_available:
        return AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    return AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_SCALE, rounding=ROUND_HALF_EVEN)


def _require_aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = [
    "AlphaCorrectnessProof",
    "AlphaCorrectnessStatus",
    "FeatureCorrectnessComparison",
    "FeatureReproductionResult",
    "PersistedFeatureObservation",
    "PersistedTargetObservation",
    "PhysicalSourceVerification",
    "TargetReproductionResult",
    "build_alpha_correctness_proof",
    "reproduce_intraday_features",
    "reproduce_t_plus_one_1030_target",
    "establish_physical_reproduction",
]
