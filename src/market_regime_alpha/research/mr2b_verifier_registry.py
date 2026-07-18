"""Versioned verifier routing for immutable MR-2B F2B artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b_reader import load_verified_f2b_run
from market_regime_alpha.research.mr2b_f2b_v2_reader import load_verified_f2b_v2_run
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset
from market_regime_alpha.research.prr_artifact_schemas import (
    MR2B_F2B_RUN_SCHEMA,
    MR2B_F2B_V2_RUN_SCHEMA,
)


Verifier = Callable[..., object]


@dataclass(frozen=True, slots=True)
class ArtifactVerifierRegistration:
    schema_version: str
    verifier_id: str
    loader: Verifier


def build_verifier_registry(
    registrations: tuple[ArtifactVerifierRegistration, ...],
) -> dict[str, ArtifactVerifierRegistration]:
    output: dict[str, ArtifactVerifierRegistration] = {}
    for registration in registrations:
        if registration.schema_version in output:
            raise ValueError("duplicate MR-2B verifier registration")
        output[registration.schema_version] = registration
    return output


MR2B_VERIFIER_REGISTRY = build_verifier_registry(
    (
        ArtifactVerifierRegistration(MR2B_F2B_RUN_SCHEMA.schema_version, "mr2b-f2b-v1-semantic-reader", load_verified_f2b_run),
        ArtifactVerifierRegistration(MR2B_F2B_V2_RUN_SCHEMA.schema_version, "mr2b-f2b-v2-semantic-reader", load_verified_f2b_v2_run),
    )
)


def load_verified_mr2b_f2b_run(
    path: Path, *, dataset: VerifiedPRRDataset, mr1: VerifiedMR1Run, f2a: VerifiedF2ARun
) -> object:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("MR-2B F2B manifest is missing")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = payload.get("schema_version") if isinstance(payload, dict) else None
    registration = MR2B_VERIFIER_REGISTRY.get(str(schema))
    if registration is None:
        raise ValueError("unknown MR-2B F2B Artifact schema")
    result = registration.loader(path, dataset=dataset, mr1=mr1, f2a=f2a)
    verified_schema = getattr(getattr(result, "manifest", None), "get", lambda *_: None)("schema_version")
    if verified_schema != registration.schema_version:
        raise ValueError("MR-2B verifier schema mismatch")
    return result
