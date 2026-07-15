"""Compatibility adapter from Legacy MACD experiment identity to the V2 contract.

The adapter is intentionally outside ``core`` and ``research`` so the canonical V2
contracts do not depend on Legacy implementation modules. The caller supplies the
Legacy canonical config hash computed by the existing MACD identity implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.research.experiment_identity import ExperimentIdentity


@runtime_checkable
class LegacyMACDExperimentIdentityLike(Protocol):
    """Minimal Legacy fields required to create a V2 compatibility reference."""

    git_commit: str
    dataset_version: str
    data_split_hash: str
    pipeline_id: str
    execution_config_hash: str
    sizing_owner: str


def adapt_legacy_macd_experiment_identity(
    identity: LegacyMACDExperimentIdentityLike,
    *,
    legacy_config_hash: str,
) -> ExperimentIdentity:
    """Map a Legacy MACD identity into the canonical project experiment identity.

    This does not claim that the Legacy object already has canonical Universe, Target,
    or Feature identities. Those remain absent until explicitly reconstructed. The
    complete Legacy result-affecting configuration remains anchored by the existing
    ``legacy_config_hash``.
    """

    if not isinstance(identity, LegacyMACDExperimentIdentityLike):
        raise TypeError("identity does not satisfy LegacyMACDExperimentIdentityLike")
    if not isinstance(legacy_config_hash, str) or not legacy_config_hash.strip():
        raise ValueError("legacy_config_hash must be a non-empty trimmed string")
    if legacy_config_hash != legacy_config_hash.strip():
        raise ValueError("legacy_config_hash must be a non-empty trimmed string")

    return ExperimentIdentity(
        code_revision=identity.git_commit,
        dataset_id=DatasetId(f"legacy-macd-dataset-version:{identity.dataset_version}"),
        config_hash=legacy_config_hash,
        execution_assumption_ref=f"legacy-macd-execution:{identity.execution_config_hash}",
        semantic_refs=(
            ("compatibility_adapter", "legacy-macd-experiment-identity-v1"),
            ("legacy_data_split_hash", identity.data_split_hash),
            ("legacy_pipeline_id", identity.pipeline_id),
            ("legacy_sizing_owner", identity.sizing_owner),
        ),
    )
