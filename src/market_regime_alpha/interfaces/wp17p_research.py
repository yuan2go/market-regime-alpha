"""Controlled materialization helpers for the WP-17P exploratory pilot.

This interface layer composes existing Authorities.  It owns no Dataset,
Selection, Decision, Outcome, or Evaluation state and deliberately contains no
PostgreSQL writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import json
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DecisionInputDatasetDefinition,
    FeatureCellStatus,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime, require_utc


class Wp17pFeatureLineageKind(StrEnum):
    BAR_REVISION = "BAR_REVISION"
    SOURCE_GAP = "SOURCE_GAP"


@dataclass(frozen=True, slots=True)
class Wp17pDatasetMember:
    instrument_id: UUID
    universe_member_id: UUID
    eligibility_assessment_id: UUID
    status: FeatureCellStatus
    reason_code: str
    lineage_kind: Wp17pFeatureLineageKind
    lineage_id: UUID
    value: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FeatureCellStatus):
            raise TypeError("status must be FeatureCellStatus")
        if not isinstance(self.lineage_kind, Wp17pFeatureLineageKind):
            raise TypeError("lineage_kind must be Wp17pFeatureLineageKind")
        available = self.status is FeatureCellStatus.AVAILABLE
        if available != (self.value is not None):
            raise ValueError("only AVAILABLE feature members carry a value")
        if available != (self.lineage_kind is Wp17pFeatureLineageKind.BAR_REVISION):
            raise ValueError("feature state and typed lineage are incompatible")


@dataclass(frozen=True, slots=True)
class Wp17pDatasetMaterialization:
    dataset_id: UUID
    dataset_code: str
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    feature_definition_id: UUID
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    manifest_content: bytes
    row_count: int
    available_count: int
    unavailable_count: int

    def definition(self, manifest_artifact: ArtifactBinding) -> DecisionInputDatasetDefinition:
        return DecisionInputDatasetDefinition(
            dataset_id=self.dataset_id,
            dataset_code=self.dataset_code,
            version=1,
            decision_time=self.decision_time,
            universe_revision_id=self.universe_revision_id,
            eligibility_policy_id=self.eligibility_policy_id,
            feature_definition_ids=(self.feature_definition_id,),
            manifest_artifact=manifest_artifact,
            code_artifact=self.code_artifact,
            config_artifact=self.config_artifact,
        )


def materialize_wp17p_dataset(
    *,
    dataset_id: UUID,
    dataset_code: str,
    simulated_decision_time: datetime,
    universe_revision_id: UUID,
    eligibility_policy_id: UUID,
    feature_definition_id: UUID,
    code_artifact: ArtifactBinding,
    config_artifact: ArtifactBinding,
    members: tuple[Wp17pDatasetMember, ...],
) -> Wp17pDatasetMaterialization:
    """Build one complete label-free Dataset manifest from typed lineage."""

    decision_time = DecisionTime(require_utc(simulated_decision_time, field="simulated_decision_time"))
    ordered = tuple(sorted(members, key=lambda item: str(item.instrument_id)))
    if not ordered or len({item.instrument_id for item in ordered}) != len(ordered):
        raise ValueError("Dataset member roster must be non-empty and unique")
    feature_source_id = uuid5(dataset_id, f"feature:{feature_definition_id}")
    sources: list[dict[str, object]] = [
        {
            "dataset_source_id": str(feature_source_id),
            "feature_definition_id": str(feature_definition_id),
            "role": "FEATURE_DEFINITION",
        }
    ]
    rows: list[dict[str, object]] = []
    for member in ordered:
        population_source_id = uuid5(
            dataset_id,
            f"population:{member.instrument_id}",
        )
        lineage_source_id = uuid5(
            dataset_id,
            f"lineage:{member.lineage_kind.value}:{member.lineage_id}",
        )
        sources.append(
            {
                "dataset_source_id": str(population_source_id),
                "eligibility_assessment_id": str(member.eligibility_assessment_id),
                "instrument_id": str(member.instrument_id),
                "role": "POPULATION",
                "universe_member_id": str(member.universe_member_id),
            }
        )
        lineage: dict[str, object] = {
            "dataset_source_id": str(lineage_source_id),
            "role": ("MARKET_BAR_REVISION" if member.lineage_kind is Wp17pFeatureLineageKind.BAR_REVISION else "MARKET_SOURCE_GAP"),
        }
        lineage["market_bar_revision_id" if member.lineage_kind is Wp17pFeatureLineageKind.BAR_REVISION else "market_source_gap_id"] = str(
            member.lineage_id
        )
        sources.append(lineage)
        rows.append(
            {
                "cells": [
                    {
                        "feature_definition_id": str(feature_definition_id),
                        "reason_code": member.reason_code,
                        "source_ids": sorted((str(feature_source_id), str(lineage_source_id))),
                        "status": member.status.value,
                        "value": (
                            None
                            if member.value is None
                            else format(member.value, "f")
                        ),
                    }
                ],
                "instrument_id": str(member.instrument_id),
                "population_source_id": str(population_source_id),
            }
        )
    sources.sort(key=lambda item: str(item["dataset_source_id"]))
    payload = {
        "code_artifact": _artifact_payload(code_artifact),
        "config_artifact": _artifact_payload(config_artifact),
        "dataset_code": dataset_code,
        "dataset_id": str(dataset_id),
        "dataset_version": 1,
        "decision_time": decision_time.value.isoformat(),
        "eligibility_policy_id": str(eligibility_policy_id),
        "feature_definition_ids": [str(feature_definition_id)],
        "rows": rows,
        "schema": "mra-decision-input-dataset-v1",
        "sources": sources,
        "universe_revision_id": str(universe_revision_id),
    }
    content = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    available = sum(item.status is FeatureCellStatus.AVAILABLE for item in ordered)
    return Wp17pDatasetMaterialization(
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        decision_time=decision_time,
        universe_revision_id=universe_revision_id,
        eligibility_policy_id=eligibility_policy_id,
        feature_definition_id=feature_definition_id,
        code_artifact=code_artifact,
        config_artifact=config_artifact,
        manifest_content=content,
        row_count=len(ordered),
        available_count=available,
        unavailable_count=len(ordered) - available,
    )


def _artifact_payload(binding: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": str(binding.artifact_id),
        "content_sha256": str(ContentHash(str(binding.content_sha256))),
        "size_bytes": binding.size_bytes,
    }


__all__ = [
    "Wp17pDatasetMaterialization",
    "Wp17pDatasetMember",
    "Wp17pFeatureLineageKind",
    "materialize_wp17p_dataset",
]
