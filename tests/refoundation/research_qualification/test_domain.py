from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DatasetSourceRole,
    DecisionInputDatasetDefinition,
    FeatureAvailabilityRule,
    FeatureCellStatus,
    FeatureDefinition,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.shared.time import DecisionTime


def _artifact(number: int, hash_character: str) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=UUID(int=number),
        content_sha256=hash_character * 64,
        size_bytes=number,
    )


def _feature(
    number: int,
    *,
    code: str,
    value_type: FeatureValueType,
    value_unit: str,
) -> FeatureDefinition:
    return FeatureDefinition(
        feature_definition_id=UUID(int=number),
        feature_code=code,
        version=1,
        value_type=value_type,
        value_unit=value_unit,
        frequency_value=1,
        frequency_unit=FeatureIntervalUnit.TRADING_SESSION,
        window_value=20,
        window_unit=FeatureIntervalUnit.TRADING_SESSION,
        lookback_value=20,
        lookback_unit=FeatureIntervalUnit.TRADING_SESSION,
        source_requirements=(
            FeatureSourceRequirement.MARKET_BAR_REVISION,
            FeatureSourceRequirement.TRADING_SESSION,
        ),
        availability_rule=FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        missingness_policy=FeatureMissingnessPolicy.EXPLICIT_STATUS,
        algorithm_code="mean_turnover",
        algorithm_version="1",
        algorithm_sha256="c" * 64,
        code_artifact=_artifact(number + 100, "d"),
        config_artifact=_artifact(number + 200, "e"),
    )


def _dataset(features: tuple[FeatureDefinition, ...]) -> DecisionInputDatasetDefinition:
    return DecisionInputDatasetDefinition(
        dataset_id=UUID(int=10),
        dataset_code="candidate-input-v1",
        version=1,
        decision_time=DecisionTime(datetime(2026, 8, 29, 6, tzinfo=timezone.utc)),
        universe_revision_id=UUID(int=11),
        eligibility_policy_id=UUID(int=12),
        feature_definition_ids=tuple(
            sorted(
                (item.feature_definition_id for item in features),
                key=str,
            )
        ),
        manifest_artifact=_artifact(13, "a"),
        code_artifact=_artifact(14, "b"),
        config_artifact=_artifact(15, "f"),
    )


def _manifest_payload(
    dataset: DecisionInputDatasetDefinition,
    features: tuple[FeatureDefinition, ...],
) -> dict[str, object]:
    instrument_id = UUID(int=20)
    population_source_id = UUID(int=30)
    decimal_feature, boolean_feature = features
    decimal_source_id = UUID(int=31)
    boolean_source_id = UUID(int=32)
    market_source_id = UUID(int=33)
    gap_source_id = UUID(int=34)
    return {
        "schema": "mra-decision-input-dataset-v1",
        "dataset_id": str(dataset.dataset_id),
        "dataset_code": dataset.dataset_code,
        "dataset_version": dataset.version,
        "decision_time": dataset.decision_time.value.isoformat(),
        "universe_revision_id": str(dataset.universe_revision_id),
        "eligibility_policy_id": str(dataset.eligibility_policy_id),
        "feature_definition_ids": [
            str(item.feature_definition_id) for item in features
        ],
        "code_artifact": {
            "artifact_id": str(dataset.code_artifact.artifact_id),
            "content_sha256": str(dataset.code_artifact.content_sha256),
            "size_bytes": dataset.code_artifact.size_bytes,
        },
        "config_artifact": {
            "artifact_id": str(dataset.config_artifact.artifact_id),
            "content_sha256": str(dataset.config_artifact.content_sha256),
            "size_bytes": dataset.config_artifact.size_bytes,
        },
        "sources": [
            {
                "dataset_source_id": str(population_source_id),
                "role": DatasetSourceRole.POPULATION.value,
                "instrument_id": str(instrument_id),
                "universe_member_id": str(UUID(int=21)),
                "eligibility_assessment_id": str(UUID(int=22)),
            },
            {
                "dataset_source_id": str(decimal_source_id),
                "role": DatasetSourceRole.FEATURE_DEFINITION.value,
                "feature_definition_id": str(decimal_feature.feature_definition_id),
            },
            {
                "dataset_source_id": str(boolean_source_id),
                "role": DatasetSourceRole.FEATURE_DEFINITION.value,
                "feature_definition_id": str(boolean_feature.feature_definition_id),
            },
            {
                "dataset_source_id": str(market_source_id),
                "role": DatasetSourceRole.MARKET_BAR_REVISION.value,
                "market_bar_revision_id": str(UUID(int=23)),
            },
            {
                "dataset_source_id": str(gap_source_id),
                "role": DatasetSourceRole.MARKET_SOURCE_GAP.value,
                "market_source_gap_id": str(UUID(int=24)),
            },
        ],
        "rows": [
            {
                "instrument_id": str(instrument_id),
                "population_source_id": str(population_source_id),
                "cells": [
                    {
                        "feature_definition_id": str(decimal_feature.feature_definition_id),
                        "status": FeatureCellStatus.AVAILABLE.value,
                        "value": "123.4500000000",
                        "reason_code": "OBSERVED",
                        "source_ids": [
                            str(decimal_source_id),
                            str(market_source_id),
                        ],
                    },
                    {
                        "feature_definition_id": str(boolean_feature.feature_definition_id),
                        "status": FeatureCellStatus.MISSING.value,
                        "value": None,
                        "reason_code": "SOURCE_GAP",
                        "source_ids": [
                            str(boolean_source_id),
                            str(gap_source_id),
                        ],
                    },
                ],
            }
        ],
    }


