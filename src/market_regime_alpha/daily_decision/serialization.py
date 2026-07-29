"""Canonical adapters for existing Universe and Feature domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
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
)
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilityRecord,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
    UniverseMembershipRecord,
)


def universe_snapshot_to_dict(
    snapshot: PITUniverseSnapshot,
) -> dict[str, Any]:
    return {
        "universe_id": str(snapshot.universe_id),
        "as_of": snapshot.as_of.isoformat(),
        "source_dataset_id": str(snapshot.source_dataset_id),
        "evidence_artifact_id": str(snapshot.evidence_artifact_id),
        "method_version": snapshot.method_version,
        "records": [
            {"symbol": item.symbol, "is_member": item.is_member}
            for item in snapshot.records
        ],
    }


def universe_snapshot_from_dict(
    payload: Mapping[str, Any],
) -> PITUniverseSnapshot:
    expected = {
        "universe_id",
        "as_of",
        "source_dataset_id",
        "evidence_artifact_id",
        "method_version",
        "records",
    }
    if set(payload) != expected:
        raise ValueError("PITUniverseSnapshot fields mismatch")
    records: list[UniverseMembershipRecord] = []
    for item in payload["records"]:
        if not isinstance(item, Mapping) or set(item) != {"symbol", "is_member"}:
            raise ValueError("UniverseMembershipRecord fields mismatch")
        if not isinstance(item["is_member"], bool):
            raise ValueError("UniverseMembershipRecord is_member must be boolean")
        records.append(
            UniverseMembershipRecord(
                symbol=str(item["symbol"]),
                is_member=item["is_member"],
            )
        )
    return PITUniverseSnapshot(
        universe_id=UniverseId(str(payload["universe_id"])),
        as_of=AsOfTime(datetime.fromisoformat(str(payload["as_of"]))),
        source_dataset_id=DatasetId(str(payload["source_dataset_id"])),
        evidence_artifact_id=ArtifactId(str(payload["evidence_artifact_id"])),
        method_version=str(payload["method_version"]),
        records=tuple(records),
    )


def eligibility_snapshot_to_dict(
    snapshot: TradingEligibilitySnapshot,
) -> dict[str, Any]:
    return {
        "as_of": snapshot.as_of.isoformat(),
        "source_dataset_id": str(snapshot.source_dataset_id),
        "evidence_artifact_id": str(snapshot.evidence_artifact_id),
        "records": [
            {
                "symbol": item.symbol,
                "status": item.status.value,
                "reasons": list(item.reasons),
            }
            for item in snapshot.records
        ],
    }


def eligibility_snapshot_from_dict(
    payload: Mapping[str, Any],
) -> TradingEligibilitySnapshot:
    expected = {
        "as_of",
        "source_dataset_id",
        "evidence_artifact_id",
        "records",
    }
    if set(payload) != expected:
        raise ValueError("TradingEligibilitySnapshot fields mismatch")
    records: list[TradingEligibilityRecord] = []
    for item in payload["records"]:
        if not isinstance(item, Mapping) or set(item) != {
            "symbol",
            "status",
            "reasons",
        }:
            raise ValueError("TradingEligibilityRecord fields mismatch")
        records.append(
            TradingEligibilityRecord(
                symbol=str(item["symbol"]),
                status=TradingEligibilityStatus(str(item["status"])),
                reasons=tuple(str(value) for value in item["reasons"]),
            )
        )
    return TradingEligibilitySnapshot(
        as_of=AsOfTime(datetime.fromisoformat(str(payload["as_of"]))),
        source_dataset_id=DatasetId(str(payload["source_dataset_id"])),
        evidence_artifact_id=ArtifactId(str(payload["evidence_artifact_id"])),
        records=tuple(records),
    )


def feature_definition_to_dict(
    definition: FeatureDefinition,
) -> dict[str, Any]:
    return {
        "feature_id": str(definition.feature_id),
        "name": definition.name,
        "semantic_family": definition.semantic_family,
        "source_information_families": list(
            definition.source_information_families
        ),
        "representation_method": definition.representation_method,
        "source_fields": list(definition.source_fields),
        "frequency": definition.frequency,
        "lookback": definition.lookback,
        "availability_rule": definition.availability_rule,
        "missingness_policy": definition.missingness_policy,
        "research_status": definition.research_status,
        "input_feature_ids": [
            str(item) for item in definition.input_feature_ids
        ],
        "value_type": definition.value_type,
        "parameters": [list(item) for item in definition.parameters],
    }


def feature_definition_from_dict(
    payload: Mapping[str, Any],
) -> FeatureDefinition:
    expected = {
        "feature_id",
        "name",
        "semantic_family",
        "source_information_families",
        "representation_method",
        "source_fields",
        "frequency",
        "lookback",
        "availability_rule",
        "missingness_policy",
        "research_status",
        "input_feature_ids",
        "value_type",
        "parameters",
    }
    if set(payload) != expected:
        raise ValueError("FeatureDefinition fields mismatch")
    parameters: list[tuple[str, str]] = []
    for item in payload["parameters"]:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("FeatureDefinition parameter mismatch")
        parameters.append((str(item[0]), str(item[1])))
    return FeatureDefinition(
        feature_id=FeatureDefinitionId(str(payload["feature_id"])),
        name=str(payload["name"]),
        semantic_family=str(payload["semantic_family"]),
        source_information_families=tuple(
            str(item) for item in payload["source_information_families"]
        ),
        representation_method=str(payload["representation_method"]),
        source_fields=tuple(str(item) for item in payload["source_fields"]),
        frequency=str(payload["frequency"]),
        lookback=str(payload["lookback"]),
        availability_rule=str(payload["availability_rule"]),
        missingness_policy=str(payload["missingness_policy"]),
        research_status=str(payload["research_status"]),
        input_feature_ids=tuple(
            FeatureDefinitionId(str(item))
            for item in payload["input_feature_ids"]
        ),
        value_type=str(payload["value_type"]),
        parameters=tuple(parameters),
    )


def feature_materialization_to_dict(
    materialization: FeatureMaterialization,
) -> dict[str, Any]:
    return {
        "materialization_id": str(materialization.materialization_id),
        "definition_id": str(materialization.definition_id),
        "dataset_id": str(materialization.dataset_id),
        "universe_id": str(materialization.universe_id),
        "as_of": materialization.as_of.isoformat(),
        "code_revision": materialization.code_revision,
        "config_hash": materialization.config_hash,
        "observations": [
            {
                "symbol": item.symbol,
                "status": item.status.value,
                "value": item.value,
            }
            for item in materialization.observations
        ],
    }


def feature_materialization_from_dict(
    payload: Mapping[str, Any],
) -> FeatureMaterialization:
    expected = {
        "materialization_id",
        "definition_id",
        "dataset_id",
        "universe_id",
        "as_of",
        "code_revision",
        "config_hash",
        "observations",
    }
    if set(payload) != expected:
        raise ValueError("FeatureMaterialization fields mismatch")
    observations: list[FeatureObservation] = []
    for item in payload["observations"]:
        if not isinstance(item, Mapping) or set(item) != {
            "symbol",
            "status",
            "value",
        }:
            raise ValueError("FeatureObservation fields mismatch")
        observations.append(
            FeatureObservation(
                symbol=str(item["symbol"]),
                status=InputAvailabilityStatus(str(item["status"])),
                value=item["value"],
            )
        )
    return FeatureMaterialization(
        materialization_id=FeatureMaterializationId(
            str(payload["materialization_id"])
        ),
        definition_id=FeatureDefinitionId(str(payload["definition_id"])),
        dataset_id=DatasetId(str(payload["dataset_id"])),
        universe_id=UniverseId(str(payload["universe_id"])),
        as_of=AsOfTime(datetime.fromisoformat(str(payload["as_of"]))),
        code_revision=str(payload["code_revision"]),
        config_hash=str(payload["config_hash"]),
        observations=tuple(observations),
    )
