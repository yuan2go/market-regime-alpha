from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationError,
    RuntimeConfigurationReader,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.forecasting import (
    PATH_FORECAST_CONFIG_SCHEMA,
    PathForecastConfig,
)
from market_regime_alpha.features.technical.catalog import (
    canonical_technical_feature_set,
)
from market_regime_alpha.portfolio import (
    COMPLETE_ACCOUNT_RISK_CONFIGURATION_SCHEMA,
    RISK_BUDGET_SCHEMA,
    CompleteAccountRiskConfiguration,
    RiskBudget,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
    default_research_pipeline_config,
)
from market_regime_alpha.signals import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SignalFamily,
    SignalModelConfig,
    canonical_signal_input_mapping,
)
from market_regime_alpha.strategies.entry import (
    EntryBarrierSpec,
    build_entry_path_target_contract,
)


def _signal_configuration() -> SignalModelConfig:
    return SignalModelConfig(
        profile_id="runtime-signal-v1",
        model_id=ModelId("runtime-signal-model-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-1455-v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        signal_family=SignalFamily.TREND_CONTINUATION,
        price_action_min_return=0.01,
        volume_confirmation_min_ratio=1.2,
        trend_confirmation_min_return=0.02,
        vwap_min_relative_return=0.0,
        overheat_max_return=0.08,
        minimum_confirmations=3,
        scoring_method="EQUAL_CONFIRMATION_MEAN_V1",
        schema_version=SIGNAL_MODEL_CONFIG_SCHEMA,
    )


def _path_configuration() -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="runtime-path-v1",
        model_id=ModelId("runtime-path-model-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-1455-v1",
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
        minimum_usable_samples=2,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _complete_account_risk_configuration() -> CompleteAccountRiskConfiguration:
    budget = RiskBudget.create(
        profile_id="runtime-risk-budget-v1",
        maximum_gross_exposure=0.8,
        single_symbol_limit=0.2,
        theme_limit=0.4,
        liquidity_max_participation=0.1,
        minimum_cash_reserve=0.1,
        maximum_loss_budget=0.1,
        t_plus_one_enforced=True,
        risk_service_timeout_seconds=2.0,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=RISK_BUDGET_SCHEMA,
    )
    return CompleteAccountRiskConfiguration.create(
        profile_id="runtime-complete-account-risk-v1",
        risk_budget=budget,
        maximum_account_snapshot_age_seconds=60.0,
        schema_version=COMPLETE_ACCOUNT_RISK_CONFIGURATION_SCHEMA,
    )


def _reference(
    configuration: (
        ResearchPipelineConfig
        | SignalModelConfig
        | PathForecastConfig
        | CompleteAccountRiskConfiguration
    ),
    kind: LifecycleConfigurationKind,
    path: Path,
) -> LifecycleConfigurationReference:
    version = (
        ResearchPipelineConfig.SCHEMA_VERSION
        if isinstance(configuration, ResearchPipelineConfig)
        else configuration.schema_version
    )
    return LifecycleConfigurationReference(
        configuration_kind=kind,
        configuration_id=configuration.configuration_id,
        configuration_version=version,
        content_hash=configuration.configuration_hash,
        locator=str(path),
    )


@pytest.mark.parametrize(
    ("configuration", "kind"),
    (
        (
            default_research_pipeline_config(),
            LifecycleConfigurationKind.RESEARCH_PIPELINE,
        ),
        (_signal_configuration(), LifecycleConfigurationKind.SIGNAL_MODEL),
        (_path_configuration(), LifecycleConfigurationKind.PATH_FORECAST),
        (
            _complete_account_risk_configuration(),
            LifecycleConfigurationKind.COMPLETE_ACCOUNT_RISK,
        ),
    ),
)
def test_reader_restores_existing_typed_configuration_without_defaults(
    tmp_path: Path,
    configuration: (
        ResearchPipelineConfig
        | SignalModelConfig
        | PathForecastConfig
        | CompleteAccountRiskConfiguration
    ),
    kind: LifecycleConfigurationKind,
) -> None:
    path = tmp_path / f"{kind.value.lower()}.json"
    path.write_text(
        json.dumps(configuration.to_canonical_dict(), sort_keys=True),
        encoding="utf-8",
    )
    reference = _reference(configuration, kind, path)
    loaded = RuntimeConfigurationReader().read(reference)
    assert loaded.reference == reference
    assert loaded.configuration == configuration


def test_reader_restores_feature_set_and_signal_mapping_configurations(
    tmp_path: Path,
) -> None:
    effective = datetime(2026, 1, 1, tzinfo=timezone.utc)
    feature_set = canonical_technical_feature_set(effective_from=effective)
    mapping = canonical_signal_input_mapping(effective_from=effective)
    values = (
        (
            feature_set,
            LifecycleConfigurationKind.FEATURE_SET,
            feature_set.feature_set_id,
            feature_set.feature_set_version,
            feature_set.content_hash,
        ),
        (
            mapping,
            LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING,
            mapping.configuration_id,
            mapping.configuration_version,
            mapping.configuration_hash,
        ),
    )
    for configuration, kind, identity, version, content_hash in values:
        path = tmp_path / f"{kind.value.lower()}.json"
        path.write_text(
            json.dumps(configuration.to_canonical_dict(), sort_keys=True),
            encoding="utf-8",
        )
        reference = LifecycleConfigurationReference(
            configuration_kind=kind,
            configuration_id=identity,
            configuration_version=version,
            content_hash=content_hash,
            locator=str(path),
        )
        assert RuntimeConfigurationReader().read(reference).configuration == configuration


def test_reader_rejects_locator_content_hash_identity_and_version_tamper(
    tmp_path: Path,
) -> None:
    configuration = _signal_configuration()
    path = tmp_path / "signal.json"
    path.write_text(json.dumps(configuration.to_canonical_dict()), encoding="utf-8")
    reference = _reference(
        configuration,
        LifecycleConfigurationKind.SIGNAL_MODEL,
        path,
    )
    reader = RuntimeConfigurationReader()

    with pytest.raises(RuntimeConfigurationError, match="cannot read"):
        reader.read(replace(reference, locator=str(tmp_path / "missing.json")))
    with pytest.raises(RuntimeConfigurationError, match="identity, version or hash"):
        reader.read(replace(reference, content_hash="sha256:" + "0" * 64))
    with pytest.raises(RuntimeConfigurationError, match="identity, version or hash"):
        reader.read(replace(reference, configuration_version="wrong"))

    payload = configuration.to_canonical_dict()
    payload["minimum_confirmations"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeConfigurationError, match="identity, version or hash"):
        reader.read(reference)


def test_reader_rejects_duplicate_keys_and_non_json_numbers(tmp_path: Path) -> None:
    path = tmp_path / "generic.json"
    reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.GENERIC,
        configuration_id=ArtifactId("generic-test"),
        configuration_version="1",
        content_hash="sha256:" + "a" * 64,
        locator=str(path),
    )
    path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(RuntimeConfigurationError, match="strict JSON"):
        RuntimeConfigurationReader().read(reference)
    path.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(RuntimeConfigurationError, match="strict JSON"):
        RuntimeConfigurationReader().read(reference)
def test_generic_kind_is_explicitly_non_executable_and_cannot_hide_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "generic.json"
    path.write_text(json.dumps({"mode": "read-only"}), encoding="utf-8")
    reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.GENERIC,
        configuration_id=ArtifactId("generic-test"),
        configuration_version="1",
        content_hash="sha256:" + "a" * 64,
        locator=str(path),
    )
    with pytest.raises(RuntimeConfigurationError, match="cannot restore GENERIC"):
        RuntimeConfigurationReader().read(reference)


def test_configuration_reference_rejects_remote_or_uncontrolled_locator() -> None:
    configuration = _signal_configuration()
    with pytest.raises(ValueError, match="controlled local"):
        LifecycleConfigurationReference(
            configuration_kind=LifecycleConfigurationKind.SIGNAL_MODEL,
            configuration_id=configuration.configuration_id,
            configuration_version=configuration.schema_version,
            content_hash=configuration.configuration_hash,
            locator="https://example.invalid/configuration.json",
        )