@pytest.fixture
def feature_definitions() -> tuple[FeatureDefinition, ...]:
    return (
        _feature(
            1,
            code="mean_turnover_20s",
            value_type=FeatureValueType.DECIMAL,
            value_unit="CNY",
        ),
        _feature(
            2,
            code="limit_metadata_present",
            value_type=FeatureValueType.BOOLEAN,
            value_unit="BOOLEAN",
        ),
    )


def test_feature_definition_is_only_immutable_calculation_semantics(
    feature_definitions: tuple[FeatureDefinition, ...],
) -> None:
    feature = feature_definitions[0]
    assert feature.value_type is FeatureValueType.DECIMAL
    assert feature.source_requirements == (
        FeatureSourceRequirement.MARKET_BAR_REVISION,
        FeatureSourceRequirement.TRADING_SESSION,
    )
    assert len(str(feature.content_sha256)) == 64
    assert not {
        "alpha_supported",
        "research_maturity",
        "external_validation",
        "qualification_status",
        "dependencies",
    } & set(feature.__dataclass_fields__)


def test_manifest_preserves_every_row_and_explicit_missing_feature_cell(
    feature_definitions: tuple[FeatureDefinition, ...],
) -> None:
    dataset = _dataset(feature_definitions)
    payload = _manifest_payload(dataset, feature_definitions)

    manifest = parse_decision_input_dataset_manifest(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        dataset=dataset,
        feature_definitions=feature_definitions,
    )

    assert manifest.row_count == 1
    assert manifest.feature_count == 2
    assert manifest.cell_count == 2
    assert manifest.available_cell_count == 1
    assert manifest.missing_cell_count == 1
    assert manifest.rows[0].cells[0].value == Decimal("123.4500000000")
    assert manifest.rows[0].cells[1].status is FeatureCellStatus.MISSING
    assert manifest.rows[0].cells[1].value is None


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "target",
        "outcome",
        "forward_return",
        "mfe",
        "mae",
        "barrier_result",
        "futureObservation",
        "realized_label",
        "posterior_value",
    ),
)
def test_manifest_parser_physically_rejects_label_leakage_fields(
    feature_definitions: tuple[FeatureDefinition, ...],
    forbidden_key: str,
) -> None:
    dataset = _dataset(feature_definitions)
    payload = _manifest_payload(dataset, feature_definitions)
    payload["rows"][0]["cells"][0][forbidden_key] = "leak"  # type: ignore[index]

    with pytest.raises(ValueError, match="label leakage"):
        parse_decision_input_dataset_manifest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            dataset=dataset,
            feature_definitions=feature_definitions,
        )


def test_manifest_parser_rejects_float_and_wrong_typed_value(
    feature_definitions: tuple[FeatureDefinition, ...],
) -> None:
    dataset = _dataset(feature_definitions)
    payload = _manifest_payload(dataset, feature_definitions)
    payload["rows"][0]["cells"][0]["value"] = 123.45  # type: ignore[index]
    with pytest.raises(ValueError, match="floating-point"):
        parse_decision_input_dataset_manifest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            dataset=dataset,
            feature_definitions=feature_definitions,
        )


def test_manifest_parser_rejects_duplicate_role_specific_source_identity(
    feature_definitions: tuple[FeatureDefinition, ...],
) -> None:
    dataset = _dataset(feature_definitions)
    payload = _manifest_payload(dataset, feature_definitions)
    duplicate_id = UUID(int=35)
    payload["sources"].append(  # type: ignore[union-attr]
        {
            "dataset_source_id": str(duplicate_id),
            "role": DatasetSourceRole.MARKET_BAR_REVISION.value,
            "market_bar_revision_id": str(UUID(int=23)),
        }
    )
    payload["sources"].sort(key=lambda item: item["dataset_source_id"])  # type: ignore[union-attr,index]
    payload["rows"][0]["cells"][0]["source_ids"].append(str(duplicate_id))  # type: ignore[index,union-attr]
    payload["rows"][0]["cells"][0]["source_ids"].sort()  # type: ignore[index,union-attr]

    with pytest.raises(ValueError, match="source identities must be unique"):
        parse_decision_input_dataset_manifest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            dataset=dataset,
            feature_definitions=feature_definitions,
        )

    payload = _manifest_payload(dataset, feature_definitions)
    payload["rows"][0]["cells"][1]["value"] = "true"  # type: ignore[index]
    payload["rows"][0]["cells"][1]["status"] = "AVAILABLE"  # type: ignore[index]
    payload["rows"][0]["cells"][1]["source_ids"][1] = str(UUID(int=33))  # type: ignore[index]
    with pytest.raises(ValueError, match="BOOLEAN Feature value"):
        parse_decision_input_dataset_manifest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            dataset=dataset,
            feature_definitions=feature_definitions,
        )
