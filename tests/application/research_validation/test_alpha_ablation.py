from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_regime_alpha.application.research_validation.ablation import (
    AblationObservation,
    AblationProtocol,
    AblationVariant,
    AblationVariantKind,
    run_alpha_ablation_suite,
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
        "THEME",
        "VOLATILITY",
    }
    assert "NOT_FORMAL_ALPHA_EVIDENCE" in suite.limitations


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
