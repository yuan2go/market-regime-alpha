from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    candidate_population_from_manifest,
    dataset_source_lineage_sha256,
)
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    DatasetSource,
    DatasetSourceRole,
    DecisionInputDatasetManifest,
    DecisionInputDatasetRow,
    FeatureCell,
    FeatureCellStatus,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.selection.domain import CandidateCellStatus
from market_regime_alpha.selection.ports import CandidateArtifactBinding
from market_regime_alpha.selection.ports.research_inputs import (
    CandidateDatasetDependency,
    CandidateFeatureDependency,
)
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


def _uuid(number: int) -> UUID:
    return UUID(int=number)


def _manifest(status: FeatureCellStatus) -> DecisionInputDatasetManifest:
    decision_time = DecisionTime(datetime(2026, 8, 30, 6, 30, tzinfo=UTC))
    feature_id = _uuid(10)
    unused_feature_id = _uuid(11)
    population_source_id = _uuid(20)
    feature_source_id = _uuid(21)
    unused_source_id = _uuid(22)
    market_source_id = _uuid(23)
    sources = (
        DatasetSource(
            dataset_source_id=population_source_id,
            role=DatasetSourceRole.POPULATION,
            instrument_id=_uuid(30),
            universe_member_id=_uuid(31),
            eligibility_assessment_id=_uuid(32),
        ),
        DatasetSource(
            dataset_source_id=feature_source_id,
            role=DatasetSourceRole.FEATURE_DEFINITION,
            feature_definition_id=feature_id,
        ),
        DatasetSource(
            dataset_source_id=unused_source_id,
            role=DatasetSourceRole.FEATURE_DEFINITION,
            feature_definition_id=unused_feature_id,
        ),
        DatasetSource(
            dataset_source_id=market_source_id,
            role=DatasetSourceRole.MARKET_BAR_REVISION,
            market_bar_revision_id=_uuid(40),
        ),
    )
    return DecisionInputDatasetManifest(
        dataset_id=_uuid(1),
        dataset_code="candidate-input",
        dataset_version=1,
        decision_time=decision_time,
        universe_revision_id=_uuid(2),
        eligibility_policy_id=_uuid(3),
        feature_definition_ids=(feature_id, unused_feature_id),
        code_artifact=ArtifactBinding(_uuid(4), "4" * 64, 4),
        config_artifact=ArtifactBinding(_uuid(5), "5" * 64, 5),
        sources=sources,
        rows=(
            DecisionInputDatasetRow(
                instrument_id=_uuid(30),
                population_source_id=population_source_id,
                cells=(
                    FeatureCell(
                        feature_definition_id=feature_id,
                        status=status,
                        value=(
                            Decimal("12.5")
                            if status is FeatureCellStatus.AVAILABLE
                            else None
                        ),
                        reason_code=(
                            "OBSERVED"
                            if status is FeatureCellStatus.AVAILABLE
                            else f"SOURCE_{status.value}"
                        ),
                        source_ids=(feature_source_id, market_source_id),
                    ),
                    FeatureCell(
                        feature_definition_id=unused_feature_id,
                        status=FeatureCellStatus.MISSING,
                        value=None,
                        reason_code="NOT_REQUIRED",
                        source_ids=(unused_source_id, market_source_id),
                    ),
                ),
            ),
        ),
        content_sha256=ContentHash("a" * 64),
    )


def _dataset(
    status: FeatureCellStatus = FeatureCellStatus.AVAILABLE,
) -> CandidateDatasetDependency:
    manifest = _manifest(status)
    return CandidateDatasetDependency(
        dataset_id=_uuid(1),
        content_sha256="a" * 64,
        decision_time=DecisionTime(datetime(2026, 8, 30, 6, 30, tzinfo=UTC)),
        universe_revision_id=_uuid(2),
        eligibility_policy_id=_uuid(3),
        row_count=1,
        feature_count=manifest.feature_count,
        source_count=manifest.source_count,
        cell_count=manifest.cell_count,
        available_cell_count=manifest.available_cell_count,
        missing_cell_count=manifest.missing_cell_count,
        unknown_cell_count=manifest.unknown_cell_count,
        stale_cell_count=manifest.stale_cell_count,
        conflict_cell_count=manifest.conflict_cell_count,
        dataset_source_lineage_sha256=dataset_source_lineage_sha256(
            manifest.sources
        ),
        manifest_artifact=CandidateArtifactBinding(_uuid(6), "6" * 64, 6),
        code_artifact=CandidateArtifactBinding(_uuid(4), "4" * 64, 4),
        config_artifact=CandidateArtifactBinding(_uuid(5), "5" * 64, 5),
    )


