"""Compatibility adapter from Legacy MACD dataset manifests to canonical Data contracts.

The adapter preserves existing content-derived dataset identity while preventing Legacy
local classifications from silently becoming canonical FORMAL_RESEARCH eligibility.
"""

from __future__ import annotations

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract, ProviderReference
from market_regime_alpha.dividend_t.macd_oos import (
    DatasetClassification,
    DatasetManifest,
    dataset_version,
)


def adapt_legacy_dataset_manifest(
    manifest: DatasetManifest,
    *,
    manifest_artifact_id: ArtifactId,
    provider_references: tuple[ProviderReference, ...],
    scope: str,
    limitations: tuple[str, ...] = (),
) -> DatasetContract:
    """Expose a Legacy dataset manifest through the canonical DatasetContract.

    ``FORMAL_FINAL_CANDIDATE`` is intentionally rejected. The Glossary explicitly says
    it is a Legacy local classification, not canonical Data Eligibility. A separate
    canonical review must establish FORMAL_RESEARCH eligibility for a declared scope.
    """

    if manifest.classification is DatasetClassification.FIXTURE:
        eligibility = DataEligibility.UNQUALIFIED
    elif manifest.classification is DatasetClassification.REHEARSAL:
        eligibility = DataEligibility.REHEARSAL
    elif manifest.classification is DatasetClassification.FORMAL_FINAL_CANDIDATE:
        raise ValueError("CANONICAL_DATA_ELIGIBILITY_REVIEW_REQUIRED")
    else:  # pragma: no cover - defensive against future Legacy enum expansion
        raise ValueError(f"UNSUPPORTED_LEGACY_DATASET_CLASSIFICATION:{manifest.classification}")

    return DatasetContract(
        dataset_id=DatasetId(dataset_version(manifest)),
        schema_version=manifest.schema_version,
        eligibility=eligibility,
        manifest_artifact_id=manifest_artifact_id,
        provider_references=provider_references,
        pit_correct_for_scope=bool(manifest.pit_adjustment_complete),
        scope=scope,
        limitations=limitations,
    )
