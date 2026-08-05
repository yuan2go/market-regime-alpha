from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.controlled_operation.entry_blocker import (
    load_controlled_entry_blocker,
)
from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.forecasting import PATH_FORECAST_CONFIG_SCHEMA, PathForecastConfig
from market_regime_alpha.forecasting.contracts import PathForecastStatus
from market_regime_alpha.signals import (
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)
from market_regime_alpha.strategies.entry import EntryBarrierSpec, build_entry_path_target_contract
from tests.features.test_materialization_runner_v2 import CREATED_AT, DECISION_TIME
from tests.features.test_operational_overlay import _composition


UTC = timezone.utc


def _path_configuration() -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="controlled-path-profile-v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a_share_1455_v1",
        decision_time_local="10:30",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=build_entry_path_target_contract(
            EntryBarrierSpec(
                upper_return=0.03,
                lower_return=-0.02,
                horizon_sessions=5,
                price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            )
        ),
        horizon_label="5_TRADING_SESSIONS",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=20,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def test_controlled_signal_path_and_entry_are_v3_insufficient_and_blocked(
    tmp_path: Path,
) -> None:
    (
        static,
        overlay,
        _,
        static_features,
        intraday_features,
        daily,
        minute,
        candidates,
        calendar,
    ) = _composition(tmp_path)
    signal_output = SignalStageHandler(
        configuration=canonical_signal_model_configuration_v2(),
        output_root=tmp_path / "signals",
        mapping_configuration=canonical_signal_input_mapping_v2(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC)
        ),
        feature_set_configuration=static_features.artifact.feature_set,
        requirement_policy=canonical_all_factors_required_policy(),
        freshness_policy=canonical_signal_freshness_policy(trading_calendar=calendar),
    ).run_controlled_v2(
        candidate_set=candidates,
        static_bundle=static,
        static_feature_bundle=static_features,
        daily_dataset=daily,
        intraday_overlay=overlay,
        intraday_feature_bundle=intraday_features,
        minute_dataset=minute,
        trading_calendar=calendar,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="controlled-test",
    )
    path_output = PathForecastStageHandler(
        configuration=_path_configuration(),
        output_root=tmp_path / "forecasts",
    ).run_controlled(signal=signal_output.signal)
    blocker, blocker_path = EntryAssessmentStageHandler(
        authority_ceiling=LifecycleAuthorityCeiling()
    ).run_controlled(
        signal=signal_output.signal,
        forecasts=path_output.forecasts,
        output_root=tmp_path / "entry",
        created_at=CREATED_AT,
    )

    assert signal_output.signal.artifact.candidate_feature_view.schema_version == (
        "candidate-feature-view-v2"
    )
    assert all(not batch.samples for batch in path_output.sample_batches)
    assert all(
        item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT
        for item in path_output.forecasts
    )
    assert blocker.assessment_state == "BLOCKED"
    assert "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" in blocker.reason_codes
    assert load_controlled_entry_blocker(blocker_path) == blocker
