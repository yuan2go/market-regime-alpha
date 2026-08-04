"""Read-only Candidate projection over one universe-scoped Feature Bundle.

The view contains references only.  Feature values remain authoritative in the
original immutable Feature Artifacts and are resolved by the verified Bundle
reader when Signal inputs are assembled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.v2_contracts import FeatureArtifactReferenceV2
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet


CANDIDATE_FEATURE_VIEW_SCHEMA = "candidate-feature-view-v1"

_ELIGIBILITY_ORDER = {
    DataEligibility.UNQUALIFIED: 0,
    DataEligibility.EXPLORATORY: 1,
    DataEligibility.REHEARSAL: 2,
    DataEligibility.FORMAL_RESEARCH: 3,
}


@dataclass(frozen=True, slots=True)
class CandidateFeatureView:
    """Content-addressed reference projection; never a second Feature authority."""

    schema_version: str
    view_id: ArtifactId
    content_hash: str
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    dataset_id: DatasetId
    dataset_hash: str
    decision_time: datetime
    universe_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    feature_artifact_references: tuple[FeatureArtifactReferenceV2, ...]
    data_eligibility: DataEligibility

    def __post_init__(self) -> None:
        if self.schema_version != CANDIDATE_FEATURE_VIEW_SCHEMA:
            raise ValueError("unsupported Candidate Feature View schema")
        for label, value in (
            ("content_hash", self.content_hash),
            ("feature_bundle_hash", self.feature_bundle_hash),
            ("candidate_set_hash", self.candidate_set_hash),
            ("dataset_hash", self.dataset_hash),
        ):
            require_sha256(label, value)
        require_utc_second("decision_time", self.decision_time)
        if not self.universe_symbols or self.universe_symbols != tuple(
            sorted(set(self.universe_symbols))
        ):
            raise ValueError("Candidate Feature View universe must be non-empty and sorted")
        if self.candidate_symbols != tuple(sorted(set(self.candidate_symbols))):
            raise ValueError("Candidate Feature View candidates must be unique and sorted")
        if not set(self.candidate_symbols).issubset(self.universe_symbols):
            raise ValueError("Candidate Feature View exceeds Feature Bundle universe")
        source_pairs = tuple(
            (str(item_id), item_hash)
            for item_id, item_hash in self.source_manifest_references
        )
        if not source_pairs or source_pairs != tuple(sorted(set(source_pairs))):
            raise ValueError("Candidate Feature View source manifests must be sorted")
        for _, item_hash in self.source_manifest_references:
            require_sha256("source_manifest_hash", item_hash)
        keys = tuple(
            (item.symbol, item.feature_id, item.timeframe.value)
            for item in self.feature_artifact_references
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Candidate Feature View Feature references must be unique and sorted")
        if any(
            reference.symbol not in self.candidate_symbols
            for reference in self.feature_artifact_references
        ):
            raise ValueError("Candidate Feature View contains an unselected symbol")

    @classmethod
    def create(
        cls,
        *,
        candidate_set: CandidateSet,
        feature_bundle: VerifiedFeatureBundleV2,
        verified_dataset: VerifiedMarketDataDataset,
        minimum_data_eligibility: DataEligibility,
    ) -> CandidateFeatureView:
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        bundle = feature_bundle.artifact
        dataset = verified_dataset.artifact
        bundle.verify_identity()
        bundle.verify_materialized_projection(
            tuple(item.artifact for item in feature_bundle.artifacts)
        )
        dataset.verify_identity()
        if candidate_set.envelope.decision_time.value != bundle.decision_time:
            raise ValueError("CandidateSet and Feature Bundle DecisionTime mismatch")
        if (
            bundle.dataset_id != dataset.dataset_id
            or bundle.dataset_hash != dataset.content_hash
            or bundle.source_manifest_references != dataset.source_manifest_references
        ):
            raise ValueError("Feature Bundle and Market Data Dataset lineage mismatch")
        candidate_source = (
            candidate_set.envelope.source_manifest_id,
            candidate_set.envelope.source_manifest_hash,
        )
        if candidate_source not in bundle.source_manifest_references:
            raise ValueError("CandidateSet and Feature Bundle SourceManifest mismatch")
        if _ELIGIBILITY_ORDER[bundle.data_eligibility] < _ELIGIBILITY_ORDER[
            minimum_data_eligibility
        ]:
            raise ValueError("Feature Bundle data eligibility is below Signal requirement")
        candidate_symbols = tuple(sorted(item.symbol for item in candidate_set.selected))
        if len(candidate_symbols) != len(set(candidate_symbols)):
            raise ValueError("duplicate selected Candidate symbol")
        if not set(candidate_symbols).issubset(bundle.symbols):
            raise ValueError("CandidateSet references a symbol outside Feature Bundle scope")
        references = tuple(
            sorted(
                (
                    item
                    for item in bundle.feature_artifact_references
                    if item.symbol in candidate_symbols
                ),
                key=lambda item: (item.symbol, item.feature_id, item.timeframe.value),
            )
        )
        expected = {
            (symbol, definition.feature_id)
            for symbol in candidate_symbols
            for definition in bundle.feature_set.definitions
        }
        actual = {(item.symbol, item.feature_id) for item in references}
        if actual != expected or len(references) != len(expected):
            raise ValueError("Candidate Feature View Feature scope is incomplete or duplicated")
        payload = _payload(
            feature_bundle_id=bundle.bundle_id,
            feature_bundle_hash=bundle.content_hash,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            decision_time=bundle.decision_time,
            universe_symbols=bundle.symbols,
            candidate_symbols=candidate_symbols,
            source_manifest_references=bundle.source_manifest_references,
            feature_artifact_references=references,
            data_eligibility=bundle.data_eligibility,
        )
        content_hash = canonical_hash(payload)
        result = cls(
            schema_version=CANDIDATE_FEATURE_VIEW_SCHEMA,
            view_id=ArtifactId(
                f"candidate-feature-view-{content_hash.split(':', 1)[1][:24]}"
            ),
            content_hash=content_hash,
            feature_bundle_id=bundle.bundle_id,
            feature_bundle_hash=bundle.content_hash,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.content_hash,
            decision_time=bundle.decision_time,
            universe_symbols=bundle.symbols,
            candidate_symbols=candidate_symbols,
            source_manifest_references=bundle.source_manifest_references,
            feature_artifact_references=references,
            data_eligibility=bundle.data_eligibility,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            feature_bundle_id=self.feature_bundle_id,
            feature_bundle_hash=self.feature_bundle_hash,
            candidate_set_id=self.candidate_set_id,
            candidate_set_hash=self.candidate_set_hash,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            decision_time=self.decision_time,
            universe_symbols=self.universe_symbols,
            candidate_symbols=self.candidate_symbols,
            source_manifest_references=self.source_manifest_references,
            feature_artifact_references=self.feature_artifact_references,
            data_eligibility=self.data_eligibility,
        )

    def verify_identity(self) -> None:
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Candidate Feature View payload hash mismatch")
        expected_id = f"candidate-feature-view-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.view_id) != expected_id:
            raise ValueError("Candidate Feature View identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "view_id": str(self.view_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> CandidateFeatureView:
        expected = {
            "schema_version",
            "view_id",
            "content_hash",
            "feature_bundle_id",
            "feature_bundle_hash",
            "candidate_set_id",
            "candidate_set_hash",
            "dataset_id",
            "dataset_hash",
            "decision_time",
            "universe_symbols",
            "candidate_symbols",
            "source_manifest_references",
            "feature_artifact_references",
            "data_eligibility",
        }
        if set(payload) != expected:
            raise ValueError("Candidate Feature View fields mismatch")
        raw_sources = payload["source_manifest_references"]
        raw_features = payload["feature_artifact_references"]
        if not isinstance(raw_sources, list) or not isinstance(raw_features, list):
            raise ValueError("Candidate Feature View references must be arrays")
        result = cls(
            schema_version=str(payload["schema_version"]),
            view_id=ArtifactId(str(payload["view_id"])),
            content_hash=str(payload["content_hash"]),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            dataset_id=DatasetId(str(payload["dataset_id"])),
            dataset_hash=str(payload["dataset_hash"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            universe_symbols=_strings(payload["universe_symbols"], "universe_symbols"),
            candidate_symbols=_strings(payload["candidate_symbols"], "candidate_symbols"),
            source_manifest_references=tuple(
                (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
                for item in raw_sources
                if isinstance(item, dict)
                and set(item) == {"artifact_id", "content_hash"}
            ),
            feature_artifact_references=tuple(
                FeatureArtifactReferenceV2.from_canonical_dict(item)
                for item in raw_features
                if isinstance(item, dict)
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if len(result.source_manifest_references) != len(raw_sources) or len(
            result.feature_artifact_references
        ) != len(raw_features):
            raise ValueError("Candidate Feature View reference fields mismatch")
        result.verify_identity()
        return result


def _payload(
    *,
    feature_bundle_id: ArtifactId,
    feature_bundle_hash: str,
    candidate_set_id: ArtifactId,
    candidate_set_hash: str,
    dataset_id: DatasetId,
    dataset_hash: str,
    decision_time: datetime,
    universe_symbols: tuple[str, ...],
    candidate_symbols: tuple[str, ...],
    source_manifest_references: tuple[tuple[ArtifactId, str], ...],
    feature_artifact_references: tuple[FeatureArtifactReferenceV2, ...],
    data_eligibility: DataEligibility,
) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_FEATURE_VIEW_SCHEMA,
        "feature_bundle_id": str(feature_bundle_id),
        "feature_bundle_hash": feature_bundle_hash,
        "candidate_set_id": str(candidate_set_id),
        "candidate_set_hash": candidate_set_hash,
        "dataset_id": str(dataset_id),
        "dataset_hash": dataset_hash,
        "decision_time": canonical_datetime(decision_time),
        "universe_symbols": list(universe_symbols),
        "candidate_symbols": list(candidate_symbols),
        "source_manifest_references": [
            {"artifact_id": str(item_id), "content_hash": item_hash}
            for item_id, item_hash in source_manifest_references
        ],
        "feature_artifact_references": [
            item.to_canonical_dict() for item in feature_artifact_references
        ],
        "data_eligibility": data_eligibility.value,
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def publish_candidate_feature_view(
    *, root: Path, view: CandidateFeatureView
) -> Path:
    view.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(view.view_id)
    if final.exists():
        if load_candidate_feature_view(final) != view:
            raise FileExistsError(f"conflicting Candidate Feature View exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", view.to_canonical_dict())
        _write_json(
            stage / "SHA256SUMS.json",
            {"artifact.json": _file_hash(stage / "artifact.json")},
        )
        _load_candidate_feature_view(stage, enforce_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_candidate_feature_view(path: Path) -> CandidateFeatureView:
    return _load_candidate_feature_view(path, enforce_identity=True)


def _load_candidate_feature_view(
    path: Path, *, enforce_identity: bool
) -> CandidateFeatureView:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {
        "SHA256SUMS.json",
        "artifact.json",
    }:
        raise ValueError("Candidate Feature View exact file set mismatch")
    checksums = _read_object(root / "SHA256SUMS.json")
    if set(checksums) != {"artifact.json"} or _file_hash(
        root / "artifact.json"
    ) != checksums["artifact.json"]:
        raise ValueError("Candidate Feature View checksum mismatch")
    view = CandidateFeatureView.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if enforce_identity and root.name != str(view.view_id):
        raise ValueError("Candidate Feature View directory identity mismatch")
    return view


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Candidate Feature View JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Candidate Feature View JSON must be an object")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CANDIDATE_FEATURE_VIEW_SCHEMA",
    "CandidateFeatureView",
    "load_candidate_feature_view",
    "publish_candidate_feature_view",
]
