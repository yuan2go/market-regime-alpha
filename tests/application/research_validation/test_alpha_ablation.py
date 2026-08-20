from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from market_regime_alpha.application.research_validation.ablation import (
    AblationObservation,
    AblationProtocol,
    AblationVariant,
    AblationVariantKind,
    run_alpha_ablation_suite,
    run_incremental_alpha_ablation_suite,
)
from market_regime_alpha.application.research_validation.common import (
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 12, tzinfo=UTC)


def _reference() -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "RESEARCH_PANEL_V2",
        ArtifactId("alpha-ablation-panel"),
        canonical_hash({"panel": "alpha-ablation"}),
    )


def _observations() -> tuple[AblationObservation, ...]:
    rows: list[AblationObservation] = []
    for session in range(6):
        for rank in range(8):
            price = Decimal(rank - 3)
            regime = Decimal("0.5") if session % 2 == 0 else Decimal("-0.5")
            gross = (
                price * Decimal("0.002")
                + regime * Decimal("0.001")
                + Decimal((rank + session) % 3) * Decimal("0.0004")
            )
            rows.append(
                AblationObservation(
                    observation_id=f"o-{session}-{rank}",
                    session_key=f"s-{session}",
                    symbol=f"{rank:06d}.SZ",
                    score=price,
                    realized_return=gross,
                    mfe=max(gross, Decimal("0")) + Decimal("0.004"),
                    mae=min(gross, Decimal("0")) - Decimal("0.003"),
                    selected=rank >= 6,
                    previous_selected=rank >= 6,
                    factor_values=(
                        (FactorFamily.MARKET_REGIME, "regime", regime),
                        (FactorFamily.PRICE, "price", price),
                    ),
                    cost_return=Decimal("0.0006"),
                    market_regime="RISK_ON" if session % 2 == 0 else "RISK_OFF",
                    liquidity_bucket="HIGH" if rank >= 4 else "LOW",
                    market_cap_bucket="LARGE" if rank >= 4 else "SMALL",
                    volatility_bucket="HIGH" if session >= 3 else "LOW",
                    theme="TECH" if rank % 2 == 0 else "FINANCE",
                    industry="I1" if rank % 2 == 0 else "I2",
                    trading_date=date(2026, 8, 1 + session),
                )
            )
    return tuple(rows)


def test_ablation_suite_uses_cross_sectional_sessions_costs_and_frozen_sequence() -> None:
    price = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    regime = AblationVariant.standard(
        AblationVariantKind.PRICE_VOLUME_MARKET_REGIME
    )
    protocol = AblationProtocol.create(
        protocol_version="alpha-proof-v1",
        variants=(price, regime),
        comparison_sequence=(price.variant_id, regime.variant_id),
        top_k=2,
        scoring_contract="EXACT_REGISTERED_FACTOR_SUM_V1",
        created_at=NOW,
    )

    suite = run_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observations=_observations(),
        score_functions={
            price.variant_id: lambda item, _variant: dict(
                (factor_id, value)
                for _family, factor_id, value in item.factor_values
            )["price"],
            regime.variant_id: lambda item, _variant: sum(
                value for _family, _factor_id, value in item.factor_values
            ),
        },
        created_at=NOW,
    )

    assert suite.authority is ResearchEvidenceAuthority.EXPLORATORY
    assert suite.comparison_sequence == (price.variant_id, regime.variant_id)
    assert len(suite.results) == 2
    assert suite.results[0].metrics.session_count == 6
    assert suite.results[0].metrics.ic is not None
    assert suite.results[0].metrics.icir is not None
    assert suite.results[0].metrics.gross_return is not None
    assert suite.results[0].metrics.cost_return == Decimal("0.0006")
    assert suite.results[0].metrics.net_return == (
        suite.results[0].metrics.gross_return - Decimal("0.0006")
    )
    assert suite.results[1].metrics.incremental_lift is not None
    assert {item.dimension for item in suite.slice_evaluations} == {
        "INDUSTRY",
        "LIQUIDITY",
        "MARKET_CAP",
        "MARKET_REGIME",
        "MONTH",
        "QUARTER",
        "THEME",
        "VOLATILITY",
        "YEAR",
    }
    assert "NOT_FORMAL_ALPHA_EVIDENCE" in suite.limitations


