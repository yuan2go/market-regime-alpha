from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from market_regime_alpha.application.continuous_research.scope import (
    prepare_continuous_research_scope,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import AsOfTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.market_data import AssetType, Exchange, FormalPitStatus, PriceLimitState
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_artifacts import (
    HistoricalTradingEligibilityRecord,
    build_historical_trading_eligibility_artifact,
)
from market_regime_alpha.universe.operational import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from market_regime_alpha.universe.orderability import (
    OrderabilitySide,
    OrderabilityStatus,
    ResearchOrderabilityEvidence,
    default_research_orderability_policy,
)
from market_regime_alpha.universe.request_scoped import build_request_scoped_universe


NOW = datetime(2026, 8, 6, 6, 50, tzinfo=timezone.utc)
HASH = "sha256:" + "1" * 64


def _universe_record(symbol: str, *, included: bool) -> OperationalUniverseRecord:
    source = ArtifactId(f"source-{symbol}")
    return OperationalUniverseRecord(
        symbol=symbol,
        asset_type=AssetType.A_SHARE,
        exchange=Exchange.SH if symbol.endswith(".SH") else Exchange.SZ,
        membership_source="CONTROLLED_REQUEST_SCOPE_V1",
        listing_status=ListingStatus.LISTED,
        st_status=STStatus.NOT_ST,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        liquidity_evidence=OperationalLiquidityEvidence(
            lookback_sessions=20,
            observed_sessions=20,
            median_daily_amount=Decimal("250000000"),
            minimum_daily_amount=Decimal("100000000"),
            available_at=NOW,
            source_artifact_id=source,
            source_content_hash=HASH,
        ),
        history_sessions_observed=250,
        history_sessions_required=250,
        included=included,
        inclusion_reasons=("SOURCE_INCLUDED",) if included else (),
        exclusion_reasons=() if included else ("SOURCE_EXCLUDED",),
        source_artifact_references=((source, HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _request_scope():
    source = OperationalUniverseArtifact.create(
        decision_date=date(2026, 8, 6),
        effective_at=NOW,
        available_at=NOW,
        records=(
            _universe_record("000001.SZ", included=False),
            _universe_record("600000.SH", included=True),
        ),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=(
            (ArtifactId("source-000001.SZ"), HASH),
            (ArtifactId("source-600000.SH"), HASH),
        ),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    return build_request_scoped_universe(
        source=source,
        requested_symbols=("000001.SZ", "600000.SH", "688001.SH"),
        configuration_id=ArtifactId("request-scope-config"),
        configuration_hash=HASH,
    )


def _eligibility(*, exact_time: bool = True):
    as_of = AsOfTime(NOW if exact_time else NOW.replace(minute=49))
    return build_historical_trading_eligibility_artifact(
        source_dataset_id=DatasetId("eligibility-source"),
        policy_version="eligibility-v1",
        records=(
            HistoricalTradingEligibilityRecord(
                as_of=as_of,
                symbol="000001.SZ",
                status=TradingEligibilityStatus.INELIGIBLE,
                reasons=("SOURCE_INELIGIBLE",),
            ),
            HistoricalTradingEligibilityRecord(
                as_of=as_of,
                symbol="600000.SH",
                status=TradingEligibilityStatus.ELIGIBLE,
            ),
        ),
        policy_artifact_id=ArtifactId("eligibility-policy"),
    )


def _orderability(*, complete: bool):
    policy = default_research_orderability_policy()
    evidence = ResearchOrderabilityEvidence(
        symbol="600000.SH",
        observed_at=NOW,
        side=OrderabilitySide.BUY,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        price_limit_state=PriceLimitState.NORMAL,
        last_price=Decimal("10.00"),
        board_rule_id="main-board-v1" if complete else None,
        lot_size=100,
        in_continuous_auction=True,
        liquidity_sufficient=True,
        listing_rule_id="listed-v1",
        source_manifest_id=ArtifactId("orderability-manifest"),
        source_manifest_hash=HASH,
    )
    return policy.assess(evidence)


def test_scope_preserves_exclusions_and_fails_closed_on_missing_evidence() -> None:
    result = prepare_continuous_research_scope(
        request_scoped_universe=_request_scope(),
        eligibility_artifact=_eligibility(),
        decision_time=DecisionTime(NOW),
        orderability_assessments={"600000.SH": _orderability(complete=False)},
    )

    assert tuple(item.symbol for item in result.records) == (
        "000001.SZ",
        "600000.SH",
        "688001.SH",
    )
    assert result.record_for("000001.SZ").universe_included is False
    assert result.record_for("688001.SH").eligibility_status is TradingEligibilityStatus.UNKNOWN
    candidate = result.record_for("600000.SH")
    assert candidate.orderability_status is OrderabilityStatus.ORDERABILITY_UNKNOWN
    assert candidate.research_candidate_eligible is False
    assert result.entry_authority_granted is False


def test_scope_reuses_exact_eligibility_and_research_orderability_contracts() -> None:
    result = prepare_continuous_research_scope(
        request_scoped_universe=_request_scope(),
        eligibility_artifact=_eligibility(),
        decision_time=DecisionTime(NOW),
        orderability_assessments={"600000.SH": _orderability(complete=True)},
    )

    candidate = result.record_for("600000.SH")
    assert candidate.eligibility_status is TradingEligibilityStatus.ELIGIBLE
    assert candidate.orderability_status is OrderabilityStatus.ORDERABLE_FOR_RESEARCH
    assert candidate.research_candidate_eligible is True


def test_scope_does_not_carry_stale_eligibility_forward() -> None:
    result = prepare_continuous_research_scope(
        request_scoped_universe=_request_scope(),
        eligibility_artifact=_eligibility(exact_time=False),
        decision_time=DecisionTime(NOW),
        orderability_assessments={"600000.SH": _orderability(complete=True)},
    )

    candidate = result.record_for("600000.SH")
    assert candidate.eligibility_status is TradingEligibilityStatus.UNKNOWN
    assert "ELIGIBILITY_SNAPSHOT_MISSING" in candidate.reason_codes
    assert candidate.research_candidate_eligible is False
