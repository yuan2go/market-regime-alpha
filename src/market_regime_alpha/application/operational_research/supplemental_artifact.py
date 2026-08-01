"""Exact-file-set publisher and semantic reader for supplemental evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.application.operational_research.contracts import (
    SUPPLEMENTAL_RESEARCH_EVIDENCE_SCHEMA,
    SupplementalResearchEvidenceBundle,
)


SUPPLEMENTAL_RESEARCH_EVIDENCE_ARTIFACT_SCHEMA = (
    "supplemental-research-evidence-artifact-v1"
)
SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES = (
    "SHA256SUMS.json",
    "bundle.json",
    "manifest.json",
)


@dataclass(frozen=True, slots=True)
class VerifiedSupplementalResearchEvidence:
    root: Path
    bundle: SupplementalResearchEvidenceBundle
    checksums_hash: str


def _manifest(bundle: SupplementalResearchEvidenceBundle) -> dict[str, Any]:
    return {
        "schema_version": SUPPLEMENTAL_RESEARCH_EVIDENCE_ARTIFACT_SCHEMA,
        "bundle_schema_version": SUPPLEMENTAL_RESEARCH_EVIDENCE_SCHEMA,
        "bundle_id": str(bundle.bundle_id),
        "content_hash": bundle.content_hash,
        "source_manifest_id": str(
            bundle.source_manifest.source_manifest_id
        ),
        "source_manifest_hash": bundle.source_manifest.content_hash,
        "decision_time": bundle.decision_time.isoformat(),
        "data_eligibility": bundle.data_eligibility.value,
        "required_artifacts": sorted(SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES),
        "formal_pit": "NOT_ESTABLISHED",
        "formal_oos_alpha": "NOT_ESTABLISHED",
        "trading_authority": "NOT_GRANTED",
    }


def publish_supplemental_research_evidence(
    *, root: Path, bundle: SupplementalResearchEvidenceBundle
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(bundle.bundle_id)
    if final.exists():
        raise FileExistsError(f"Supplemental evidence Artifact exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_json(stage / "manifest.json", _manifest(bundle))
        _write_json(stage / "bundle.json", bundle.to_canonical_dict())
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES
                if name != "SHA256SUMS.json"
            },
        )
        if {item.name for item in stage.iterdir()} != set(
            SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES
        ):
            raise RuntimeError("supplemental evidence exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def load_verified_supplemental_research_evidence(
    path: Path,
) -> VerifiedSupplementalResearchEvidence:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES
    ):
        raise ValueError("supplemental evidence exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("supplemental evidence contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(SUPPLEMENTAL_RESEARCH_EVIDENCE_FILES) - {
        "SHA256SUMS.json"
    }
    if set(checksums) != expected:
        raise ValueError("supplemental evidence checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(
            root / name
        ) != expected_hash:
            raise ValueError(f"supplemental evidence checksum mismatch: {name}")
    bundle = SupplementalResearchEvidenceBundle.from_canonical_dict(
        _read_object(root / "bundle.json")
    )
    manifest = _read_object(root / "manifest.json")
    if manifest != _manifest(bundle):
        raise ValueError("supplemental evidence manifest is not reconstructible")
    if root.name != str(bundle.bundle_id):
        raise ValueError("supplemental evidence directory identity mismatch")
    return VerifiedSupplementalResearchEvidence(
        root=root,
        bundle=bundle,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


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


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid supplemental evidence JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
