from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    build_free_research_universe_snapshot,
)
from market_regime_alpha.universe.runtime_scope import (
    RuntimeEligibilityObservation,
    RuntimeScopeDecision,
    UniversePolicySelector,
    UniverseScopeKind,
    build_research_universe_policy,
    build_runtime_scope,
)


KNOWN_AT = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
AS_OF = datetime(2020, 1, 2, 6, 55, tzinfo=UTC)
HASH = canonical_hash({"source": "test"})


def _snapshot():
    return build_free_research_universe_snapshot(
        as_of_date=date(2020, 1, 2),
        known_at=KNOWN_AT,
        provider_id="provider-baostock-public",
        provider_contract="query_stock_basic/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST", ArtifactId("manifest-free-universe"), HASH
        ),
        raw_archive_id="archive-free-universe",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        rows=(
            _row("sz.000001", "平安银行", "1991-04-03", "", "1"),
            _row("sz.000002", "万科A", "1991-01-29", "", "1"),
            _row("sh.600001", "退市样本", "1990-12-19", "2019-12-31", "0"),
            {
                "code": "sh.689999",
                "code_name": "未知样本",
                "ipoDate": "",
                "outDate": "",
                "type": "",
                "status": "",
            },
        ),
    )


def _row(
    code: str, name: str, ipo_date: str, out_date: str, status: str
) -> dict[str, str]:
    return {
        "code": code,
        "code_name": name,
        "ipoDate": ipo_date,
        "outDate": out_date,
        "type": "1",
        "status": status,
    }


def _eligibility(
    symbol: str,
    *,
    is_st: bool | None = False,
    suspended: bool | None = False,
    history: int | None = 300,
    amount: Decimal | None = Decimal("200000000"),
) -> RuntimeEligibilityObservation:
    return RuntimeEligibilityObservation.create(
        symbol=symbol,
        observed_at=AS_OF,
        known_at=KNOWN_AT,
        included=True,
        listing_status="LISTED",
        is_st=is_st,
        suspended=suspended,
        history_sessions=history,
        median_daily_amount=amount,
        source_references=(
            ValidationArtifactReference(
                "ELIGIBILITY_FACT", ArtifactId(f"eligibility-{symbol}"), HASH
            ),
        ),
    )


def _policy(*, selectors: tuple[UniversePolicySelector, ...] | None = None):
    return build_research_universe_policy(
        policy_version="full-a-liquid-non-st-v1",
        selectors=selectors
        or (
            UniversePolicySelector(
                kind=UniverseScopeKind.FULL_A,
                selector_id="all-a-share-security-master",
                symbols=(),
            ),
        ),
        minimum_history_sessions=250,
        minimum_median_daily_amount=Decimal("100000000"),
        include_st=False,
        require_tradable=True,
        lot_size=100,
        data_authority="FREE_RESEARCH_DATA",
    )


def test_full_a_scope_preserves_included_excluded_unknown_and_provenance() -> None:
    receipt = build_runtime_scope(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master=_snapshot(),
        eligibility_observations=(
            _eligibility("000001.SZ"),
            _eligibility("000002.SZ", is_st=True),
        ),
        membership_snapshots=(),
        code_revision="d27bc355",
    )

    assert receipt.requested_symbols == ("000001.SZ",)
    assert receipt.record_for("000001.SZ").decision is RuntimeScopeDecision.INCLUDED
    assert receipt.record_for("000002.SZ").decision is RuntimeScopeDecision.EXCLUDED
    assert receipt.record_for("600001.SH").decision is RuntimeScopeDecision.EXCLUDED
    assert receipt.record_for("689999.SH").decision is RuntimeScopeDecision.UNKNOWN
    assert "ST_NOT_ALLOWED" in receipt.record_for("000002.SZ").reason_codes
    assert "FREE_DATA_EXPLORATORY" in receipt.limitations
    assert receipt.formal_pit is False
    assert len(receipt.input_references) == 3


@pytest.mark.parametrize(
    ("observation", "reason"),
    (
        (_eligibility("000001.SZ", suspended=True), "SUSPENDED"),
        (_eligibility("000001.SZ", history=20), "MINIMUM_HISTORY_NOT_MET"),
        (
            _eligibility("000001.SZ", amount=Decimal("1000")),
            "MINIMUM_LIQUIDITY_NOT_MET",
        ),
        (_eligibility("000001.SZ", suspended=None), "TRADABILITY_UNKNOWN"),
    ),
)
def test_scope_fails_closed_for_tradability_history_and_liquidity(
    observation: RuntimeEligibilityObservation, reason: str
) -> None:
    receipt = build_runtime_scope(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master=_snapshot(),
        eligibility_observations=(observation, _eligibility("000002.SZ")),
        membership_snapshots=(),
        code_revision="d27bc355",
    )

    record = receipt.record_for("000001.SZ")
    assert record.decision is not RuntimeScopeDecision.INCLUDED
    assert reason in record.reason_codes


def test_watchlist_absence_is_unknown_and_not_silently_dropped() -> None:
    watchlist = UniversePolicySelector(
        kind=UniverseScopeKind.WATCHLIST,
        selector_id="operator-watchlist-20200811",
        symbols=("000001.SZ", "999999.SZ"),
    )

    receipt = build_runtime_scope(
        policy=_policy(selectors=(watchlist,)),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master=_snapshot(),
        eligibility_observations=(_eligibility("000001.SZ"),),
        membership_snapshots=(),
        code_revision="d27bc355",
    )

    assert receipt.record_for("999999.SZ").decision is RuntimeScopeDecision.UNKNOWN
    assert "SECURITY_MASTER_RECORD_MISSING" in receipt.record_for(
        "999999.SZ"
    ).reason_codes


def test_historical_free_snapshot_cannot_be_used_before_recorded_known_at() -> None:
    with pytest.raises(ValueError, match="not known at the requested build time"):
        build_runtime_scope(
            policy=_policy(),
            as_of=AS_OF,
            built_at=datetime(2020, 1, 2, 7, 0, tzinfo=UTC),
            security_master=_snapshot(),
            eligibility_observations=(),
            membership_snapshots=(),
            code_revision="d27bc355",
        )


def test_explicit_exclusion_wins_over_unknown_and_otherwise_passing_facts() -> None:
    excluded = RuntimeEligibilityObservation.create(
        symbol="000001.SZ",
        observed_at=AS_OF,
        known_at=KNOWN_AT,
        included=False,
        listing_status="UNKNOWN",
        is_st=None,
        suspended=False,
        history_sessions=300,
        median_daily_amount=Decimal("200000000"),
        source_references=_eligibility("000001.SZ").source_references,
    )

    receipt = build_runtime_scope(
        policy=_policy(),
        as_of=AS_OF,
        built_at=KNOWN_AT,
        security_master=_snapshot(),
        eligibility_observations=(excluded, _eligibility("000002.SZ")),
        membership_snapshots=(),
        code_revision="phase-d-exclusion-priority",
    )

    record = receipt.record_for("000001.SZ")
    assert record.decision is RuntimeScopeDecision.EXCLUDED
    assert "PROVIDER_EXCLUDED" in record.reason_codes
    assert "LISTING_STATUS_UNKNOWN" in record.reason_codes
