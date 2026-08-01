"""Fail-closed application composition for operational research evidence."""

from __future__ import annotations

from pathlib import Path

from market_regime_alpha.application.operational_research.contracts import (
    SupplementalResearchEvidenceBundle,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.daily_decision.artifact import (
    DailyDecisionArtifactStatus,
)
from market_regime_alpha.daily_decision.reader import (
    VerifiedPhaseDDailyDecisionArtifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.serialization import (
    eligibility_snapshot_to_dict,
    universe_snapshot_to_dict,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchEvidenceKind,
    ResearchInputBundle,
    ThemeMembership,
    ThemeResearchObservation,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
)


def adapt_operational_research_inputs(
    daily: VerifiedPhaseDDailyDecisionArtifact,
    supplemental: SupplementalResearchEvidenceBundle,
) -> ResearchInputBundle:
    """Validate and combine authorities without deriving missing evidence."""

    bundle = daily.bundle
    if bundle.status is not DailyDecisionArtifactStatus.DECISION_PUBLISHED:
        raise ValueError("operational research requires a published Daily Artifact")
    if (
        bundle.universe_snapshot is None
        or bundle.eligibility_snapshot is None
        or bundle.decision_price_snapshot is None
    ):
        raise ValueError("published Daily Artifact omits required snapshots")
    if supplemental.decision_time != bundle.source_manifest.decision_time:
        raise ValueError("supplemental and Daily DecisionTime mismatch")
    if (
        bundle.source_manifest.data_eligibility
        is not DataEligibility.EXPLORATORY
        or supplemental.data_eligibility is not DataEligibility.EXPLORATORY
    ):
        raise ValueError("operational bridge cannot increase DataEligibility")
    if supplemental.missing_evidence:
        raise ValueError("supplemental evidence is incomplete")
    if not all(
        (
            supplemental.theme_observations,
            supplemental.capital_observations,
            supplemental.symbol_observations,
            supplemental.theme_memberships,
            supplemental.etf_theme_mappings,
            supplemental.etf_observations,
        )
    ):
        raise ValueError("supplemental evidence is incomplete")

    population = _prediction_population(bundle.prediction_runs)
    membership_symbols = {
        item.symbol for item in supplemental.theme_memberships
    }
    if membership_symbols != population:
        raise ValueError("PIT theme membership coverage mismatch")
    symbol_observation_symbols = {
        item.symbol for item in supplemental.symbol_observations
    }
    if symbol_observation_symbols != population:
        raise ValueError("supplemental symbol observation coverage mismatch")

    themes = {item.theme_id: item for item in supplemental.theme_observations}
    capital = {
        item.theme_id: item for item in supplemental.capital_observations
    }
    if set(themes) != set(capital):
        raise ValueError("Theme and Capital observation coverage mismatch")
    membership_theme_ids = {
        theme_id
        for item in supplemental.theme_memberships
        for theme_id in (item.primary_theme_id, *item.supporting_theme_ids)
    }
    if not membership_theme_ids.issubset(themes):
        raise ValueError("PIT theme membership references an unknown theme")

    mapping_by_etf = {
        item.etf_id: item for item in supplemental.etf_theme_mappings
    }
    expected_pairs = {
        (etf_id, theme.theme_id)
        for theme in supplemental.theme_observations
        for etf_id in theme.proxy_etf_ids
    }
    mapping_pairs = {
        (item.etf_id, item.theme_id)
        for item in supplemental.etf_theme_mappings
    }
    observation_pairs = {
        (item.etf_id, item.theme_id)
        for item in supplemental.etf_observations
    }
    if mapping_pairs != expected_pairs or observation_pairs != mapping_pairs:
        raise ValueError("ETF/Theme mapping coverage mismatch")
    if any(
        item.theme_id not in themes
        for item in mapping_by_etf.values()
    ):
        raise ValueError("ETF mapping references an unknown theme")

    theme_observations = tuple(
        _combine_theme_and_capital(theme, capital[theme.theme_id])
        for theme in supplemental.theme_observations
    )
    input_lineage: dict[ArtifactId, str] = {}

    def add_lineage(artifact_id: ArtifactId, content_hash: str) -> None:
        existing = input_lineage.get(artifact_id)
        if existing is not None and existing != content_hash:
            raise ValueError("input Artifact identity has conflicting hashes")
        input_lineage[artifact_id] = content_hash

    add_lineage(ArtifactId(daily.artifact_id), bundle.content_hash)
    add_lineage(supplemental.bundle_id, supplemental.content_hash)
    add_lineage(
        bundle.source_manifest.source_manifest_id,
        bundle.source_manifest.content_hash,
    )
    add_lineage(
        supplemental.source_manifest.source_manifest_id,
        supplemental.source_manifest.content_hash,
    )
    add_lineage(
        bundle.universe_snapshot.evidence_artifact_id,
        canonical_hash(universe_snapshot_to_dict(bundle.universe_snapshot)),
    )
    add_lineage(
        bundle.eligibility_snapshot.evidence_artifact_id,
        canonical_hash(
            eligibility_snapshot_to_dict(bundle.eligibility_snapshot)
        ),
    )
    add_lineage(
        bundle.decision_price_snapshot.decision_snapshot_id,
        bundle.decision_price_snapshot.content_hash,
    )
    for source in supplemental.source_manifest.source_artifacts:
        add_lineage(source.artifact_id, source.content_hash)
    ordered = tuple(sorted(input_lineage.items(), key=lambda item: str(item[0])))
    return ResearchInputBundle(
        evidence_kind=ResearchEvidenceKind.HISTORICAL_IMMUTABLE_ARCHIVE,
        source_manifest=bundle.source_manifest,
        universe_snapshot=bundle.universe_snapshot,
        eligibility_snapshot=bundle.eligibility_snapshot,
        decision_price_snapshot=bundle.decision_price_snapshot,
        market_observation=supplemental.market_observation,
        theme_observations=theme_observations,
        symbol_observations=supplemental.symbol_observations,
        theme_memberships=tuple(
            ThemeMembership(
                symbol=item.symbol,
                primary_theme_id=item.primary_theme_id,
                supporting_theme_ids=item.supporting_theme_ids,
            )
            for item in supplemental.theme_memberships
        ),
        etf_observations=supplemental.etf_observations,
        stock_daily_bars=supplemental.stock_daily_bars,
        prediction_runs=bundle.prediction_runs,
        input_artifact_ids=tuple(item[0] for item in ordered),
        input_content_hashes=tuple(item[1] for item in ordered),
        created_at=supplemental.created_at,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


class OperationalResearchRunner:
    """Application service for verified run and semantic replay."""

    def __init__(self) -> None:
        self._research = PlatformResearchRunner()

    def run(
        self,
        *,
        daily_artifact_path: Path,
        supplemental_artifact_path: Path,
        configuration: ResearchPipelineConfig,
        output_root: Path,
        code_revision: str,
    ) -> VerifiedResearchLayerArtifact:
        daily = load_verified_daily_decision_artifact(daily_artifact_path)
        supplemental = load_verified_supplemental_research_evidence(
            supplemental_artifact_path
        )
        inputs = adapt_operational_research_inputs(daily, supplemental.bundle)
        return self._research.run(
            inputs=inputs,
            configuration=configuration,
            output_root=output_root,
            code_revision=code_revision,
        )

    def replay(self, path: Path) -> VerifiedResearchLayerArtifact:
        return self._research.replay(path)


def _prediction_population(prediction_runs: tuple[object, ...]) -> set[str]:
    if not prediction_runs:
        raise ValueError("Daily Artifact has no PredictionRuns")
    populations: list[set[str]] = []
    from market_regime_alpha.platform.prediction_run import PredictionRun

    for value in prediction_runs:
        if not isinstance(value, PredictionRun):
            raise TypeError("prediction_runs must contain PredictionRun")
        populations.append(
            {
                *(item.symbol for item in value.predictions),
                *(item.symbol for item in value.rejections),
            }
        )
    if any(population != populations[0] for population in populations[1:]):
        raise ValueError("PredictionRun population mismatch")
    return populations[0]


def _combine_theme_and_capital(
    theme: object,
    capital: object,
) -> ThemeResearchObservation:
    from market_regime_alpha.application.operational_research.contracts import (
        CapitalObservationEvidence,
        ThemeObservationEvidence,
    )

    if not isinstance(theme, ThemeObservationEvidence) or not isinstance(
        capital, CapitalObservationEvidence
    ):
        raise TypeError("theme and capital evidence types mismatch")
    return ThemeResearchObservation(
        theme_id=theme.theme_id,
        theme_name=theme.theme_name,
        benchmark_id=theme.benchmark_id,
        proxy_etf_ids=theme.proxy_etf_ids,
        available_at=(
            theme.available_at
            if theme.available_at.value >= capital.available_at.value
            else capital.available_at
        ),
        source_artifact_id=capital.source_artifact_id,
        relative_strength_1d=theme.relative_strength_1d,
        relative_strength_3d=theme.relative_strength_3d,
        relative_strength_5d=theme.relative_strength_5d,
        relative_strength_10d=theme.relative_strength_10d,
        amount_expansion=theme.amount_expansion,
        etf_amount_expansion=capital.etf_amount_expansion,
        breadth=theme.breadth,
        new_high_breadth=theme.new_high_breadth,
        leader_strength=theme.leader_strength,
        participation_change=theme.participation_change,
        rank_persistence=theme.rank_persistence,
        amount_persistence=capital.amount_persistence,
        capital_concentration=capital.capital_concentration,
        diffusion_score=capital.diffusion_score,
        confidence=theme.confidence,
        reason_codes=tuple(
            dict.fromkeys((*theme.reason_codes, *capital.reason_codes))
        ),
    )
