from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    CapitalStateConfiguration,
    EtfRotationConfiguration,
    MarketStateConfiguration,
    MissingDataPolicy,
    ThemeRotationConfiguration,
    TransitionThresholds,
)


NOW = datetime(2026, 8, 6, 6, 35, tzinfo=timezone.utc)


def lineage() -> StateLineage:
    return StateLineage(
        continuous_operation_id=ArtifactId("operation-1"),
        runtime_tick_id=ArtifactId("tick-1"),
        provider_attempt_ids=(ArtifactId("provider-attempt-1"),),
        evidence_ids=(ArtifactId("evidence-1"),),
        dataset_id=DatasetId("dataset-1"),
        feature_id=ArtifactId("feature-1"),
        source_artifact_ids=(ArtifactId("source-1"),),
        model_id=ModelId("state-model"),
        model_version="1.0.0",
        configuration_id=ArtifactId("config-1"),
        configuration_hash="sha256:" + "a" * 64,
        as_of_time=NOW,
        available_at=NOW,
        created_at=NOW,
    )


def thresholds() -> TransitionThresholds:
    return TransitionThresholds(
        enter_threshold=Decimal("0.65"),
        exit_threshold=Decimal("0.45"),
        hysteresis=Decimal("0.20"),
        confirmation_count=2,
        minimum_dwell_seconds=300,
        minimum_coverage=Decimal("0.70"),
        missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
    )


def test_state_lineage_round_trip_and_identity_are_deterministic() -> None:
    value = lineage()

    decoded = StateLineage.from_canonical_dict(value.to_canonical_dict())

    assert decoded == value
    assert decoded.lineage_hash == value.lineage_hash


def test_state_lineage_rejects_future_available_evidence() -> None:
    with pytest.raises(ValueError, match="available_at must not exceed as_of_time"):
        replace(lineage(), available_at=datetime(2026, 8, 6, 6, 36, tzinfo=timezone.utc))


def test_state_lineage_rejects_tampered_configuration_hash() -> None:
    payload = lineage().to_canonical_dict()
    payload["configuration_hash"] = "not-a-hash"

    with pytest.raises(ValueError, match="configuration_hash"):
        StateLineage.from_canonical_dict(payload)


@pytest.mark.parametrize(
    "configuration_type",
    [
        MarketStateConfiguration,
        EtfRotationConfiguration,
        ThemeRotationConfiguration,
        CapitalStateConfiguration,
    ],
)
def test_domain_configuration_is_versioned_and_content_addressed(
    configuration_type: type[
        MarketStateConfiguration
        | EtfRotationConfiguration
        | ThemeRotationConfiguration
        | CapitalStateConfiguration
    ],
) -> None:
    configuration = configuration_type.create(
        model_id=ModelId("model-1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("config-1"),
        configuration_version="1.0.0",
        thresholds=thresholds(),
    )

    assert configuration.configuration_hash.startswith("sha256:")
    assert configuration_type.from_canonical_dict(
        configuration.to_canonical_dict()
    ) == configuration


def test_thresholds_reject_unversioned_or_invalid_policy_values() -> None:
    with pytest.raises(ValueError, match="enter_threshold must exceed exit_threshold"):
        replace(thresholds(), enter_threshold=Decimal("0.40"))
    with pytest.raises(ValueError, match="hysteresis"):
        replace(thresholds(), hysteresis=Decimal("0.10"))
    with pytest.raises(ValueError, match="confirmation_count"):
        replace(thresholds(), confirmation_count=0)


def test_configuration_requires_explicit_versions() -> None:
    with pytest.raises(ValueError, match="model_version"):
        MarketStateConfiguration.create(
            model_id=ModelId("model-1"),
            model_version="",
            configuration_id=ArtifactId("config-1"),
            configuration_version="1.0.0",
            thresholds=thresholds(),
        )
