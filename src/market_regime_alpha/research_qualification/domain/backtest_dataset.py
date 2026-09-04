"""Deterministic label-free Dataset materialization for generic Backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import json
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain.model import (
    ArtifactBinding,
    DecisionInputDatasetDefinition,
)
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureCellStatus,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime, require_utc


class BacktestFeatureLineageKind(StrEnum):
    BAR_REVISION = "BAR_REVISION"
    SOURCE_GAP = "SOURCE_GAP"


@dataclass(frozen=True, slots=True)
class BacktestDatasetFeatureCell:
    feature_definition_id: UUID
    status: FeatureCellStatus
    reason_code: str
    lineage_kind: BacktestFeatureLineageKind
    lineage_id: UUID
    value: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FeatureCellStatus):
            raise TypeError("status must be FeatureCellStatus")
        if not isinstance(self.lineage_kind, BacktestFeatureLineageKind):
            raise TypeError("lineage_kind must be BacktestFeatureLineageKind")
        if not self.reason_code:
            raise ValueError("Feature cell reason_code is required")
        available = self.status is FeatureCellStatus.AVAILABLE
        if available != (self.value is not None):
            raise ValueError("only AVAILABLE Feature cells carry a value")
        if available != (
            self.lineage_kind is BacktestFeatureLineageKind.BAR_REVISION
        ):
            raise ValueError("Feature state and typed lineage are incompatible")


@dataclass(frozen=True, slots=True)
class BacktestDatasetMember:
    instrument_id: UUID
    universe_member_id: UUID
    eligibility_assessment_id: UUID
    cells: tuple[BacktestDatasetFeatureCell, ...]

    def __post_init__(self) -> None:
        if not self.cells:
            raise ValueError("Dataset member requires Feature cells")
        if len({item.feature_definition_id for item in self.cells}) != len(
            self.cells
        ):
            raise ValueError("Dataset member Feature cells must be unique")


@dataclass(frozen=True, slots=True)
class BacktestDatasetMaterialization:
    dataset_id: UUID
    dataset_code: str
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    feature_definition_ids: tuple[UUID, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    manifest_content: bytes
    row_count: int
    available_cell_count: int
    unavailable_cell_count: int

    def definition(
        self,
        manifest_artifact: ArtifactBinding,
    ) -> DecisionInputDatasetDefinition:
        return DecisionInputDatasetDefinition(
            dataset_id=self.dataset_id,
            dataset_code=self.dataset_code,
            version=1,
            decision_time=self.decision_time,
            universe_revision_id=self.universe_revision_id,
            eligibility_policy_id=self.eligibility_policy_id,
            feature_definition_ids=self.feature_definition_ids,
            manifest_artifact=manifest_artifact,
            code_artifact=self.code_artifact,
            config_artifact=self.config_artifact,
        )


def materialize_backtest_dataset(
    *,
    dataset_id: UUID,
    dataset_code: str,
    simulated_decision_time: datetime,
    universe_revision_id: UUID,
    eligibility_policy_id: UUID,
    feature_definition_ids: tuple[UUID, ...],
    code_artifact: ArtifactBinding,
    config_artifact: ArtifactBinding,
    members: tuple[BacktestDatasetMember, ...],
) -> BacktestDatasetMaterialization:
    """Build exact deterministic bytes from typed population/Feature lineage."""

    decision_time = DecisionTime(
        require_utc(simulated_decision_time, field="simulated_decision_time")
    )
    if not feature_definition_ids or feature_definition_ids != tuple(
        sorted(set(feature_definition_ids), key=str)
    ):
        raise ValueError("Feature definition roster must be non-empty, unique and sorted")
    ordered = tuple(sorted(members, key=lambda item: str(item.instrument_id)))
    if len({item.instrument_id for item in ordered}) != len(ordered):
        raise ValueError("Dataset member roster must be unique")
    expected_features = set(feature_definition_ids)
    if any(
        {cell.feature_definition_id for cell in member.cells} != expected_features
        for member in ordered
    ):
        raise ValueError("every Dataset member must carry the exact Feature roster")

    sources_by_id: dict[UUID, dict[str, object]] = {}
    for feature_definition_id in feature_definition_ids:
        source_id = uuid5(dataset_id, f"feature:{feature_definition_id}")
        sources_by_id[source_id] = {
            "dataset_source_id": str(source_id),
            "feature_definition_id": str(feature_definition_id),
            "role": "FEATURE_DEFINITION",
        }

    rows: list[dict[str, object]] = []
    available_count = 0
    for member in ordered:
        population_source_id = uuid5(
            dataset_id,
            f"population:{member.instrument_id}",
        )
        sources_by_id[population_source_id] = {
            "dataset_source_id": str(population_source_id),
            "eligibility_assessment_id": str(member.eligibility_assessment_id),
            "instrument_id": str(member.instrument_id),
            "role": "POPULATION",
            "universe_member_id": str(member.universe_member_id),
        }
        cells: list[dict[str, object]] = []
        for cell in sorted(member.cells, key=lambda item: str(item.feature_definition_id)):
            feature_source_id = uuid5(
                dataset_id,
                f"feature:{cell.feature_definition_id}",
            )
            lineage_source_id = uuid5(
                dataset_id,
                f"lineage:{cell.lineage_kind.value}:{cell.lineage_id}",
            )
            lineage: dict[str, object] = {
                "dataset_source_id": str(lineage_source_id),
                "role": (
                    "MARKET_BAR_REVISION"
                    if cell.lineage_kind is BacktestFeatureLineageKind.BAR_REVISION
                    else "MARKET_SOURCE_GAP"
                ),
            }
            lineage[
                "market_bar_revision_id"
                if cell.lineage_kind is BacktestFeatureLineageKind.BAR_REVISION
                else "market_source_gap_id"
            ] = str(cell.lineage_id)
            previous = sources_by_id.setdefault(lineage_source_id, lineage)
            if previous != lineage:
                raise ValueError("Feature lineage identity is inconsistent")
            cells.append(
                {
                    "feature_definition_id": str(cell.feature_definition_id),
                    "reason_code": cell.reason_code,
                    "source_ids": sorted(
                        (str(feature_source_id), str(lineage_source_id))
                    ),
                    "status": cell.status.value,
                    "value": (
                        None if cell.value is None else format(cell.value, "f")
                    ),
                }
            )
            available_count += cell.status is FeatureCellStatus.AVAILABLE
        rows.append(
            {
                "cells": cells,
                "instrument_id": str(member.instrument_id),
                "population_source_id": str(population_source_id),
            }
        )

    sources = sorted(sources_by_id.values(), key=lambda item: str(item["dataset_source_id"]))
    payload = {
        "code_artifact": _artifact_payload(code_artifact),
        "config_artifact": _artifact_payload(config_artifact),
        "dataset_code": dataset_code,
        "dataset_id": str(dataset_id),
        "dataset_version": 1,
        "decision_time": decision_time.value.isoformat(),
        "eligibility_policy_id": str(eligibility_policy_id),
        "feature_definition_ids": [str(item) for item in feature_definition_ids],
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
    cell_count = len(ordered) * len(feature_definition_ids)
    return BacktestDatasetMaterialization(
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        decision_time=decision_time,
        universe_revision_id=universe_revision_id,
        eligibility_policy_id=eligibility_policy_id,
        feature_definition_ids=feature_definition_ids,
        code_artifact=code_artifact,
        config_artifact=config_artifact,
        manifest_content=content,
        row_count=len(ordered),
        available_cell_count=available_count,
        unavailable_cell_count=cell_count - available_count,
    )


def _artifact_payload(binding: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": str(binding.artifact_id),
        "content_sha256": str(ContentHash(str(binding.content_sha256))),
        "size_bytes": binding.size_bytes,
    }


__all__ = [
    "BacktestDatasetFeatureCell",
    "BacktestDatasetMaterialization",
    "BacktestDatasetMember",
    "BacktestFeatureLineageKind",
    "materialize_backtest_dataset",
]
