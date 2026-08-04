"""Atomic exact-file-set Research Layer Artifact Publisher."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.envelope import ArtifactEnvelope
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundleAny
from market_regime_alpha.research.theme_rotation.contracts import (
    ThemeRotationSnapshot,
)


RESEARCH_LAYER_ARTIFACT_SCHEMA = "platform-v2-research-layer-artifact-v1"
RESEARCH_LAYER_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "candidate_set.json",
    "capital_evolution.json",
    "configuration.json",
    "input_bundle.json",
    "manifest.json",
    "market_regime.json",
    "report.md",
    "theme_rotation.json",
)


class ResearchLayerStatus(str, Enum):
    RESEARCH_READY = "RESEARCH_READY"
    RESEARCH_RESTRICTED = "RESEARCH_RESTRICTED"
    RESEARCH_BLOCKED = "RESEARCH_BLOCKED"


@dataclass(frozen=True, slots=True)
class ResearchLayerArtifact:
    envelope: ArtifactEnvelope
    inputs: ResearchInputBundleAny
    configuration: ResearchPipelineConfig
    market_regime: MarketRegimeSnapshot
    theme_rotation: ThemeRotationSnapshot
    capital_evolution: CapitalEvolutionSnapshot
    candidate_set: CandidateSet
    research_status: ResearchLayerStatus
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.envelope.status != self.research_status.value:
            raise ValueError("Research Layer status does not match Envelope")
        component_ids = {
            self.market_regime.envelope.artifact_id,
            self.theme_rotation.envelope.artifact_id,
            self.capital_evolution.envelope.artifact_id,
            self.candidate_set.envelope.artifact_id,
        }
        if not component_ids.issubset(set(self.envelope.input_artifact_ids)):
            raise ValueError("Research Layer Envelope omits component lineage")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    @property
    def content_hash(self) -> str:
        return self.envelope.content_hash

    @staticmethod
    def semantic_payload_for(
        *,
        market_regime: MarketRegimeSnapshot,
        theme_rotation: ThemeRotationSnapshot,
        capital_evolution: CapitalEvolutionSnapshot,
        candidate_set: CandidateSet,
        source_manifest_id: ArtifactId,
        input_bundle_id: ArtifactId,
        configuration_ids: tuple[ArtifactId, ...],
        model_ids: tuple[ModelId, ...],
        research_status: ResearchLayerStatus,
        reason_codes: tuple[str, ...],
        limitations: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "market_regime_snapshot": _reference(market_regime.envelope),
            "theme_rotation_snapshot": _reference(theme_rotation.envelope),
            "capital_evolution_snapshot": _reference(
                capital_evolution.envelope
            ),
            "candidate_set": _reference(candidate_set.envelope),
            "source_manifest_id": str(source_manifest_id),
            "input_bundle_id": str(input_bundle_id),
            "configuration_ids": [str(item) for item in configuration_ids],
            "model_ids": [str(item) for item in model_ids],
            "research_status": research_status.value,
            "reason_codes": list(reason_codes),
            "limitations": list(limitations),
        }

    def artifact_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            market_regime=self.market_regime,
            theme_rotation=self.theme_rotation,
            capital_evolution=self.capital_evolution,
            candidate_set=self.candidate_set,
            source_manifest_id=self.inputs.source_manifest.source_manifest_id,
            input_bundle_id=self.inputs.input_bundle_id,
            configuration_ids=(
                self.configuration.market_regime.configuration_id,
                self.configuration.theme_rotation.configuration_id,
                self.configuration.capital_evolution.configuration_id,
                self.configuration.candidate_discovery.configuration_id,
                self.configuration.configuration_id,
            ),
            model_ids=(
                self.configuration.market_regime.model_id,
                self.configuration.theme_rotation.model_id,
                self.configuration.capital_evolution.model_id,
                self.configuration.candidate_discovery.model_id,
            ),
            research_status=self.research_status,
            reason_codes=self.reason_codes,
            limitations=self.limitations,
        )


def build_research_layer_manifest(
    artifact: ResearchLayerArtifact,
) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_LAYER_ARTIFACT_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.content_hash,
        "status": artifact.research_status.value,
        "envelope": artifact.envelope.to_canonical_dict(),
        "source_manifest_id": str(
            artifact.inputs.source_manifest.source_manifest_id
        ),
        "input_bundle_id": str(artifact.inputs.input_bundle_id),
        "configuration_id": str(artifact.configuration.configuration_id),
        "component_artifact_ids": [
            str(artifact.market_regime.envelope.artifact_id),
            str(artifact.theme_rotation.envelope.artifact_id),
            str(artifact.capital_evolution.envelope.artifact_id),
            str(artifact.candidate_set.envelope.artifact_id),
        ],
        "required_artifacts": sorted(RESEARCH_LAYER_ARTIFACT_FILES),
        "data_eligibility": artifact.envelope.data_eligibility.value,
        "formal_pit": artifact.envelope.formal_pit,
        "formal_oos_alpha": artifact.envelope.formal_oos_alpha,
        "trading_authority": artifact.envelope.trading_authority,
    }


def publish_research_layer_artifact(
    *, root: Path, artifact: ResearchLayerArtifact
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        raise FileExistsError(f"Research Layer Artifact exists: {final}")
    stage = Path(
        tempfile.mkdtemp(prefix=f".{artifact.artifact_id}.", dir=root)
    )
    try:
        _write_json(stage / "manifest.json", build_research_layer_manifest(artifact))
        _write_json(
            stage / "input_bundle.json", artifact.inputs.to_canonical_dict()
        )
        _write_json(
            stage / "configuration.json",
            artifact.configuration.to_canonical_dict(),
        )
        _write_json(
            stage / "market_regime.json",
            artifact.market_regime.to_canonical_dict(),
        )
        _write_json(
            stage / "theme_rotation.json",
            artifact.theme_rotation.to_canonical_dict(),
        )
        _write_json(
            stage / "capital_evolution.json",
            artifact.capital_evolution.to_canonical_dict(),
        )
        _write_json(
            stage / "candidate_set.json",
            artifact.candidate_set.to_canonical_dict(),
        )
        (stage / "report.md").write_text(
            render_research_layer_report(artifact),
            encoding="utf-8",
        )
        checksums = {
            name: _file_hash(stage / name)
            for name in RESEARCH_LAYER_ARTIFACT_FILES
            if name != "SHA256SUMS.json"
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        if {item.name for item in stage.iterdir()} != set(
            RESEARCH_LAYER_ARTIFACT_FILES
        ):
            raise RuntimeError("Research Layer staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def render_research_layer_report(artifact: ResearchLayerArtifact) -> str:
    selected = artifact.candidate_set.selected
    lines = [
        "# Platform V2 Research Layer Report",
        "",
        f"- Artifact: `{artifact.artifact_id}`",
        f"- Status: `{artifact.research_status.value}`",
        f"- Evidence Kind: `{artifact.inputs.evidence_kind.value}`",
        f"- Market State: `{artifact.market_regime.market_state.value}`",
        f"- Trade Permission: `{artifact.market_regime.trade_permission.value}`",
        f"- Theme Count: `{len(artifact.theme_rotation.themes)}`",
        f"- Capital Symbol Count: `{len(artifact.capital_evolution.symbols)}`",
        f"- Candidate Reconciliation Count: `{len(artifact.candidate_set.records)}`",
        f"- Selected Research Candidates: `{len(selected)}`",
        "",
        "## Authority",
        "",
        "- `data_eligibility = EXPLORATORY`",
        "- `formal_pit = NOT_ESTABLISHED`",
        "- `formal_oos_alpha = NOT_ESTABLISHED`",
        "- `trading_authority = NOT_GRANTED`",
        "",
        "CandidateSet is research opportunity discovery, not a buy list.",
        "",
    ]
    return "\n".join(lines)


def _reference(envelope: ArtifactEnvelope) -> dict[str, str]:
    return {
        "artifact_id": str(envelope.artifact_id),
        "content_hash": envelope.content_hash,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
