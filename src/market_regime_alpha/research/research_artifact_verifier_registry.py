"""Versioned routing for immutable research Artifact semantic readers.

The registry is deliberately excluded from every statistical Artifact identity:
adding a future reader must not invalidate historical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, cast

from market_regime_alpha.research.mr2b_f2b_reader import load_verified_f2b_run
from market_regime_alpha.research.mr2b_f2b_v2_reader import load_verified_f2b_v2_run
from market_regime_alpha.research.mr2b_f2b_v3_reader import load_verified_f2b_v3_run


class VerifiedResearchArtifact(Protocol):
    root: Path
    run_id: str
    manifest: Mapping[str, Any]


ArtifactLoader = Callable[..., VerifiedResearchArtifact]


@dataclass(frozen=True, slots=True)
class ArtifactVerifierRegistration:
    schema_version: str
    verifier_id: str
    loader: ArtifactLoader


def build_verifier_registry(
    registrations: tuple[ArtifactVerifierRegistration, ...],
) -> Mapping[str, ArtifactVerifierRegistration]:
    output: dict[str, ArtifactVerifierRegistration] = {}
    for registration in registrations:
        if not registration.schema_version or not registration.verifier_id:
            raise ValueError("research Artifact verifier identity must be non-empty")
        if registration.schema_version in output:
            raise ValueError(f"duplicate research Artifact verifier: {registration.schema_version}")
        output[registration.schema_version] = registration
    return output


RESEARCH_ARTIFACT_VERIFIER_REGISTRY = build_verifier_registry(
    (
        ArtifactVerifierRegistration(
            "mr-2b-f2b-run-v1",
            "mr2b-f2b-v1-semantic-reader",
            cast(ArtifactLoader, load_verified_f2b_run),
        ),
        ArtifactVerifierRegistration(
            "mr-2b-f2b-run-v2",
            "mr2b-f2b-v2-semantic-reader",
            cast(ArtifactLoader, load_verified_f2b_v2_run),
        ),
        ArtifactVerifierRegistration(
            "mr-2b-f2b-run-v3",
            "mr2b-f2b-v3-semantic-reader",
            cast(ArtifactLoader, load_verified_f2b_v3_run),
        ),
    )
)


def load_verified_research_artifact(
    path: Path,
    *,
    dataset: object,
    mr1: object,
    f2a: object,
) -> VerifiedResearchArtifact:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("research Artifact manifest is missing")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("research Artifact manifest must be an object")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str):
        raise ValueError("research Artifact schema_version is missing")
    registration = RESEARCH_ARTIFACT_VERIFIER_REGISTRY.get(schema_version)
    if registration is None:
        raise ValueError(f"unsupported research Artifact schema: {schema_version}")
    verified = registration.loader(path, dataset=dataset, mr1=mr1, f2a=f2a)
    returned_schema = verified.manifest.get("schema_version")
    if returned_schema != registration.schema_version:
        raise ValueError("research Artifact verifier returned the wrong schema")
    return verified
