from __future__ import annotations

from datetime import UTC, date, datetime

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactCoverageGap,
    HistoricalSecurityFactKind,
    HistoricalSecurityFactsOwner,
)


SOURCE = ValidationArtifactReference(
    "RAW_PROVIDER_REQUEST",
    ArtifactId("historical-facts-source"),
    canonical_hash({"source": "historical-facts"}),
)


def _fact(
    kind: HistoricalSecurityFactKind,
    *,
    effective: date,
    published: date | None,
    values: dict[str, str],
) -> HistoricalSecurityFact:
    return HistoricalSecurityFact.create(
        fact_kind=kind,
        symbol="600000.SH",
        effective_date=effective,
        published_date=published,
        values=values,
        source_reference=SOURCE,
        reason_codes=("REAL_FREE_PROVIDER_OBSERVATION",),
    )


def _owner(*, include_gap: bool = False) -> HistoricalSecurityFactsOwner:
    facts = (
        _fact(
            HistoricalSecurityFactKind.INDUSTRY,
            effective=date(2024, 12, 30),
            published=None,
            values={"industry": "J66货币金融服务", "classification": "证监会行业分类"},
        ),
        _fact(
            HistoricalSecurityFactKind.SHARE_CAPITAL,
            effective=date(2024, 9, 30),
            published=date(2024, 10, 30),
            values={"total_shares": "29352080397", "liquid_shares": "29352080397"},
        ),
        _fact(
            HistoricalSecurityFactKind.SHARE_CAPITAL,
            effective=date(2024, 12, 31),
            published=date(2025, 4, 30),
            values={"total_shares": "29352080397", "liquid_shares": "29352080397"},
        ),
        _fact(
            HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
            effective=date(2025, 6, 18),
            published=None,
            values={
                "adjustment_factor": "1.23",
                "back_adjust_factor": "1.23",
                "forward_adjust_factor": "0.81",
            },
        ),
        _fact(
            HistoricalSecurityFactKind.DIVIDEND_EVENT,
            effective=date(2025, 6, 18),
            published=date(2025, 4, 1),
            values={
                "cash_dividend_per_share_before_tax": "0.1",
                "stock_dividend_per_share": "0",
                "reserve_to_stock_per_share": "0",
            },
        ),
    )
    return HistoricalSecurityFactsOwner.create(
        known_at=datetime(2026, 8, 13, tzinfo=UTC),
        provider_id="provider-baostock-public",
        provider_contracts=(
            "baostock-query-adjust-factor/v1",
            "baostock-query-dividend-data/v1",
            "baostock-query-profit-data/v1",
            "baostock-query-stock-industry/v1",
        ),
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("historical-facts-manifest"),
            canonical_hash({"manifest": "historical-facts"}),
        ),
        raw_archive_id="historical-facts-archive",
        facts=facts,
        requested_symbols=("600000.SH",),
        acquisition_start_date=date(2025, 1, 1),
        acquisition_end_date=date(2025, 12, 31),
        universe_scope_references=(
            ValidationArtifactReference(
                "HISTORICAL_CONSTITUENT_TIMELINE",
                ArtifactId("historical-facts-test-timeline"),
                canonical_hash({"timeline": "historical-facts-test"}),
            ),
        ),
        coverage_gaps=(
            (
                HistoricalSecurityFactCoverageGap.create(
                    fact_kind=HistoricalSecurityFactKind.DIVIDEND_EVENT,
                    symbol="600000.SH",
                    coverage_start=date(2025, 1, 1),
                    coverage_end=date(2025, 12, 31),
                    raw_row_hash=canonical_hash({"raw_row": "unresolved"}),
                    source_reference=SOURCE,
                    reason_codes=("CORPORATE_ACTION_PROVIDER_ROW_UNRESOLVED",),
                ),
            )
            if include_gap
            else ()
        ),
    )


def test_historical_facts_resolve_only_effective_and_published_rows() -> None:
    owner = _owner()

    assert owner.requested_symbols == ("600000.SH",)
    assert owner.acquisition_start_date == date(2025, 1, 1)
    assert owner.acquisition_end_date == date(2025, 12, 31)
    assert owner.universe_scope_references[0].artifact_kind == (
        "HISTORICAL_CONSTITUENT_TIMELINE"
    )

    assert owner.industry_as_of("600000.SH", date(2025, 1, 2)) is not None
    early = owner.share_capital_as_of("600000.SH", date(2025, 1, 2))
    late = owner.share_capital_as_of("600000.SH", date(2025, 5, 2))

    assert early is not None and early.effective_date == date(2024, 9, 30)
    assert late is not None and late.effective_date == date(2024, 12, 31)
    assert owner.share_capital_as_of("600000.SH", date(2024, 10, 1)) is None


def test_historical_facts_find_corporate_actions_without_current_backfill() -> None:
    owner = _owner()

    assert owner.corporate_actions(
        "600000.SH",
        after=date(2025, 6, 17),
        through=date(2025, 6, 18),
    ) == tuple(
        item
        for item in owner.facts
        if item.fact_kind
        in {
            HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
            HistoricalSecurityFactKind.DIVIDEND_EVENT,
        }
    )
    assert (
        owner.corporate_actions(
            "600000.SH",
            after=date(2025, 6, 18),
            through=date(2025, 6, 19),
        )
        == ()
    )
    assert HistoricalSecurityFactsOwner.from_canonical_dict(owner.to_canonical_dict()) == owner


def test_historical_fact_coverage_gap_fails_closed_for_intersecting_interval() -> None:
    owner = _owner(include_gap=True)

    assert len(
        owner.corporate_action_gaps(
            "600000.SH",
            after=date(2025, 6, 17),
            through=date(2025, 6, 18),
        )
    ) == 1
    assert owner.corporate_action_gaps(
        "600000.SH",
        after=date(2026, 1, 1),
        through=date(2026, 1, 2),
    ) == ()
