from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    FeatureAvailabilityRule,
    FeatureCellStatus,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.research_qualification.domain.backtest_dataset import (
    BacktestDatasetFeatureCell,
    BacktestDatasetMember,
    BacktestFeatureLineageKind,
    materialize_backtest_dataset,
)
from market_regime_alpha.shared.hashing import sha256_bytes


def _id(value: int) -> UUID:
    return UUID(int=value)


def _artifact(value: int) -> ArtifactBinding:
    return ArtifactBinding(_id(value), f"{value:064x}", value)


def _feature(value: int, code: str) -> FeatureDefinition:
    return FeatureDefinition(
        feature_definition_id=_id(value),
        feature_code=code,
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
        algorithm_code=code,
        algorithm_version="1",
        algorithm_sha256=f"{value:064x}",
        code_artifact=_artifact(value + 100),
        config_artifact=_artifact(value + 200),
    )


def test_generic_materializer_freezes_multiple_typed_feature_cells() -> None:
    features = (_feature(10, "intraday_move"), _feature(11, "intraday_range"))
    members = (
        BacktestDatasetMember(
            instrument_id=_id(20),
            universe_member_id=_id(21),
            eligibility_assessment_id=_id(22),
            cells=(
                BacktestDatasetFeatureCell(
                    features[1].feature_definition_id,
                    FeatureCellStatus.MISSING,
                    "EXACT_ARCHIVED_GAP",
                    BacktestFeatureLineageKind.SOURCE_GAP,
                    _id(24),
                    None,
                ),
                BacktestDatasetFeatureCell(
                    features[0].feature_definition_id,
                    FeatureCellStatus.AVAILABLE,
                    "EXACT_ARCHIVED_BAR",
                    BacktestFeatureLineageKind.BAR_REVISION,
                    _id(23),
                    Decimal("0.0125"),
                ),
            ),
        ),
    )
    materialized = materialize_backtest_dataset(
        dataset_id=_id(30),
        dataset_code="generic_fit_20260105",
        simulated_decision_time=datetime(2026, 1, 5, 7, 1, tzinfo=UTC),
        universe_revision_id=_id(31),
        eligibility_policy_id=_id(32),
        feature_definition_ids=tuple(
            sorted((item.feature_definition_id for item in features), key=str)
        ),
        code_artifact=_artifact(33),
        config_artifact=_artifact(34),
        members=members,
    )
    manifest_artifact = ArtifactBinding(
        _id(35),
        sha256_bytes(materialized.manifest_content),
        len(materialized.manifest_content),
    )

    parsed = parse_decision_input_dataset_manifest(
        materialized.manifest_content,
        dataset=materialized.definition(manifest_artifact),
        feature_definitions=features,
    )

    assert materialized.row_count == 1
    assert materialized.available_cell_count == 1
    assert materialized.unavailable_cell_count == 1
    assert parsed.available_cell_count == 1
    assert parsed.missing_cell_count == 1
    assert b'"target"' not in materialized.manifest_content
    assert b'"outcome"' not in materialized.manifest_content


def test_generic_materializer_is_order_independent() -> None:
    feature_ids = (_id(10), _id(11))
    cell = lambda feature_id, value: BacktestDatasetFeatureCell(  # noqa: E731
        feature_id,
        FeatureCellStatus.AVAILABLE,
        "EXACT_ARCHIVED_BAR",
        BacktestFeatureLineageKind.BAR_REVISION,
        _id(value + 100),
        Decimal(value),
    )
    members = tuple(
        BacktestDatasetMember(
            _id(value),
            _id(value + 1),
            _id(value + 2),
            (cell(feature_ids[1], value + 1), cell(feature_ids[0], value)),
        )
        for value in (20, 30)
    )
    kwargs = {
        "dataset_id": _id(40),
        "dataset_code": "generic_validation_20260601",
        "simulated_decision_time": datetime(2026, 6, 1, 7, 1, tzinfo=UTC),
        "universe_revision_id": _id(41),
        "eligibility_policy_id": _id(42),
        "feature_definition_ids": feature_ids,
        "code_artifact": _artifact(43),
        "config_artifact": _artifact(44),
    }

    first = materialize_backtest_dataset(**kwargs, members=members)
    replay = materialize_backtest_dataset(
        **kwargs,
        members=tuple(
            BacktestDatasetMember(
                item.instrument_id,
                item.universe_member_id,
                item.eligibility_assessment_id,
                tuple(reversed(item.cells)),
            )
            for item in reversed(members)
        ),
    )

    assert first.manifest_content == replay.manifest_content


def test_generic_materializer_rejects_incomplete_feature_roster() -> None:
    member = BacktestDatasetMember(
        _id(20),
        _id(21),
        _id(22),
        (
            BacktestDatasetFeatureCell(
                _id(10),
                FeatureCellStatus.AVAILABLE,
                "EXACT_ARCHIVED_BAR",
                BacktestFeatureLineageKind.BAR_REVISION,
                _id(23),
                Decimal("1"),
            ),
        ),
    )

    try:
        materialize_backtest_dataset(
            dataset_id=_id(30),
            dataset_code="generic_incomplete",
            simulated_decision_time=datetime(2026, 1, 5, 7, 1, tzinfo=UTC),
            universe_revision_id=_id(31),
            eligibility_policy_id=_id(32),
            feature_definition_ids=(_id(10), _id(11)),
            code_artifact=_artifact(33),
            config_artifact=_artifact(34),
            members=(member,),
        )
    except ValueError as error:
        assert "exact Feature roster" in str(error)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("incomplete feature roster was accepted")


def test_generic_materializer_preserves_empty_selection_as_valid_dataset() -> None:
    materialized = materialize_backtest_dataset(
        dataset_id=_id(50),
        dataset_code="generic_empty_selection",
        simulated_decision_time=datetime(2026, 1, 5, 7, 1, tzinfo=UTC),
        universe_revision_id=_id(51),
        eligibility_policy_id=_id(52),
        feature_definition_ids=(_id(10),),
        code_artifact=_artifact(53),
        config_artifact=_artifact(54),
        members=(),
    )

    assert materialized.row_count == 0
    assert materialized.available_cell_count == 0
    assert materialized.unavailable_cell_count == 0
