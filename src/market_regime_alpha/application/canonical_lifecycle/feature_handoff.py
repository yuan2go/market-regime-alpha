"""Universe-first Feature materialization and Candidate projection service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
)
from market_regime_alpha.features.materialization_v2 import (
    FeatureRunRepositoryFactory,
    FeatureMaterializationRunner,
    VerifiedFeatureBundleV2,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.candidate_view import CandidateFeatureView


class UniverseFeatureScopeKind(str, Enum):
    PIT_UNIVERSE = "PIT_UNIVERSE"
    CONTROLLED_EXPLORATORY_UNIVERSE = "CONTROLLED_EXPLORATORY_UNIVERSE"


@dataclass(frozen=True, slots=True)
class UniverseFeatureHandoff:
    scope_kind: UniverseFeatureScopeKind
    universe_symbols: tuple[str, ...]
    verified_dataset: VerifiedMarketDataDataset
    feature_bundle: VerifiedFeatureBundleV2
    receipt: FeatureMaterializationReceipt


class OperationalFeatureHandoffRunner:
    """Materialize the full governed universe before Candidate Discovery."""

    def __init__(
        self,
        *,
        repository_factory: FeatureRunRepositoryFactory,
        max_workers: int = 1,
    ) -> None:
        self._runner = FeatureMaterializationRunner(
            max_workers=max_workers,
            repository_factory=repository_factory,
        )

    def materialize_universe(
        self,
        *,
        verified_dataset: VerifiedMarketDataDataset,
        feature_set: FeatureSetConfiguration,
        universe_symbols: tuple[str, ...],
        scope_kind: UniverseFeatureScopeKind,
        decision_time: datetime,
        created_at: datetime,
        code_revision: str,
        output_root: Path,
        idempotency_key: str,
        execution_mode: FeatureMaterializationExecutionMode,
    ) -> UniverseFeatureHandoff:
        expected = verified_dataset.artifact.coverage.expected_symbols
        if universe_symbols != tuple(sorted(set(universe_symbols))):
            raise ValueError("Feature universe symbols must be unique and sorted")
        if universe_symbols != expected:
            raise ValueError(
                "Universe Feature materialization must cover the complete Dataset scope"
            )
        if scope_kind is UniverseFeatureScopeKind.PIT_UNIVERSE and (
            verified_dataset.artifact.formal_pit_status.value
            != "PIT_CORRECT_FOR_DECLARED_SCOPE"
        ):
            raise ValueError("PIT_UNIVERSE requires PIT-correct Market Data authority")
        if (
            scope_kind is UniverseFeatureScopeKind.CONTROLLED_EXPLORATORY_UNIVERSE
            and verified_dataset.artifact.data_eligibility
            is not DataEligibility.EXPLORATORY
        ):
            raise ValueError(
                "controlled exploratory Feature scope must remain EXPLORATORY"
            )
        receipt = self._runner.run(
            verified_dataset=verified_dataset,
            feature_set=feature_set,
            decision_time=decision_time,
            created_at=created_at,
            selected_symbols=universe_symbols,
            code_revision=code_revision,
            output_root=output_root,
            idempotency_key=idempotency_key,
            execution_mode=execution_mode,
        )
        bundle = load_verified_feature_bundle_v2(
            output_root / receipt.bundle_locator,
            artifact_root=output_root / "feature-artifacts",
        )
        if bundle.artifact.symbols != universe_symbols:
            raise ValueError("Universe Feature Bundle scope changed during materialization")
        return UniverseFeatureHandoff(
            scope_kind=scope_kind,
            universe_symbols=universe_symbols,
            verified_dataset=verified_dataset,
            feature_bundle=bundle,
            receipt=receipt,
        )

    @staticmethod
    def project_candidates(
        *,
        handoff: UniverseFeatureHandoff,
        candidate_set: CandidateSet,
        minimum_data_eligibility: DataEligibility,
    ) -> CandidateFeatureView:
        return CandidateFeatureView.create(
            candidate_set=candidate_set,
            feature_bundle=handoff.feature_bundle,
            verified_dataset=handoff.verified_dataset,
            minimum_data_eligibility=minimum_data_eligibility,
        )


__all__ = [
    "OperationalFeatureHandoffRunner",
    "UniverseFeatureHandoff",
    "UniverseFeatureScopeKind",
]
