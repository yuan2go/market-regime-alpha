from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.forecasting.contracts import CalibrationStatus
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.research_integration import (
    EmpiricalForecastBias,
    EmpiricalForecastStatus,
    SignalV4State,
    audit_feature_exposures,
    bind_candidate_set,
    project_empirical_forecast_v2,
    project_signal_v4,
)
from tests.research.platform_v2.conftest import (
    research_input_bundle as research_input_bundle,
)
from tests.research.platform_v2.test_candidate_discovery import _qualified, _run
from tests.research.state_system.test_pool import config, context, lineage, member
from tests.signals.test_engine import _run as _legacy_signal_run
from market_regime_alpha.research.state_system.pool import evaluate_dynamic_pool


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def _candidate_set(research_input_bundle) -> CandidateSet:
    return _run(_qualified(research_input_bundle))[3]


def _pool(symbols: tuple[str, ...]):
    return evaluate_dynamic_pool(
        state_context=context(),
        eligibility=tuple(member(symbol) for symbol in symbols),
        previous=None,
        configuration=config(),
        lineage=lineage(),
    ).pool


def test_candidate_binding_consumes_exact_pool_and_preserves_full_cross_section(
    research_input_bundle,
) -> None:
    candidates = _candidate_set(research_input_bundle)
    symbols = tuple(record.symbol for record in candidates.records)
    pool = _pool(symbols)

    binding = bind_candidate_set(
        candidate_set=candidates,
        dynamic_pool=pool,
        market_regime_state_id=pool.market_regime_state_id,
        etf_rotation_state_ids=pool.etf_rotation_state_ids,
        theme_rotation_state_ids=pool.theme_rotation_state_ids,
        capital_state_id=pool.capital_state_id,
        feature_bundle_id=ArtifactId("feature-bundle-1"),
        runtime_tick_id=pool.runtime_tick_id,
        available_at=pool.available_at,
        as_of_time=pool.decision_time,
        rule_version="candidate-binding-v1",
        configuration_version="1.0.0",
    )

    assert binding.dynamic_pool_id == pool.pool_id
    assert len(binding.records) == len(candidates.records) == len(pool.members)
    assert tuple(record.symbol for record in binding.records) == symbols


def test_candidate_binding_rejects_partial_top_k_or_future_artifact(
    research_input_bundle,
) -> None:
    candidates = _candidate_set(research_input_bundle)
    pool = _pool(tuple(record.symbol for record in candidates.records[:-1]))

    with pytest.raises(ValueError, match="complete Pool cross section"):
        bind_candidate_set(
            candidate_set=candidates,
            dynamic_pool=pool,
            market_regime_state_id=pool.market_regime_state_id,
            etf_rotation_state_ids=pool.etf_rotation_state_ids,
            theme_rotation_state_ids=pool.theme_rotation_state_ids,
            capital_state_id=pool.capital_state_id,
            feature_bundle_id=ArtifactId("feature-bundle-1"),
            runtime_tick_id=pool.runtime_tick_id,
            available_at=pool.available_at,
            as_of_time=pool.decision_time,
            rule_version="candidate-binding-v1",
            configuration_version="1.0.0",
        )


def test_signal_v4_writes_factor_coverage_not_confidence_and_reuses_identity() -> None:
    kwargs = {
        "symbol": "600000.SH",
        "candidate_binding_id": ArtifactId("candidate-binding-1"),
        "dynamic_pool_id": ArtifactId("dynamic-pool-1"),
        "feature_bundle_id": ArtifactId("feature-bundle-1"),
        "active_factors": ("MOMENTUM", "PRICE_ACTION"),
        "failed_factors": ("VOLUME",),
        "missing_factors": ("VWAP",),
        "signal_state": SignalV4State.WATCH,
        "rule_id": ArtifactId("signal-rule-v4"),
        "rule_version": "4.0.0",
        "configuration_id": ArtifactId("signal-config-v4"),
        "configuration_version": "4.0.0",
        "decision_time": NOW,
        "available_at": NOW,
    }

    first = project_signal_v4(**kwargs)
    replay = project_signal_v4(**kwargs)

    assert first.factor_coverage == Decimal("0.5")
    assert not hasattr(first, "confidence")
    assert "factor_coverage" in first.to_canonical_dict()
    assert first.signal_id == replay.signal_id