def _feature() -> CandidateFeatureDependency:
    return CandidateFeatureDependency(
        feature_definition_id=_uuid(10),
        content_sha256="b" * 64,
        value_type="DECIMAL",
    )


def test_infrastructure_translation_keeps_every_row_and_only_hashes_cell_sources() -> None:
    population = candidate_population_from_manifest(
        _manifest(FeatureCellStatus.AVAILABLE),
        dataset=_dataset(),
        required_features=(_feature(),),
        dependency_sha256="c" * 64,
    )

    assert population.row_count == 1
    assert population.rows[0].dataset_population_source_id == _uuid(20)
    assert len(population.rows[0].cells) == 1
    cell = population.rows[0].cells[0]
    assert cell.status is CandidateCellStatus.AVAILABLE
    assert cell.value == Decimal("12.5")
    assert len(str(cell.cell_source_lineage_hash)) == 64
    assert not hasattr(cell, "source_ids")
    assert not hasattr(cell, "dataset_source_ids")


def test_translation_preserves_each_non_available_status_without_half_imputation() -> None:
    for status in (
        FeatureCellStatus.MISSING,
        FeatureCellStatus.UNKNOWN,
        FeatureCellStatus.STALE,
        FeatureCellStatus.CONFLICT,
    ):
        population = candidate_population_from_manifest(
            _manifest(status),
            dataset=_dataset(status),
            required_features=(_feature(),),
            dependency_sha256="c" * 64,
        )
        cell = population.rows[0].cells[0]
        assert cell.status.value == status.value
        assert cell.value is None


def test_lineage_hash_binds_dataset_cell_and_sorted_source_identity() -> None:
    first = _manifest(FeatureCellStatus.AVAILABLE)
    original = candidate_population_from_manifest(
        first,
        dataset=_dataset(),
        required_features=(_feature(),),
        dependency_sha256="c" * 64,
    )
    cell = first.rows[0].cells[0]
    reordered_cell = FeatureCell(
        feature_definition_id=cell.feature_definition_id,
        status=cell.status,
        value=cell.value,
        reason_code=cell.reason_code,
        source_ids=tuple(reversed(cell.source_ids)),
    )
    reordered = DecisionInputDatasetManifest(
        dataset_id=first.dataset_id,
        dataset_code=first.dataset_code,
        dataset_version=first.dataset_version,
        decision_time=first.decision_time,
        universe_revision_id=first.universe_revision_id,
        eligibility_policy_id=first.eligibility_policy_id,
        feature_definition_ids=first.feature_definition_ids,
        code_artifact=first.code_artifact,
        config_artifact=first.config_artifact,
        sources=first.sources,
        rows=(
            DecisionInputDatasetRow(
                instrument_id=first.rows[0].instrument_id,
                population_source_id=first.rows[0].population_source_id,
                cells=(reordered_cell, first.rows[0].cells[1]),
            ),
        ),
        content_sha256=first.content_sha256,
    )
    translated = candidate_population_from_manifest(
        reordered,
        dataset=_dataset(),
        required_features=(_feature(),),
        dependency_sha256="c" * 64,
    )

    assert (
        original.rows[0].cells[0].cell_source_lineage_hash
        == translated.rows[0].cells[0].cell_source_lineage_hash
    )


def test_translation_fails_closed_on_dataset_counts_or_relational_lineage_drift() -> None:
    manifest = _manifest(FeatureCellStatus.AVAILABLE)

    with pytest.raises(ArtifactIntegrityError, match="counts"):
        candidate_population_from_manifest(
            manifest,
            dataset=replace(_dataset(), source_count=99),
            required_features=(_feature(),),
            dependency_sha256="c" * 64,
        )
    with pytest.raises(ArtifactIntegrityError, match="lineage"):
        candidate_population_from_manifest(
            manifest,
            dataset=replace(
                _dataset(),
                dataset_source_lineage_sha256="0" * 64,
            ),
            required_features=(_feature(),),
            dependency_sha256="c" * 64,
        )
