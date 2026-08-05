"""Candidate Feature View V2 over separate static and intraday authorities."""

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
    canonical_json,
    require_sha256,
    require_unique_text,
)
from market_regime_alpha.features.operational_overlay import (
    CandidateIntradayFeatureOverlay,
    StaticUniverseFeatureBundle,
)
from market_regime_alpha.features.v2_contracts import FeatureArtifactReferenceV2
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet


CANDIDATE_FEATURE_VIEW_V2_SCHEMA = "candidate-feature-view-v2"


@dataclass(frozen=True, slots=True)
class CandidateFeatureViewV2:
    schema_version: str
    view_id: ArtifactId
    content_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    static_bundle_id: ArtifactId
    static_bundle_hash: str
    intraday_overlay_id: ArtifactId
    intraday_overlay_hash: str
    daily_dataset_id: DatasetId
    daily_dataset_hash: str
    minute_dataset_id: DatasetId
    minute_dataset_hash: str
    decision_time: datetime
    universe_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    static_feature_references: tuple[FeatureArtifactReferenceV2, ...]
    intraday_feature_references: tuple[FeatureArtifactReferenceV2, ...]
    data_eligibility: DataEligibility
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CANDIDATE_FEATURE_VIEW_V2_SCHEMA:
            raise ValueError("unsupported Candidate Feature View V2 schema")
        for label, value in (
            ("content_hash", self.content_hash),
            ("candidate_set_hash", self.candidate_set_hash),
            ("static_bundle_hash", self.static_bundle_hash),
            ("intraday_overlay_hash", self.intraday_overlay_hash),
            ("daily_dataset_hash", self.daily_dataset_hash),
            ("minute_dataset_hash", self.minute_dataset_hash),
        ):
            require_sha256(label, value)
        require_utc_second("decision_time", self.decision_time)
        if self.universe_symbols != tuple(sorted(set(self.universe_symbols))):
            raise ValueError("Candidate Feature View V2 Universe must be sorted")
        if self.candidate_symbols != tuple(sorted(set(self.candidate_symbols))):
            raise ValueError("Candidate Feature View V2 Candidates must be sorted")
        if not self.candidate_symbols or not set(self.candidate_symbols).issubset(
            self.universe_symbols
        ):
            raise ValueError("Candidate Feature View V2 Candidate scope is invalid")
        static_keys = _reference_keys(self.static_feature_references)
        intraday_keys = _reference_keys(self.intraday_feature_references)
        if static_keys != tuple(sorted(set(static_keys))) or intraday_keys != tuple(
            sorted(set(intraday_keys))
        ):
            raise ValueError("Candidate Feature View V2 references must be unique and sorted")
        if set(static_keys) & set(intraday_keys):
            raise ValueError("Static and intraday Feature authorities overlap")
        if any(item.symbol not in self.candidate_symbols for item in (*self.static_feature_references, *self.intraday_feature_references)):
            raise ValueError("Candidate Feature View V2 contains non-Candidate Feature")
        sources = tuple((str(item), digest) for item, digest in self.source_manifest_references)
        if not sources or sources != tuple(sorted(set(sources))):
            raise ValueError("Candidate Feature View V2 sources must be sorted")
        for _, digest in self.source_manifest_references:
            require_sha256("source manifest hash", digest)
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Candidate Feature View V2 limitations must be sorted")
        if "REFERENCE_ONLY_NO_SECOND_FEATURE_AUTHORITY" not in self.limitations:
            raise ValueError("Candidate Feature View V2 authority ceiling is missing")

    @property
    def feature_artifact_references(self) -> tuple[FeatureArtifactReferenceV2, ...]:
        return tuple(
            sorted(
                (*self.static_feature_references, *self.intraday_feature_references),
                key=lambda item: (item.symbol, item.feature_id, item.timeframe.value),
            )
        )

    @classmethod
    def create(
        cls,
        *,
        candidate_set: CandidateSet,
        static_bundle: StaticUniverseFeatureBundle,
        intraday_overlay: CandidateIntradayFeatureOverlay,
    ) -> CandidateFeatureViewV2:
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        static_bundle.verify_identity()
        intraday_overlay.verify_identity()
        candidates = tuple(sorted(item.symbol for item in candidate_set.selected))
        if (
            intraday_overlay.candidate_set_id != candidate_set.envelope.artifact_id
            or intraday_overlay.candidate_set_hash != candidate_set.envelope.content_hash
        ):
            raise ValueError("Candidate Feature View V2 CandidateSet mismatch")
        if (
            intraday_overlay.static_bundle_id != static_bundle.artifact_id
            or intraday_overlay.static_bundle_hash != static_bundle.content_hash
        ):
            raise ValueError("Candidate Feature View V2 Static Bundle mismatch")
        if intraday_overlay.candidate_symbols != candidates:
            raise ValueError("Candidate Feature View V2 Candidate scope mismatch")
        static_refs = tuple(
            item
            for item in static_bundle.feature_artifact_references
            if item.symbol in candidates
        )
        expected_static = {
            (symbol, feature_id)
            for symbol in candidates
            for feature_id in {
                item.feature_id for item in static_bundle.feature_artifact_references
            }
        }
        if {(item.symbol, item.feature_id) for item in static_refs} != expected_static:
            raise ValueError("Candidate Feature View V2 static projection is incomplete")
        sources = tuple(
            sorted(
                set(static_bundle.source_manifest_references)
                | set(intraday_overlay.source_manifest_references),
                key=lambda item: (str(item[0]), item[1]),
            )
        )
        limitations = tuple(
            sorted(
                {
                    *static_bundle.limitations,
                    *intraday_overlay.limitations,
                    "REFERENCE_ONLY_NO_SECOND_FEATURE_AUTHORITY",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        values: dict[str, Any] = {
            "candidate_set_id": candidate_set.envelope.artifact_id,
            "candidate_set_hash": candidate_set.envelope.content_hash,
            "static_bundle_id": static_bundle.artifact_id,
            "static_bundle_hash": static_bundle.content_hash,
            "intraday_overlay_id": intraday_overlay.artifact_id,
            "intraday_overlay_hash": intraday_overlay.content_hash,
            "daily_dataset_id": static_bundle.daily_dataset_id,
            "daily_dataset_hash": static_bundle.daily_dataset_hash,
            "minute_dataset_id": intraday_overlay.minute_dataset_id,
            "minute_dataset_hash": intraday_overlay.minute_dataset_hash,
            "decision_time": intraday_overlay.decision_time,
            "universe_symbols": static_bundle.symbols,
            "candidate_symbols": candidates,
            "source_manifest_references": sources,
            "static_feature_references": static_refs,
            "intraday_feature_references": intraday_overlay.feature_artifact_references,
            "data_eligibility": min(
                static_bundle.data_eligibility,
                intraday_overlay.data_eligibility,
                key=_eligibility_rank,
            ),
            "limitations": limitations,
        }
        semantic = _payload(**values)
        digest = canonical_hash(semantic)
        result = cls(
            schema_version=CANDIDATE_FEATURE_VIEW_V2_SCHEMA,
            view_id=ArtifactId(f"candidate-feature-view-v2-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            static_bundle_id=static_bundle.artifact_id,
            static_bundle_hash=static_bundle.content_hash,
            intraday_overlay_id=intraday_overlay.artifact_id,
            intraday_overlay_hash=intraday_overlay.content_hash,
            daily_dataset_id=static_bundle.daily_dataset_id,
            daily_dataset_hash=static_bundle.daily_dataset_hash,
            minute_dataset_id=intraday_overlay.minute_dataset_id,
            minute_dataset_hash=intraday_overlay.minute_dataset_hash,
            decision_time=intraday_overlay.decision_time,
            universe_symbols=static_bundle.symbols,
            candidate_symbols=candidates,
            source_manifest_references=sources,
            static_feature_references=static_refs,
            intraday_feature_references=intraday_overlay.feature_artifact_references,
            data_eligibility=min(
                static_bundle.data_eligibility,
                intraday_overlay.data_eligibility,
                key=_eligibility_rank,
            ),
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            candidate_set_id=self.candidate_set_id,
            candidate_set_hash=self.candidate_set_hash,
            static_bundle_id=self.static_bundle_id,
            static_bundle_hash=self.static_bundle_hash,
            intraday_overlay_id=self.intraday_overlay_id,
            intraday_overlay_hash=self.intraday_overlay_hash,
            daily_dataset_id=self.daily_dataset_id,
            daily_dataset_hash=self.daily_dataset_hash,
            minute_dataset_id=self.minute_dataset_id,
            minute_dataset_hash=self.minute_dataset_hash,
            decision_time=self.decision_time,
            universe_symbols=self.universe_symbols,
            candidate_symbols=self.candidate_symbols,
            source_manifest_references=self.source_manifest_references,
            static_feature_references=self.static_feature_references,
            intraday_feature_references=self.intraday_feature_references,
            data_eligibility=self.data_eligibility,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if self.content_hash != digest:
            raise ValueError("Candidate Feature View V2 hash mismatch")
        if str(self.view_id) != f"candidate-feature-view-v2-{digest.split(':', 1)[1][:24]}":
            raise ValueError("Candidate Feature View V2 identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"view_id": str(self.view_id), "content_hash": self.content_hash, **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> CandidateFeatureViewV2:
        expected = {
            "schema_version", "view_id", "content_hash", "candidate_set_id",
            "candidate_set_hash", "static_bundle_id", "static_bundle_hash",
            "intraday_overlay_id", "intraday_overlay_hash", "daily_dataset_id",
            "daily_dataset_hash", "minute_dataset_id", "minute_dataset_hash",
            "decision_time", "universe_symbols", "candidate_symbols",
            "source_manifest_references", "static_feature_references",
            "intraday_feature_references", "data_eligibility", "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Candidate Feature View V2 fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            view_id=ArtifactId(str(payload["view_id"])),
            content_hash=str(payload["content_hash"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            static_bundle_id=ArtifactId(str(payload["static_bundle_id"])),
            static_bundle_hash=str(payload["static_bundle_hash"]),
            intraday_overlay_id=ArtifactId(str(payload["intraday_overlay_id"])),
            intraday_overlay_hash=str(payload["intraday_overlay_hash"]),
            daily_dataset_id=DatasetId(str(payload["daily_dataset_id"])),
            daily_dataset_hash=str(payload["daily_dataset_hash"]),
            minute_dataset_id=DatasetId(str(payload["minute_dataset_id"])),
            minute_dataset_hash=str(payload["minute_dataset_hash"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            universe_symbols=_strings(payload["universe_symbols"], "universe symbols"),
            candidate_symbols=_strings(payload["candidate_symbols"], "candidate symbols"),
            source_manifest_references=_source_refs(payload["source_manifest_references"]),
            static_feature_references=_feature_refs(payload["static_feature_references"]),
            intraday_feature_references=_feature_refs(payload["intraday_feature_references"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def publish_candidate_feature_view_v2(*, root: Path, view: CandidateFeatureViewV2) -> Path:
    view.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(view.view_id)
    if final.exists():
        if load_candidate_feature_view_v2(final) != view:
            raise FileExistsError("conflicting Candidate Feature View V2 exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        encoded = (canonical_json(view.to_canonical_dict()) + "\n").encode()
        (stage / "artifact.json").write_bytes(encoded)
        checksums = {"artifact.json": f"sha256:{sha256(encoded).hexdigest()}"}
        (stage / "SHA256SUMS.json").write_text(canonical_json(checksums) + "\n", encoding="utf-8")
        _load(stage, enforce_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_candidate_feature_view_v2(path: Path) -> CandidateFeatureViewV2:
    return _load(path, enforce_identity=True)


def _load(path: Path, *, enforce_identity: bool) -> CandidateFeatureViewV2:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {"artifact.json", "SHA256SUMS.json"}:
        raise ValueError("Candidate Feature View V2 exact file set mismatch")
    raw = (root / "artifact.json").read_bytes()
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("Candidate Feature View V2 checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("Candidate Feature View V2 JSON is not canonical")
    view = CandidateFeatureViewV2.from_canonical_dict(payload)
    if enforce_identity and root.name != str(view.view_id):
        raise ValueError("Candidate Feature View V2 directory identity mismatch")
    return view


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_FEATURE_VIEW_V2_SCHEMA,
        "candidate_set_id": str(values["candidate_set_id"]),
        "candidate_set_hash": values["candidate_set_hash"],
        "static_bundle_id": str(values["static_bundle_id"]),
        "static_bundle_hash": values["static_bundle_hash"],
        "intraday_overlay_id": str(values["intraday_overlay_id"]),
        "intraday_overlay_hash": values["intraday_overlay_hash"],
        "daily_dataset_id": str(values["daily_dataset_id"]),
        "daily_dataset_hash": values["daily_dataset_hash"],
        "minute_dataset_id": str(values["minute_dataset_id"]),
        "minute_dataset_hash": values["minute_dataset_hash"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "universe_symbols": list(values["universe_symbols"]),
        "candidate_symbols": list(values["candidate_symbols"]),
        "source_manifest_references": [
            {"artifact_id": str(item), "content_hash": digest}
            for item, digest in values["source_manifest_references"]
        ],
        "static_feature_references": [item.to_canonical_dict() for item in values["static_feature_references"]],
        "intraday_feature_references": [item.to_canonical_dict() for item in values["intraday_feature_references"]],
        "data_eligibility": values["data_eligibility"].value,
        "limitations": list(values["limitations"]),
    }


def _reference_keys(values: tuple[FeatureArtifactReferenceV2, ...]) -> tuple[tuple[str, str, str], ...]:
    return tuple((item.symbol, item.feature_id, item.timeframe.value) for item in values)


def _eligibility_rank(value: DataEligibility) -> int:
    return {
        DataEligibility.UNQUALIFIED: 0,
        DataEligibility.EXPLORATORY: 1,
        DataEligibility.REHEARSAL: 2,
        DataEligibility.FORMAL_RESEARCH: 3,
    }[value]


def _source_refs(value: object) -> tuple[tuple[ArtifactId, str], ...]:
    return tuple(
        (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
        for item in _objects(value, "source references")
    )


def _feature_refs(value: object) -> tuple[FeatureArtifactReferenceV2, ...]:
    return tuple(FeatureArtifactReferenceV2.from_canonical_dict(item) for item in _objects(value, "Feature references"))


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be strings")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be objects")
    return tuple(value)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CANDIDATE_FEATURE_VIEW_V2_SCHEMA",
    "CandidateFeatureViewV2",
    "load_candidate_feature_view_v2",
    "publish_candidate_feature_view_v2",
]