def test_signal_v4_rejects_future_available_at() -> None:
    with pytest.raises(ValueError, match="available_at"):
        project_signal_v4(
            symbol="600000.SH",
            candidate_binding_id=ArtifactId("candidate-binding-1"),
            dynamic_pool_id=ArtifactId("dynamic-pool-1"),
            feature_bundle_id=ArtifactId("feature-bundle-1"),
            active_factors=(),
            failed_factors=(),
            missing_factors=("MOMENTUM",),
            signal_state=SignalV4State.DATA_INSUFFICIENT,
            rule_id=ArtifactId("signal-rule-v4"),
            rule_version="4.0.0",
            configuration_id=ArtifactId("signal-config-v4"),
            configuration_version="4.0.0",
            decision_time=NOW,
            available_at=NOW + timedelta(seconds=1),
        )


def test_legacy_signal_reader_keeps_historical_confidence_field() -> None:
    historical = _legacy_signal_run().snapshots[0]
    decoded = type(historical).from_canonical_dict(historical.to_canonical_dict())

    assert decoded.confidence == historical.confidence
    assert "confidence" in decoded.to_canonical_dict()
    assert "factor_coverage" not in decoded.to_canonical_dict()


def test_forecast_remains_empirical_uncalibrated_and_probability_free() -> None:
    forecast = project_empirical_forecast_v2(
        symbol="600000.SH",
        forecast_horizon="NEXT_SESSION_1030",
        observation_time=NOW,
        as_of_time=NOW,
        available_at=NOW,
        historical_returns=(Decimal("-0.01"), Decimal("0.02"), Decimal("0.03")),
        data_coverage=Decimal("0.90"),
        minimum_sample_count=3,
        source_state_ids=(ArtifactId("market-state-1"),),
        dynamic_pool_id=ArtifactId("dynamic-pool-1"),
        model_id=ModelId("empirical-path-v2"),
        model_version="2.0.0",
        configuration_id=ArtifactId("forecast-config-v2"),
        configuration_version="2.0.0",
    )

    assert forecast.bias is EmpiricalForecastBias.UP_BIAS
    assert forecast.calibration_status is CalibrationStatus.NOT_CALIBRATED
    assert forecast.status is EmpiricalForecastStatus.AVAILABLE_FOR_RESEARCH
    assert "probability" not in forecast.to_canonical_dict()


def test_unavailable_sample_provider_fails_closed() -> None:
    forecast = project_empirical_forecast_v2(
        symbol="600000.SH",
        forecast_horizon="NEXT_SESSION_1030",
        observation_time=NOW,
        as_of_time=NOW,
        available_at=NOW,
        historical_returns=None,
        data_coverage=Decimal("0"),
        minimum_sample_count=3,
        source_state_ids=(ArtifactId("market-state-1"),),
        dynamic_pool_id=ArtifactId("dynamic-pool-1"),
        model_id=ModelId("empirical-path-v2"),
        model_version="2.0.0",
        configuration_id=ArtifactId("forecast-config-v2"),
        configuration_version="2.0.0",
    )

    assert forecast.bias is EmpiricalForecastBias.DATA_INSUFFICIENT
    assert forecast.status is EmpiricalForecastStatus.DATA_INSUFFICIENT
    assert forecast.historical_distribution == ()


def test_feature_lineage_audits_duplicate_exposure_without_changing_weights() -> None:
    audit = audit_feature_exposures(
        (
            "price_momentum_5d",
            "momentum_rank",
            "amount_expansion",
            "volume_confirmation",
            "theme_strength",
        ),
        audit_rule_version="exposure-audit-v1",
    )

    assert audit.duplicate_exposures == (("MOMENTUM", ("momentum_rank", "price_momentum_5d")),)
    assert audit.weights_changed is False
