from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from market_regime_alpha.application.historical_corpus.alpha_discovery import (
    AlphaFactorRole,
    aggregate_alpha_discovery_evaluations,
    canonical_alpha_factor_registry,
    evaluate_alpha_discovery_session,
)
from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_phase_e3_feature_configuration,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


AT = datetime(2026, 8, 20, 7, tzinfo=UTC)


def test_factor_registry_covers_every_canonical_output_once() -> None:
    owner = create_phase_e3_feature_configuration()
    registry = canonical_alpha_factor_registry(owner)
    owner_keys = {
        (definition.feature_id, output.output_id)
        for definition in owner.definitions
        for output in definition.output_schema
    }

    assert {(item.feature_id, item.output_id) for item in registry} == owner_keys
    assert len(registry) == len(owner_keys)
    assert any(
        item.output_id == "return_3"
        and item.family == "PRICE_RETURN"
        and item.role is AlphaFactorRole.NUMERIC_RANKED
        for item in registry
    )
    assert any(
        item.output_id == "sma_20"
        and item.role is AlphaFactorRole.RAW_LEVEL_DIAGNOSTIC
        for item in registry
    )
    assert any(
        item.output_id == "turnover_expansion"
        and item.role is AlphaFactorRole.NUMERIC_RANKED
        for item in registry
    )


def test_discovery_session_keeps_integrity_hard_and_evaluates_registered_variants() -> None:
    panel = _panel()

    evaluation = evaluate_alpha_discovery_session(panel=panel)
    factors = {item["factor_id"]: item for item in evaluation.factor_results}
    variants = {item["variant_id"]: item for item in evaluation.policy_results}

    assert evaluation.integrity_population_count == 11
    assert factors["technical.price_action.v1:return_3"]["observed_count"] == 11
    assert factors["technical.price_action.v1:return_3"]["rank_ic"] is not None
    assert {
        "CURRENT_HARD_CHAIN",
        "HARD_INTEGRITY_PRICE_RETURN",
        "HARD_INTEGRITY_PRICE_VOLUME_TREND",
        "SOFT_CONTEXT_CANDIDATE",
        "NO_PREDICTIVE_GATES",
    }.issubset(variants)
    assert variants["NO_PREDICTIVE_GATES"]["before_count"] == 11
    assert variants["NO_PREDICTIVE_GATES"]["after_count"] == 11
    assert variants["CURRENT_HARD_CHAIN"]["after_count"] == 6
    assert "REJECTED" not in variants["NO_PREDICTIVE_GATES"]["symbols"]
    assert {
        (item["gate_id"], item["mode"])
        for item in evaluation.gate_results
    } >= {
        ("MARKET_REGIME", "CURRENT_HARD_GATE"),
        ("MARKET_REGIME", "SOFT_FEATURE"),
        ("MARKET_REGIME", "NO_PREDICTIVE_GATE"),
        ("THEME", "CURRENT_HARD_GATE"),
        ("CAPITAL", "CURRENT_HARD_GATE"),
        ("DYNAMIC_POOL", "CURRENT_HARD_GATE"),
    }

    aggregate = aggregate_alpha_discovery_evaluations(
        tuple(
            (date(2025, 1, 2) + timedelta(days=index), evaluation)
            for index in range(21)
        )
    )
    assert aggregate["session_count"] == 21
    assert aggregate["multiple_testing"]["method"] == "BENJAMINI_HOCHBERG"
    assert {
        item["gate_id"] for item in aggregate["gate_dispositions"]
    } == {"MARKET_REGIME", "THEME", "CAPITAL", "DYNAMIC_POOL"}
    assert {
        item["disposition"] for item in aggregate["gate_dispositions"]
    } <= {"KEEP_AS_HARD_GATE", "DEMOTE_TO_FACTOR", "RETEST", "RETIRE"}
    assert aggregate["evidence_ceiling"]["formal_oos"] is False


def _panel() -> HistoricalSessionComponent:
    rows = []
    for index in range(12):
        symbol = "REJECTED" if index == 0 else f"S{index:02d}"
        integrity = index != 0
        candidate_passed = 1 <= index <= 6
        rows.append(
            {
                "symbol": symbol,
                "target_return": str((index - 5) / 1000),
                "cost_return": "0.0021",
                "mfe": "0.01",
                "mae": "-0.01",
                "capacity_ceiling": "1000000",
                "selected": candidate_passed and index >= 4,
                "candidate_diagnostic": {
                    "selection_status": (
                        "SELECTED" if candidate_passed and index >= 4 else
                        "WATCHLIST" if candidate_passed else "REJECTED"
                    ),
                    "rank": index if candidate_passed else None,
                    "score": str(index / 12) if candidate_passed else None,
                    "reason_codes": [
                        "CONTROLLED_CANDIDATE_GATES_PASSED"
                        if candidate_passed else "MARKET_REGIME_PROHIBITS_RISK"
                    ],
                },
                "gate_diagnostics": {
                    "hard_integrity": {
                        "passed": integrity,
                        "decision": "INCLUDED" if integrity else "EXCLUDED",
                        "reason_codes": [
                            "TRADING_ELIGIBILITY_SATISFIED"
                            if integrity else "SUSPENDED"
                        ],
                    },
                    "predictive": {
                        "market_regime": {
                            "passed": candidate_passed,
                            "score": str(index / 12),
                        },
                        "theme": {
                            "passed": index % 2 == 0,
                            "score": str(index / 12),
                        },
                        "capital": {
                            "passed": index % 3 == 0,
                            "score": str(index / 12),
                        },
                        "dynamic_pool": {
                            "passed": integrity,
                            "score": "1" if integrity else "0",
                            "confounded_with_hard_integrity": True,
                        },
                    },
                },
                "research_features": [
                    {
                        "feature_id": "technical.price_action.v1",
                        "output_id": "return_3",
                        "state": "AVAILABLE",
                        "value": str(index),
                    },
                    {
                        "feature_id": "technical.volume_amount_structure.v1",
                        "output_id": "amount_ratio_5",
                        "state": "AVAILABLE",
                        "value": str(index % 4),
                    },
                    {
                        "feature_id": "technical.moving_average.v2",
                        "output_id": "ma_slope_20",
                        "state": "AVAILABLE",
                        "value": str(index % 5),
                    },
                ],
                "market_regime": "RISK_ON",
                "liquidity_bucket": "HIGH",
                "market_cap_bucket": "LARGE_GTE_CNY_50B",
                "volatility_bucket": "NORMAL",
                "theme": "GLOBAL",
                "industry": "TEST",
            }
        )
    return HistoricalSessionComponent.create(
        run_id=ArtifactId("alpha-discovery-run"),
        session_id=ArtifactId("alpha-discovery-session"),
        trading_date=date(2025, 1, 2),
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        source_max_event_time=AT,
        materialized_at=AT,
        source_references=(
            ValidationArtifactReference(
                "HISTORICAL_FEATURE",
                ArtifactId("feature"),
                f"sha256:{'a' * 64}",
            ),
        ),
        payload={"rows": rows},
    )
