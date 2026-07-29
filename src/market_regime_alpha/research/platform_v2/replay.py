"""Semantic recomputation of a verified Research Layer Artifact."""

from __future__ import annotations

from market_regime_alpha.research.platform_v2.pipeline import (
    run_research_pipeline_v2,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
)


def replay_research_layer(
    verified: VerifiedResearchLayerArtifact,
) -> VerifiedResearchLayerArtifact:
    original = verified.artifact
    replayed = run_research_pipeline_v2(
        original.inputs,
        original.configuration,
        code_revision=original.envelope.code_revision,
    )
    if replayed != original:
        raise ValueError("Research Layer semantic replay mismatch")
    return verified

