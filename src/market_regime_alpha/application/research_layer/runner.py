"""Thin application orchestration for run/read/replay/report operations."""

from __future__ import annotations

from pathlib import Path

from market_regime_alpha.research.platform_v2.artifact import (
    ResearchLayerArtifact,
    publish_research_layer_artifact,
    render_research_layer_report,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundleAny
from market_regime_alpha.research.platform_v2.pipeline import (
    run_research_pipeline_v2,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.research.platform_v2.replay import (
    replay_research_layer,
)


class PlatformResearchRunner:
    def run(
        self,
        *,
        inputs: ResearchInputBundleAny,
        configuration: ResearchPipelineConfig,
        output_root: Path,
        code_revision: str,
    ) -> VerifiedResearchLayerArtifact:
        artifact = run_research_pipeline_v2(
            inputs, configuration, code_revision=code_revision
        )
        try:
            path = publish_research_layer_artifact(
                root=output_root, artifact=artifact
            )
        except FileExistsError:
            path = output_root / str(artifact.artifact_id)
        verified = load_verified_research_artifact(path)
        if verified.artifact != artifact:
            raise ValueError("existing Research Layer Artifact semantic mismatch")
        return verified

    def replay(self, path: Path) -> VerifiedResearchLayerArtifact:
        return replay_research_layer(load_verified_research_artifact(path))

    def report(self, path: Path) -> str:
        return render_research_layer_report(
            load_verified_research_artifact(path).artifact
        )

    def compute(
        self,
        *,
        inputs: ResearchInputBundleAny,
        configuration: ResearchPipelineConfig,
        code_revision: str,
    ) -> ResearchLayerArtifact:
        return run_research_pipeline_v2(
            inputs, configuration, code_revision=code_revision
        )
