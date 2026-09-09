"""Frozen account/history input values; no retired Runtime execution."""
from __future__ import annotations


from datetime import UTC, datetime, time, timedelta








from zoneinfo import ZoneInfo








from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)






from market_regime_alpha.application.continuous_research.policy import (
    default_continuous_decision_window_policy,
)












from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)


from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)








from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
)








from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)


from market_regime_alpha.evidence.canonical import canonical_hash


from market_regime_alpha.features.technical.catalog import (
    intraday_overlay_feature_set,
    static_technical_feature_set,
)
















from market_regime_alpha.signals import (
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
)


from tests.application.daily_loop.public_fixture import DECISION




from tests.persistence.postgres.test_free_data_operation import _path_config






SHANGHAI = ZoneInfo("Asia/Shanghai")


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("free-data-continuous-calendar"),
        market="A_SHARE",
        calendar_version="free-data-continuous-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            *tuple(
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
            TradingSession(
                trade_date=DECISION.value.date() + timedelta(days=1),
                session_close=datetime.combine(
                    DECISION.value.date() + timedelta(days=1),
                    time(15),
                    tzinfo=SHANGHAI,
                ),
            ),
        ),
    )


def _configuration(calendar) -> ControlledOperationRuntimeConfiguration:
    return ControlledOperationRuntimeConfiguration.create(
        static_feature_set=static_technical_feature_set(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        intraday_feature_set=intraday_overlay_feature_set(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        research=ControlledResearchPipelineConfig.create(
            candidate_discovery=ControlledCandidateDiscoveryConfig.create(
                top_n=5,
                minimum_candidate_population=5,
            )
        ),
        signal_model=canonical_signal_model_configuration_v2(),
        signal_mapping=canonical_signal_input_mapping_v2(effective_from=(DECISION.value - timedelta(days=365)).astimezone(UTC)),
        signal_requirement=canonical_all_factors_required_policy(),
        signal_freshness=canonical_signal_freshness_policy(trading_calendar=calendar),
        path_forecast=_path_config(),
    )


def _tick(command: ContinuousResearchCommand, suffix: str) -> RuntimeTickCommand:
    return RuntimeTickCommand.create(
        idempotency_key=f"{command.run_id}:{suffix}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=DECISION.value.astimezone(UTC),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )


def _continuous_command(symbols, calendar, configuration, authority_mode):
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key=f"selector-{authority_mode.value}",
        trading_date=DECISION.value.date(),
        requested_symbols=symbols,
        trading_calendar_id=calendar.artifact_id,
        trading_calendar_hash=calendar.content_hash,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("selector-provider-config"),
        provider_configuration_hash=canonical_hash({"provider": "selector"}),
        research_configuration_id=configuration.configuration_id,
        research_configuration_hash=configuration.configuration_hash,
        code_revision="selector-purpose-e2e",
        authority_mode=authority_mode,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


