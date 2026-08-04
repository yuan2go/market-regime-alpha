from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data import (
    AdjustmentFactorEvidence,
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)


UTC = timezone.utc
SESSION_START = datetime(2026, 8, 3, 1, 30, tzinfo=UTC)
SESSION_END = datetime(2026, 8, 3, 7, 0, tzinfo=UTC)
AVAILABLE_AT = datetime(2026, 8, 3, 7, 1, tzinfo=UTC)
SOURCE_HASH = "sha256:" + "1" * 64


def _raw_bar(**overrides: object) -> CanonicalMarketBar:
    values: dict[str, object] = {
        "symbol": "600000.SH",
        "exchange": Exchange.SH,
        "asset_type": AssetType.A_SHARE,
        "timeframe": Timeframe.DAILY,
        "market_date": date(2026, 8, 3),
        "event_start": SESSION_START,
        "event_end": SESSION_END,
        "available_at": AVAILABLE_AT,
        "open": Decimal("10.00"),
        "high": Decimal("10.80"),
        "low": Decimal("9.90"),
        "close": Decimal("10.50"),
        "previous_close": Decimal("9.95"),
        "volume": Decimal("123400"),
        "volume_unit": VolumeUnit.SHARES,
        "amount": Decimal("1288888.12"),
        "turnover_rate": Decimal("0.0123"),
        "adjustment_mode": AdjustmentMode.RAW,
        "adjustment_factor": Decimal("1"),
        "trading_status": TradingStatus.TRADING,
        "price_limit_state": PriceLimitState.NORMAL,
        "source_artifact_id": ArtifactId("source-600000-20260803"),
        "source_content_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return CanonicalMarketBar.create(**values)  # type: ignore[arg-type]


def test_market_bar_is_content_addressed_and_round_trips() -> None:
    bar = _raw_bar()

    restored = CanonicalMarketBar.from_canonical_dict(bar.to_canonical_dict())

    assert restored == bar
    assert str(bar.bar_id).startswith("market-bar-")
    assert bar.content_hash.startswith("sha256:")
    assert isinstance(bar.close, Decimal)
    assert isinstance(bar.volume, Decimal)


def test_market_bar_decimal_identity_is_canonical_and_reader_is_strict() -> None:
    canonical = _raw_bar(open=Decimal("10.0"), close=Decimal("10.5000"))
    equivalent = _raw_bar(open=Decimal("10.00"), close=Decimal("10.5"))

    assert canonical.bar_id == equivalent.bar_id
    assert canonical.content_hash == equivalent.content_hash
    assert canonical.to_canonical_dict()["open"] == "10"
    assert canonical.to_canonical_dict()["close"] == "10.5"

    payload = canonical.to_canonical_dict()
    payload["open"] = "10.00"
    with pytest.raises(ValueError, match="canonical decimal"):
        CanonicalMarketBar.from_canonical_dict(payload)

    payload = canonical.to_canonical_dict()
    payload["open"] = 10
    with pytest.raises(ValueError, match="canonical decimal"):
        CanonicalMarketBar.from_canonical_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("high", Decimal("9.99"), "high"),
        ("low", Decimal("10.01"), "low"),
        ("volume", Decimal("-1"), "volume"),
        ("amount", Decimal("-0.01"), "amount"),
        ("turnover_rate", Decimal("-0.1"), "turnover_rate"),
    ],
)
def test_market_bar_rejects_invalid_price_and_quantity_relations(
    field: str, value: Decimal, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _raw_bar(**{field: value})


def test_market_bar_rejects_float_prices_and_noncanonical_symbol() -> None:
    with pytest.raises(TypeError, match="open must be Decimal"):
        _raw_bar(open=10.0)
    with pytest.raises(ValueError, match="symbol exchange suffix"):
        _raw_bar(symbol="600000.SZ")


@pytest.mark.parametrize(
    "field",
    ["event_start", "event_end", "available_at"],
)
def test_market_bar_requires_canonical_utc_whole_second_time(field: str) -> None:
    with pytest.raises(ValueError, match="UTC"):
        _raw_bar(**{field: SESSION_START.astimezone(timezone(timedelta(hours=8)))})
    with pytest.raises(ValueError, match="whole-second"):
        _raw_bar(**{field: SESSION_START.replace(microsecond=1)})


def test_market_bar_rejects_future_availability_and_bad_minute_duration() -> None:
    with pytest.raises(ValueError, match="available_at cannot precede event_end"):
        _raw_bar(available_at=SESSION_END - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timeframe duration"):
        _raw_bar(
            timeframe=Timeframe.MINUTE_5,
            event_start=SESSION_START,
            event_end=SESSION_START + timedelta(minutes=4),
            available_at=SESSION_START + timedelta(minutes=4),
        )


def test_raw_bar_rejects_non_unit_adjustment_factor() -> None:
    with pytest.raises(ValueError, match="RAW adjustment factor"):
        _raw_bar(adjustment_factor=Decimal("1.1"))


def test_adjustment_factor_and_policy_are_content_addressed() -> None:
    factor = AdjustmentFactorEvidence.create(
        symbol="600000.SH",
        exchange=Exchange.SH,
        effective_date=date(2026, 8, 1),
        available_at=datetime(2026, 8, 2, 10, 0, tzinfo=UTC),
        factor=Decimal("1.025"),
        source_artifact_id=ArtifactId("adjustment-source-1"),
        source_content_hash="sha256:" + "2" * 64,
    )
    policy = PriceAdjustmentPolicy.create(
        policy_version="1.0.0",
        mode=AdjustmentMode.PIT_ADJUSTED,
        factors=(factor,),
        limitations=("PUBLIC_FACTOR_EVIDENCE_EXPLORATORY_ONLY",),
    )

    assert AdjustmentFactorEvidence.from_canonical_dict(
        factor.to_canonical_dict()
    ) == factor

    equivalent = AdjustmentFactorEvidence.create(
        symbol="600000.SH",
        exchange=Exchange.SH,
        effective_date=date(2026, 8, 1),
        available_at=datetime(2026, 8, 2, 10, 0, tzinfo=UTC),
        factor=Decimal("1.0250"),
        source_artifact_id=ArtifactId("adjustment-source-1"),
        source_content_hash="sha256:" + "2" * 64,
    )
    assert equivalent.factor_id == factor.factor_id

    payload = factor.to_canonical_dict()
    payload["factor"] = "1.0250"
    with pytest.raises(ValueError, match="canonical decimal"):
        AdjustmentFactorEvidence.from_canonical_dict(payload)
    assert PriceAdjustmentPolicy.from_canonical_dict(
        policy.to_canonical_dict()
    ) == policy
    assert policy.factor_for(
        symbol="600000.SH",
        market_date=date(2026, 8, 3),
        decision_time=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
    ) == factor


def test_pit_policy_rejects_future_factor_and_missing_symbol_factor() -> None:
    factor = AdjustmentFactorEvidence.create(
        symbol="600000.SH",
        exchange=Exchange.SH,
        effective_date=date(2026, 8, 1),
        available_at=datetime(2026, 8, 3, 3, 0, tzinfo=UTC),
        factor=Decimal("1.025"),
        source_artifact_id=ArtifactId("adjustment-source-1"),
        source_content_hash="sha256:" + "2" * 64,
    )
    policy = PriceAdjustmentPolicy.create(
        policy_version="1.0.0",
        mode=AdjustmentMode.PIT_ADJUSTED,
        factors=(factor,),
        limitations=("PUBLIC_FACTOR_EVIDENCE_EXPLORATORY_ONLY",),
    )

    with pytest.raises(ValueError, match="available after DecisionTime"):
        policy.factor_for(
            symbol="600000.SH",
            market_date=date(2026, 8, 3),
            decision_time=datetime(2026, 8, 3, 2, 0, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="factor is not established"):
        policy.factor_for(
            symbol="000001.SZ",
            market_date=date(2026, 8, 3),
            decision_time=datetime(2026, 8, 3, 4, 0, tzinfo=UTC),
        )


def test_research_back_adjusted_policy_cannot_enter_decision_runtime() -> None:
    policy = PriceAdjustmentPolicy.create(
        policy_version="1.0.0",
        mode=AdjustmentMode.RESEARCH_BACK_ADJUSTED,
        factors=(),
        limitations=(
            "FORMAL_PIT_NOT_ESTABLISHED",
            "RESEARCH_BACK_ADJUSTED_NOT_DECISION_RUNTIME_ELIGIBLE",
        ),
    )

    with pytest.raises(ValueError, match="cannot enter Decision Runtime"):
        policy.validate_for_decision_runtime()


def test_manual_identity_or_hash_tamper_is_detected() -> None:
    payload = _raw_bar().to_canonical_dict()
    payload["content_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="payload hash mismatch"):
        CanonicalMarketBar.from_canonical_dict(payload)
