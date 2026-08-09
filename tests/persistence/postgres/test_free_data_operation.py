from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.free_data_operation import (
    FreeDataBlockedArtifact,
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataPreparationRequest,
    FreeDataOperationService,
    publish_free_data_blocked,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.features.technical.catalog import (
    intraday_overlay_feature_set,
    static_technical_feature_set,
)
from market_regime_alpha.forecasting import PATH_FORECAST_CONFIG_SCHEMA, PathForecastConfig
from market_regime_alpha.market_data import AssetType
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.signals import (
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)
from market_regime_alpha.strategies.entry import (
    EntryBarrierSpec,
    build_entry_path_target_contract,
)
from tests.application.daily_loop.public_fixture import DECISION
from tests.application.daily_loop.test_runner import _qualified_stage_clients


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")
HASH = "sha256:" + "a" * 64


def test_postgres_free_data_prepare_is_idempotent_and_never_writes_sqlite(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    policy, history, status, quote = _qualified_stage_clients()
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("free-data-config-calendar"),
        market="A_SHARE",
        calendar_version="free-data-test-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=(DECISION.value.date() - timedelta(days=offset)),
                session_close=datetime.combine(
                    DECISION.value.date() - timedelta(days=offset),
                    time(15),
                    tzinfo=SHANGHAI,
                ),
            )
            for offset in range(30, -1, -1)
        ),
    )
    configuration = ControlledOperationRuntimeConfiguration.create(
        static_feature_set=static_technical_feature_set(
            effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)
        ),
        intraday_feature_set=intraday_overlay_feature_set(
            effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)
        ),
        research=ControlledResearchPipelineConfig.create(
            candidate_discovery=ControlledCandidateDiscoveryConfig.create(
                top_n=5,
                minimum_candidate_population=5,
            )
        ),
        signal_model=canonical_signal_model_configuration_v2(),
        signal_mapping=canonical_signal_input_mapping_v2(
            effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)
        ),
        signal_requirement=canonical_all_factors_required_policy(),
        signal_freshness=canonical_signal_freshness_policy(
            trading_calendar=calendar
        ),
        path_forecast=_path_config(),
    )
    configuration_path = publish_controlled_runtime_configuration(
        root=tmp_path / "runtime-configurations",
        artifact=configuration,
    )
    settings = DatabaseSettings.from_sources(
        database_url=os.environ["MARKET_REGIME_ALPHA_TEST_DATABASE_URL"],
        environ={},
    )
    repositories = RepositoryFactory(
        settings,
        postgres_factory=postgres_factory,
    )
    request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.SMOKE,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DECISION,
        created_at=datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
        code_revision="postgres-free-data-test",
        instruments=tuple(
            FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE)
            for symbol in policy.symbols
        ),
        membership_source="POSTGRES_FREE_DATA_TEST",
        minimum_history_sessions=21,
        liquidity_lookback_sessions=21,
        minimum_median_daily_amount=Decimal("1"),
        configuration_hash=configuration.configuration_hash,
    )
    observed_at = [datetime(2025, 2, 3, 14, 54, 30, tzinfo=SHANGHAI)]
    service = FreeDataOperationService(
        repositories=repositories,
        output_root=tmp_path / "operation",
        code_revision="postgres-free-data-test",
        clock=lambda: observed_at[0],
        live_profile=TencentFreeOperationalProfile(
            history_client=history,
            security_status_client=status,
            current_client=quote,
        ),
    )

    first = service.prepare(
        request=request,
        runtime_configuration_path=configuration_path,
        idempotency_key="postgres-free-data-smoke",
    )
    repeated = service.prepare(
        request=request,
        runtime_configuration_path=configuration_path,
        idempotency_key="postgres-free-data-smoke",
    )
    observed_at[0] = datetime(2025, 2, 3, 14, 55, tzinfo=SHANGHAI)
    execution = service.run(
        request=request,
        runtime_configuration_path=configuration_path,
        idempotency_key="postgres-free-data-smoke",
    )

    assert repeated.prepared_inputs.manifest == first.prepared_inputs.manifest
    assert repeated.controlled_command == first.controlled_command
    assert (history.calls, status.calls, quote.calls) == (1, 1, 1)
    assert execution.blocked_reason == "CONTROLLED_CANDIDATE_SET_EMPTY"
    assert execution.terminal_package is not None
    assert execution.terminal_package.status.value == "DATA_BLOCKED"
    assert execution.terminal_package.candidate_count == 0
    assert execution.decision is None
    assert not tuple(tmp_path.rglob("*.postgres-scope*"))
    with postgres_factory.connection(read_only=True) as connection:
        bindings = connection.execute(
            "SELECT scope_type FROM runtime_database_bindings ORDER BY scope_type"
        ).fetchall()
        feature_runs = connection.execute(
                "SELECT COUNT(*) FROM feature_materialization_run"
        ).fetchone()
    assert [str(item[0]) for item in bindings] == [
        "CONTROLLED_OPERATION",
        "DAILY_LOOP",
        "FREE_DATA_OPERATION",
    ]
    assert feature_runs is not None and int(feature_runs[0]) == 1


def test_postgres_blocked_projection_is_idempotent_and_append_only(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repositories = RepositoryFactory(
        DatabaseSettings.from_sources(
            database_url=os.environ["MARKET_REGIME_ALPHA_TEST_DATABASE_URL"],
            environ={},
        ),
        postgres_factory=postgres_factory,
    )
    repositories.bind_runtime("FREE_DATA_OPERATION", HASH)
    artifact = FreeDataBlockedArtifact.create(
        command_hash=HASH,
        source_archive_id=ArtifactId("source-replay-test"),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash=HASH,
        provider_result_hash=HASH,
        reason_code="DATA_AVAILABLE_AFTER_DECISION_TIME",
        error_type="ValueError",
        created_at=datetime(2026, 8, 5, 7, 0, tzinfo=UTC),
        code_revision="test-revision",
    )
    path = publish_free_data_blocked(root=tmp_path, artifact=artifact)
    repository = repositories.free_data_blocked()

    first = repository.record(artifact=artifact, locator=path)
    repeated = repository.record(artifact=artifact, locator=path)

    assert repeated == first
    assert repository.get(HASH) == first
    with pytest.raises(psycopg.IntegrityError):
        with postgres_factory.connection() as connection:
            connection.execute(
                "UPDATE free_data_operation_blocked SET reason_code = 'changed'"
            )
    with pytest.raises(psycopg.IntegrityError):
        with postgres_factory.connection() as connection:
            connection.execute("DELETE FROM free_data_operation_blocked")


def _path_config() -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="controlled-path-profile-v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-controlled-1455-v1",
        decision_time_local="14:55",
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
