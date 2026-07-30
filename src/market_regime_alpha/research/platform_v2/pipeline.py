"""Independent Platform V2 Research Layer orchestration."""

from __future__ import annotations

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
)
from market_regime_alpha.research.candidate_discovery.model import (
    discover_candidates_v2,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.capital_evolution.model import (
    evaluate_capital_evolution_v0,
)
from market_regime_alpha.research.market_regime.contracts import TradePermission
from market_regime_alpha.research.market_regime.model import (
    evaluate_market_regime_v0,
)
from market_regime_alpha.research.platform_v2.artifact import (
    ResearchLayerArtifact,
    ResearchLayerStatus,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.research.theme_rotation.model import (
    evaluate_theme_rotation_v0,
)


def run_research_pipeline_v2(
    inputs: ResearchInputBundle,
    config: ResearchPipelineConfig,
    *,
    code_revision: str,
) -> ResearchLayerArtifact:
    market = evaluate_market_regime_v0(
        inputs,
        config.market_regime,
        code_revision=code_revision,
    )
    themes = evaluate_theme_rotation_v0(
        inputs,
        config.theme_rotation,
        code_revision=code_revision,
    )
    capital = evaluate_capital_evolution_v0(
        inputs,
        themes,
        config.capital_evolution,
        code_revision=code_revision,
    )
    candidates = discover_candidates_v2(
        inputs,
        market,
        themes,
        capital,
        config.candidate_discovery,
        code_revision=code_revision,
    )
    theme_insufficient = not themes.themes or all(
        item.rotation_state is RotationState.DATA_INSUFFICIENT
        for item in themes.themes
    )
    capital_insufficient = not capital.themes or all(
        item.capital_evolution_state is CapitalEvolutionState.DATA_INSUFFICIENT
        for item in capital.themes
    )
    candidate_insufficient = (
        "CANDIDATE_POPULATION_INSUFFICIENT" in candidates.reason_codes
    )
    if theme_insufficient or capital_insufficient or candidate_insufficient:
        status = ResearchLayerStatus.RESEARCH_BLOCKED
    elif market.trade_permission is not TradePermission.ALLOW:
        status = ResearchLayerStatus.RESEARCH_RESTRICTED
    else:
        status = ResearchLayerStatus.RESEARCH_READY
    reasons = tuple(
        dict.fromkeys(
            (
                *(
                    ("THEME_ROTATION_DATA_INSUFFICIENT",)
                    if theme_insufficient
                    else ()
                ),
                *(
                    ("CAPITAL_EVOLUTION_DATA_INSUFFICIENT",)
                    if capital_insufficient
                    else ()
                ),
                *(
                    ("CANDIDATE_POPULATION_INSUFFICIENT",)
                    if candidate_insufficient
                    else ()
                ),
                *(
                    ("MARKET_REGIME_PROHIBITS_RISK",)
                    if market.trade_permission is TradePermission.PROHIBIT
                    else ()
                ),
                f"RESEARCH_STATUS_{status.value}",
            )
        )
    )
    limitations = tuple(
        dict.fromkeys(
            (
                *config.assumptions,
                f"EVIDENCE_KIND_{inputs.evidence_kind.value}",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "TRADING_AUTHORITY_NOT_GRANTED",
            )
        )
    )
    component_ids = (
        market.envelope.artifact_id,
        themes.envelope.artifact_id,
        capital.envelope.artifact_id,
        candidates.envelope.artifact_id,
    )
    component_hashes = (
        market.envelope.content_hash,
        themes.envelope.content_hash,
        capital.envelope.content_hash,
        candidates.envelope.content_hash,
    )
    semantic_payload = ResearchLayerArtifact.semantic_payload_for(
        market_regime=market,
        theme_rotation=themes,
        capital_evolution=capital,
        candidate_set=candidates,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        input_bundle_id=inputs.input_bundle_id,
        configuration_ids=(
            config.market_regime.configuration_id,
            config.theme_rotation.configuration_id,
            config.capital_evolution.configuration_id,
            config.candidate_discovery.configuration_id,
            config.configuration_id,
        ),
        model_ids=(
            config.market_regime.model_id,
            config.theme_rotation.model_id,
            config.capital_evolution.model_id,
            config.candidate_discovery.model_id,
        ),
        research_status=status,
        reason_codes=reasons,
        limitations=limitations,
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="RESEARCH_LAYER_ARTIFACT",
        artifact_payload=semantic_payload,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=config.configuration_id,
        configuration_hash=config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=(inputs.input_bundle_id, *component_ids),
        input_content_hashes=(inputs.content_hash, *component_hashes),
        model_id=None,
        model_version=None,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=status.value,
        reason_codes=reasons,
        limitations=limitations,
    )
    return ResearchLayerArtifact(
        envelope=envelope,
        inputs=inputs,
        configuration=config,
        market_regime=market,
        theme_rotation=themes,
        capital_evolution=capital,
        candidate_set=candidates,
        research_status=status,
        reason_codes=reasons,
        limitations=limitations,
    )