def test_incremental_ablation_consumes_ordered_session_batches() -> None:
    price = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    regime = AblationVariant.standard(
        AblationVariantKind.PRICE_VOLUME_MARKET_REGIME
    )
    protocol = AblationProtocol.create(
        protocol_version="incremental-alpha-proof-v1",
        variants=(price, regime),
        comparison_sequence=(price.variant_id, regime.variant_id),
        top_k=2,
        scoring_contract="WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2",
        created_at=NOW,
    )
    observations = _observations()
    sessions = tuple(
        tuple(item for item in observations if item.session_key == session_key)
        for session_key in sorted({item.session_key for item in observations})
    )

    first = run_incremental_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observation_sessions=iter(sessions),
        created_at=NOW,
    )
    second = run_incremental_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observation_sessions=iter(sessions),
        created_at=NOW,
    )

    assert first == second
    assert first.results[-1].metrics.sample_count == len(observations)
    assert first.results[-1].metrics.session_count == len(sessions)
    assert first.results[-1].metrics.incremental_lift is not None
    assert len(first.slice_evaluations) > 0


def test_v2_shared_constant_factor_is_neutral() -> None:
    price = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    through_theme = AblationVariant.standard(
        AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME
    )
    protocol = AblationProtocol.create(
        protocol_version="tie-aware-alpha-proof-v2",
        variants=(price, through_theme),
        comparison_sequence=(price.variant_id, through_theme.variant_id),
        top_k=1,
        scoring_contract="WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2",
        created_at=NOW,
    )
    observations = tuple(
        AblationObservation(
            observation_id=observation_id,
            session_key="constant-factor-session",
            symbol=symbol,
            score=raw_price,
            realized_return=realized,
            mfe=max(realized, Decimal("0")),
            mae=min(realized, Decimal("0")),
            selected=False,
            previous_selected=False,
            factor_values=(
                (FactorFamily.PRICE, "price", raw_price),
                (FactorFamily.THEME, "theme", Decimal("7")),
            ),
            cost_return=Decimal("0.001"),
            trading_date=date(2026, 8, 12),
        )
        for symbol, observation_id, raw_price, realized in (
            ("A", "z", Decimal("1"), Decimal("-0.01")),
            ("B", "y", Decimal("2"), Decimal("0.01")),
            ("C", "x", Decimal("3"), Decimal("0.03")),
        )
    )

    suite = run_incremental_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observation_sessions=(observations,),
        created_at=NOW,
    )

    baseline, augmented = (item.metrics for item in suite.results)
    assert augmented.top_k_return == baseline.top_k_return
    assert augmented.gross_return == baseline.gross_return
    assert augmented.net_return == baseline.net_return
    assert augmented.rank_ic == baseline.rank_ic
    assert augmented.incremental_lift == Decimal("0.0")


def test_ablation_protocol_rejects_unfrozen_or_duplicate_comparison_sequence() -> None:
    price = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    try:
        AblationProtocol.create(
            protocol_version="invalid",
            variants=(price,),
            comparison_sequence=(price.variant_id, price.variant_id),
            top_k=1,
            scoring_contract="TEST",
            created_at=NOW,
        )
    except ValueError as exc:
        assert "comparison sequence" in str(exc)
    else:
        raise AssertionError("duplicate comparison sequence must fail closed")


