from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_regime_alpha.core.identity import (
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
    FeatureObservation,
    FeatureRegistry,
)


def test_feature_registry_is_idempotent_but_rejects_identity_conflict() -> None:
    feature_id = FeatureDefinitionId("feature-relative-strength-20d-v1")
    definition = FeatureDefinition(
        feature_id=feature_id,
        name="20D Relative Strength",
        semantic_family="Relative Strength",
        source_information_families=("PRICE_ONLY",),
        representation_method="relative-return",
        parameters=(("window", "20"),),
    )
    registry = FeatureRegistry()

    assert registry.register(definition) is definition
    assert registry.register(definition) is definition
    assert registry.get(feature_id) == definition

    with pytest.raises(ValueError, match="feature identity conflict"):
        registry.register(
            FeatureDefinition(
                feature_id=feature_id,
                name="10D Relative Strength",
                semantic_family="Relative Strength",
                source_information_families=("PRICE_ONLY",),
                representation_method="relative-return",
                parameters=(("window", "10"),),
            )
        )


def test_feature_definition_rejects_blank_source_information_family() -> None:
    with pytest.raises(ValueError, match="source_information_family"):
        FeatureDefinition(
            feature_id=FeatureDefinitionId("feature-invalid-v1"),
            name="Invalid Feature",
            semantic_family="Trend",
            source_information_families=("PRICE_ONLY", ""),
            representation_method="fixture",
        )


def test_feature_observation_requires_canonical_availability_status() -> None:
    with pytest.raises(TypeError, match="InputAvailabilityStatus"):
        FeatureObservation(
            symbol="000001.SZ",
            status="MISSING",  # type: ignore[arg-type]
            value=None,
        )


def test_missing_feature_is_not_a_neutral_numeric_value() -> None:
    with pytest.raises(ValueError, match="must not carry a usable value"):
        FeatureObservation(
            symbol="000001.SZ",
            status=InputAvailabilityStatus.MISSING,
            value=0.0,
        )


def test_feature_materialization_has_distinct_identity_from_definition() -> None:
    as_of = AsOfTime(datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc))
    materialization = FeatureMaterialization(
        materialization_id=FeatureMaterializationId("fm-rs20-20260715-v1"),
        definition_id=FeatureDefinitionId("feature-relative-strength-20d-v1"),
        dataset_id=DatasetId("dataset-rehearsal-v1"),
        universe_id=UniverseId("universe-v1"),
        as_of=as_of,
        code_revision="abc123",
        config_hash="config-rs20-v1",
        observations=(
            FeatureObservation(
                symbol="000001.SZ",
                status=InputAvailabilityStatus.AVAILABLE,
                value=0.12,
            ),
            FeatureObservation(
                symbol="000002.SZ",
                status=InputAvailabilityStatus.MISSING,
                value=None,
            ),
        ),
    )

    assert materialization.materialization_id != materialization.definition_id
    assert materialization.available_symbols == ("000001.SZ",)
