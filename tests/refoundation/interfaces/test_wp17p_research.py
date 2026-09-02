from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.interfaces.wp17p_research import (
    Wp17pDatasetMember,
    Wp17pFeatureLineageKind,
    materialize_wp17p_dataset,
)
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    FeatureAvailabilityRule,
    FeatureCellStatus,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)
from market_regime_alpha.research_qualification.domain.manifest import (
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.shared.hashing import sha256_bytes


def _id(value: int) -> UUID:
    return UUID(int=value)


def _artifact(value: int) -> ArtifactBinding:
    return ArtifactBinding(_id(value), f"{value:064x}", value)


def _feature() -> FeatureDefinition:
    return FeatureDefinition(
        feature_definition_id=_id(10),
        feature_code="intraday_move_1455",
        version=1,
        value_type=FeatureValueType.DECIMAL,
        value_unit="RATIO",
        frequency_value=1,
        frequency_unit=FeatureIntervalUnit.TRADING_SESSION,
        window_value=1,
        window_unit=FeatureIntervalUnit.TRADING_SESSION,
        lookback_value=0,
        lookback_unit=FeatureIntervalUnit.TRADING_SESSION,
        source_requirements=(FeatureSourceRequirement.MARKET_BAR_REVISION,),
        availability_rule=FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        missingness_policy=FeatureMissingnessPolicy.EXPLICIT_STATUS,
        algorithm_code="intraday_move",
        algorithm_version="1",
        algorithm_sha256="a" * 64,
        code_artifact=_artifact(11),
        config_artifact=_artifact(12),
    )


def test_materializer_retains_available_and_missing_population_relationally() -> None:
    feature = _feature()
    members = (
        Wp17pDatasetMember(
            _id(20),
            _id(21),
            _id(22),
            FeatureCellStatus.AVAILABLE,
            "EXACT_ARCHIVED_BAR",
            Wp17pFeatureLineageKind.BAR_REVISION,
            _id(23),
            Decimal("0.0125"),
        ),
        Wp17pDatasetMember(
            _id(30),
            _id(31),
            _id(32),
            FeatureCellStatus.MISSING,
            "EXACT_ARCHIVED_GAP",
            Wp17pFeatureLineageKind.SOURCE_GAP,
            _id(33),
            None,
        ),
    )
    materialized = materialize_wp17p_dataset(
        dataset_id=_id(40),
        dataset_code="wp17p_fit_20260105",
        simulated_decision_time=datetime(2026, 1, 5, 7, 1, tzinfo=UTC),
        universe_revision_id=_id(41),
        eligibility_policy_id=_id(42),
        feature_definition_id=feature.feature_definition_id,
        code_artifact=_artifact(43),
        config_artifact=_artifact(44),
        members=members,
    )
    manifest_artifact = ArtifactBinding(
        _id(45),
        sha256_bytes(materialized.manifest_content),
        len(materialized.manifest_content),
    )

    parsed = parse_decision_input_dataset_manifest(
        materialized.manifest_content,
        dataset=materialized.definition(manifest_artifact),
        feature_definitions=(feature,),
    )

    assert materialized.row_count == 2
    assert materialized.available_count == materialized.unavailable_count == 1
    assert parsed.row_count == 2
    assert parsed.available_cell_count == 1
    assert parsed.missing_cell_count == 1
    assert {item.role.value for item in parsed.sources} == {
        "FEATURE_DEFINITION",
        "MARKET_BAR_REVISION",
        "MARKET_SOURCE_GAP",
        "POPULATION",
    }


def test_materializer_is_order_independent_and_contains_no_label_fields() -> None:
    feature = _feature()
    members = tuple(
        Wp17pDatasetMember(
            _id(value),
            _id(value + 10),
            _id(value + 20),
            FeatureCellStatus.AVAILABLE,
            "EXACT_ARCHIVED_BAR",
            Wp17pFeatureLineageKind.BAR_REVISION,
            _id(value + 30),
            Decimal(value),
        )
        for value in (100, 200)
    )
    kwargs = {
        "dataset_id": _id(300),
        "dataset_code": "wp17p_validation_20260601",
        "simulated_decision_time": datetime(2026, 6, 1, 7, 1, tzinfo=UTC),
        "universe_revision_id": _id(301),
        "eligibility_policy_id": _id(302),
        "feature_definition_id": feature.feature_definition_id,
        "code_artifact": _artifact(303),
        "config_artifact": _artifact(304),
    }

    first = materialize_wp17p_dataset(**kwargs, members=members)
    replay = materialize_wp17p_dataset(**kwargs, members=tuple(reversed(members)))

    assert first.manifest_content == replay.manifest_content
    assert b'"target"' not in first.manifest_content
    assert b'"outcome"' not in first.manifest_content
