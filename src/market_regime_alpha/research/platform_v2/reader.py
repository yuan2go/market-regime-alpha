"""Checksum and semantic Reader for Platform V2 Research Layer Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.evidence.envelope import ArtifactEnvelope
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
)
from market_regime_alpha.research.platform_v2.artifact import (
    RESEARCH_LAYER_ARTIFACT_FILES,
    RESEARCH_LAYER_ARTIFACT_SCHEMA,
    ResearchLayerArtifact,
    ResearchLayerStatus,
    build_research_layer_manifest,
    render_research_layer_report,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle
from market_regime_alpha.research.theme_rotation.contracts import (
    ThemeRotationSnapshot,
)


@dataclass(frozen=True, slots=True)
class VerifiedResearchLayerArtifact:
    root: Path
    artifact: ResearchLayerArtifact
    checksums_hash: str


def load_verified_research_layer_artifact(
    path: Path,
) -> VerifiedResearchLayerArtifact:
    root = path.resolve()
    _verify_files(root)
    manifest = _read_object(root / "manifest.json")
    expected_manifest_fields = {
        "schema_version",
        "artifact_id",
        "content_hash",
        "status",
        "envelope",
        "source_manifest_id",
        "input_bundle_id",
        "configuration_id",
        "component_artifact_ids",
        "required_artifacts",
        "data_eligibility",
        "formal_pit",
        "formal_oos_alpha",
        "trading_authority",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("Research Layer manifest fields mismatch")
    if manifest["schema_version"] != RESEARCH_LAYER_ARTIFACT_SCHEMA:
        raise ValueError("unsupported Research Layer Artifact schema")
    artifact = ResearchLayerArtifact(
        envelope=ArtifactEnvelope.from_canonical_dict(
            _object(manifest["envelope"])
        ),
        inputs=ResearchInputBundle.from_canonical_dict(
            _read_object(root / "input_bundle.json")
        ),
        configuration=ResearchPipelineConfig.from_canonical_dict(
            _read_object(root / "configuration.json")
        ),
        market_regime=MarketRegimeSnapshot.from_canonical_dict(
            _read_object(root / "market_regime.json")
        ),
        theme_rotation=ThemeRotationSnapshot.from_canonical_dict(
            _read_object(root / "theme_rotation.json")
        ),
        capital_evolution=CapitalEvolutionSnapshot.from_canonical_dict(
            _read_object(root / "capital_evolution.json")
        ),
        candidate_set=CandidateSet.from_canonical_dict(
            _read_object(root / "candidate_set.json")
        ),
        research_status=ResearchLayerStatus(str(manifest["status"])),
        reason_codes=tuple(
            str(item)
            for item in _array(
                _object(manifest["envelope"])["reason_codes"]
            )
        ),
        limitations=tuple(
            str(item)
            for item in _array(
                _object(manifest["envelope"])["limitations"]
            )
        ),
    )
    if manifest != build_research_layer_manifest(artifact):
        raise ValueError("Research Layer manifest is not reconstructible")
    if root.name != str(artifact.artifact_id):
        raise ValueError("Research Layer directory identity mismatch")
    if (root / "report.md").read_text(
        encoding="utf-8"
    ) != render_research_layer_report(artifact):
        raise ValueError("Research Layer report is not reconstructible")
    return VerifiedResearchLayerArtifact(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("Research Layer Artifact is missing")
    if {item.name for item in root.iterdir()} != set(
        RESEARCH_LAYER_ARTIFACT_FILES
    ):
        raise ValueError("Research Layer exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("Research Layer exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(RESEARCH_LAYER_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Research Layer checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(
            root / name
        ) != expected_hash:
            raise ValueError(f"Research Layer checksum mismatch: {name}")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Research Layer JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Research Layer value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Research Layer value must be an array")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"

