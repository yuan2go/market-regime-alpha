"""Versioned Reader routing for Research Layer Artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from market_regime_alpha.research.platform_v2.artifact import (
    RESEARCH_LAYER_ARTIFACT_SCHEMA,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
    load_verified_research_layer_artifact,
)


ResearchLayerLoader = Callable[[Path], VerifiedResearchLayerArtifact]
RESEARCH_LAYER_READER_REGISTRY: dict[str, ResearchLayerLoader] = {
    RESEARCH_LAYER_ARTIFACT_SCHEMA: load_verified_research_layer_artifact,
}


def load_verified_research_artifact(
    path: Path,
) -> VerifiedResearchLayerArtifact:
    manifest_path = path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Research Layer manifest is invalid") from exc
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("schema_version"), str
    ):
        raise ValueError("Research Layer manifest schema is missing")
    schema = str(manifest["schema_version"])
    loader = RESEARCH_LAYER_READER_REGISTRY.get(schema)
    if loader is None:
        raise ValueError(f"unsupported Research Layer Artifact schema: {schema}")
    return loader(path)