def test_variant_selection_drives_hit_rate_turnover_and_canonical_path_order() -> None:
    stable = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    rotating = AblationVariant.standard(AblationVariantKind.VOLUME_ONLY)
    protocol = AblationProtocol.create(
        protocol_version="adversarial-selection-v1",
        variants=(stable, rotating),
        comparison_sequence=(stable.variant_id, rotating.variant_id),
        top_k=1,
        scoring_contract="ADVERSARIAL_EXACT_SCORE_V1",
        created_at=NOW,
    )
    observations = tuple(
        AblationObservation(
            observation_id=f"{session}-{symbol}",
            session_key=f"session-{session}",
            symbol=symbol,
            score=Decimal("0"),
            realized_return=(
                Decimal("0.02") if symbol == "A" else Decimal("-0.02")
            ),
            mfe=Decimal("0.03"),
            mae=Decimal("-0.03"),
            selected=symbol == "A",
            previous_selected=False,
            factor_values=(
                (FactorFamily.PRICE, "stable", Decimal("1") if symbol == "A" else Decimal("0")),
                (
                    FactorFamily.VOLUME,
                    "rotating",
                    Decimal("1")
                    if symbol == ("A" if session % 2 == 0 else "B")
                    else Decimal("0"),
                ),
            ),
            trading_date=date(2026, 8, 10 + session),
        )
        for session in range(3)
        for symbol in ("A", "B")
    )
    score_functions = {
        stable.variant_id: lambda item, _variant: dict(
            (factor_id, value)
            for _family, factor_id, value in item.factor_values
        )["stable"],
        rotating.variant_id: lambda item, _variant: dict(
            (factor_id, value)
            for _family, factor_id, value in item.factor_values
        )["rotating"],
    }

    ordered = run_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observations=observations,
        score_functions=score_functions,
        created_at=NOW,
    )
    shuffled = run_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observations=tuple(reversed(observations)),
        score_functions=score_functions,
        created_at=NOW,
    )

    stable_metrics, rotating_metrics = (item.metrics for item in ordered.results)
    assert stable_metrics.hit_rate == Decimal("1.0")
    assert rotating_metrics.hit_rate == Decimal("2") / Decimal("3")
    assert stable_metrics.turnover == Decimal("0.0")
    assert rotating_metrics.turnover == Decimal("1.0")
    assert [item.metrics for item in shuffled.results] == [
        item.metrics for item in ordered.results
    ]


def test_ablation_path_metrics_reject_missing_canonical_session_dates() -> None:
    variant = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    protocol = AblationProtocol.create(
        protocol_version="missing-session-date-v1",
        variants=(variant,),
        top_k=1,
        scoring_contract="EXACT_SCORE_V1",
        created_at=NOW,
    )
    observation = AblationObservation(
        observation_id="missing-date",
        session_key="opaque-session",
        symbol="A",
        score=Decimal("1"),
        realized_return=Decimal("0.01"),
        mfe=None,
        mae=None,
        selected=True,
        previous_selected=False,
        factor_values=((FactorFamily.PRICE, "price", Decimal("1")),),
    )

    try:
        run_alpha_ablation_suite(
            protocol=protocol,
            panel_reference=_reference(),
            observations=(observation,),
            score_functions={variant.variant_id: lambda item, _variant: item.score},
            created_at=NOW,
        )
    except ValueError as exc:
        assert "canonical trading date" in str(exc)
    else:
        raise AssertionError("path metrics without canonical dates must fail closed")


def test_ablation_spread_does_not_reuse_top_names_as_bottom_names() -> None:
    variant = AblationVariant.standard(AblationVariantKind.PRICE_ONLY)
    protocol = AblationProtocol.create(
        protocol_version="disjoint-top-bottom-v1",
        variants=(variant,),
        top_k=2,
        scoring_contract="EXACT_SCORE_V1",
        created_at=NOW,
    )
    observations = tuple(
        AblationObservation(
            observation_id=f"one-session-{symbol}",
            session_key="one-session",
            symbol=symbol,
            score=score,
            realized_return=realized,
            mfe=None,
            mae=None,
            selected=True,
            previous_selected=False,
            factor_values=((FactorFamily.PRICE, "price", score),),
            trading_date=date(2026, 8, 12),
        )
        for symbol, score, realized in (
            ("A", Decimal("2"), Decimal("0.02")),
            ("B", Decimal("1"), Decimal("-0.01")),
        )
    )

    suite = run_alpha_ablation_suite(
        protocol=protocol,
        panel_reference=_reference(),
        observations=observations,
        score_functions={variant.variant_id: lambda item, _variant: item.score},
        created_at=NOW,
    )

    assert suite.results[0].metrics.top_k_return == Decimal("0.005")
    assert suite.results[0].metrics.spread is None
