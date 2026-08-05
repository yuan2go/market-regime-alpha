"""Immutable composition of pre-decision static and Candidate-only intraday Features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping, TypeVar

from market_regime_alpha.core.identity import ArtifactId, DatasetId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.v2_contracts import (
    FeatureArtifactReferenceV2,
    FeatureMaterializationReceipt,
)
from market_regime_alpha.market_data import Timeframe, VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


STATIC_UNIVERSE_FEATURE_BUNDLE_SCHEMA = "static-universe-feature-bundle-v1"
CANDIDATE_INTRADAY_OVERLAY_SCHEMA = "candidate-intraday-feature-overlay-v1"


@dataclass(frozen=True, slots=True)
class StaticUniverseFeatureBundle:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    universe_id: UniverseId
    universe_hash: str
    decision_date: date
    daily_dataset_id: DatasetId
    daily_dataset_hash: str
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    feature_set_id: ArtifactId
    feature_set_hash: str
    run_receipt_id: ArtifactId
    run_receipt_hash: str
    static_decision_time: datetime
    symbols: tuple[str, ...]
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    feature_artifact_references: tuple[FeatureArtifactReferenceV2, ...]
    data_eligibility: DataEligibility
    code_revision: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != STATIC_UNIVERSE_FEATURE_BUNDLE_SCHEMA:
            raise ValueError("unsupported Static Universe Feature Bundle schema")
        for label, value in (
            ("content_hash", self.content_hash),
            ("universe_hash", self.universe_hash),
            ("daily_dataset_hash", self.daily_dataset_hash),
            ("feature_bundle_hash", self.feature_bundle_hash),
            ("feature_set_hash", self.feature_set_hash),
            ("run_receipt_hash", self.run_receipt_hash),
        ):
            require_sha256(label, value)
        require_utc_second("static_decision_time", self.static_decision_time)
        require_text("code_revision", self.code_revision)
        if self.symbols != tuple(sorted(set(self.symbols))) or not self.symbols:
            raise ValueError("Static Feature symbols must be non-empty and sorted")
        if any(item.timeframe is not Timeframe.DAILY for item in self.feature_artifact_references):
            raise ValueError("Static Feature Bundle cannot reference intraday Features")
        _validate_references(
            self.source_manifest_references,
            self.feature_artifact_references,
            self.symbols,
        )
        _limitations(self.limitations)
        if "PRE_DECISION_STATIC_FEATURES" not in self.limitations:
            raise ValueError("Static Feature authority limitation is missing")

    @classmethod
    def create(
        cls,
        *,
        universe: OperationalUniverseArtifact,
        daily_dataset: VerifiedMarketDataDataset,
        feature_bundle: VerifiedFeatureBundleV2,
        run_receipt: FeatureMaterializationReceipt,
        code_revision: str,
    ) -> StaticUniverseFeatureBundle:
        universe.verify_identity()
        bundle = feature_bundle.artifact
        dataset = daily_dataset.artifact
        bundle.verify_identity()
        if any(
            item.artifact.timeframe is not Timeframe.DAILY
            for item in feature_bundle.artifacts
        ):
            raise ValueError("Static Feature source contains intraday Feature Artifact")
        if any(item.timeframe is not Timeframe.DAILY for item in daily_dataset.bars):
            raise ValueError("Static Feature source Dataset contains intraday Bars")
        if bundle.symbols != universe.symbols:
            raise ValueError("Static Feature Bundle and Operational Universe scope mismatch")
        if (
            bundle.dataset_id != dataset.dataset_id
            or bundle.dataset_hash != dataset.content_hash
            or bundle.source_manifest_references != dataset.source_manifest_references
        ):
            raise ValueError("Static Feature Bundle and daily Dataset lineage mismatch")
        if (
            run_receipt.bundle_id != bundle.bundle_id
            or run_receipt.bundle_hash != bundle.content_hash
        ):
            raise ValueError("Static Feature run Receipt mismatch")
        if universe.available_at > bundle.decision_time:
            raise ValueError("Operational Universe was unavailable at static DecisionTime")
        limitations = tuple(
            sorted(
                {
                    *universe.limitations,
                    *bundle.limitations,
                    "IMMUTABLE_STATIC_FEATURE_AUTHORITY",
                    "PRE_DECISION_STATIC_FEATURES",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        values = {
            "universe_id": universe.universe_id,
            "universe_hash": universe.content_hash,
            "decision_date": universe.decision_date,
            "daily_dataset_id": dataset.dataset_id,
            "daily_dataset_hash": dataset.content_hash,
            "feature_bundle_id": bundle.bundle_id,
            "feature_bundle_hash": bundle.content_hash,
            "feature_set_id": bundle.feature_set.feature_set_id,
            "feature_set_hash": bundle.feature_set.content_hash,
            "run_receipt_id": run_receipt.receipt_id,
            "run_receipt_hash": run_receipt.content_hash,
            "static_decision_time": bundle.decision_time,
            "symbols": bundle.symbols,
            "source_manifest_references": bundle.source_manifest_references,
            "feature_artifact_references": tuple(
                sorted(
                    bundle.feature_artifact_references,
                    key=lambda item: (
                        item.symbol,
                        item.feature_id,
                        item.timeframe.value,
                    ),
                )
            ),
            "data_eligibility": bundle.data_eligibility,
            "code_revision": code_revision,
            "limitations": limitations,
        }
        return cls._create(**values)

    @classmethod
    def _create(cls, **values: Any) -> StaticUniverseFeatureBundle:
        semantic = _static_payload(**values)
        digest = canonical_hash(semantic)
        result = cls(
            schema_version=STATIC_UNIVERSE_FEATURE_BUNDLE_SCHEMA,
            artifact_id=ArtifactId(f"static-feature-bundle-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _static_payload(**_static_values(self))

    def verify_identity(self) -> None:
        _verify_identity(self, "static-feature-bundle")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> StaticUniverseFeatureBundle:
        expected = {"artifact_id", "content_hash", *_static_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Static Universe Feature Bundle fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            universe_id=UniverseId(str(payload["universe_id"])),
            universe_hash=str(payload["universe_hash"]),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            daily_dataset_id=DatasetId(str(payload["daily_dataset_id"])),
            daily_dataset_hash=str(payload["daily_dataset_hash"]),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            feature_set_id=ArtifactId(str(payload["feature_set_id"])),
            feature_set_hash=str(payload["feature_set_hash"]),
            run_receipt_id=ArtifactId(str(payload["run_receipt_id"])),
            run_receipt_hash=str(payload["run_receipt_hash"]),
            static_decision_time=parse_utc_second(
                "static_decision_time", payload["static_decision_time"]
            ),
            symbols=_strings(payload["symbols"], "symbols"),
            source_manifest_references=_source_refs(payload["source_manifest_references"]),
            feature_artifact_references=_feature_refs(payload["feature_artifact_references"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            code_revision=str(payload["code_revision"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class CandidateIntradayFeatureOverlay:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    static_bundle_id: ArtifactId
    static_bundle_hash: str
    minute_dataset_id: DatasetId
    minute_dataset_hash: str
    intraday_feature_bundle_id: ArtifactId
    intraday_feature_bundle_hash: str
    intraday_feature_set_id: ArtifactId
    intraday_feature_set_hash: str
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    decision_time: datetime
    candidate_symbols: tuple[str, ...]
    source_manifest_references: tuple[tuple[ArtifactId, str], ...]
    feature_artifact_references: tuple[FeatureArtifactReferenceV2, ...]
    data_eligibility: DataEligibility
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CANDIDATE_INTRADAY_OVERLAY_SCHEMA:
            raise ValueError("unsupported Candidate Intraday Overlay schema")
        for label, value in (
            ("content_hash", self.content_hash),
            ("candidate_set_hash", self.candidate_set_hash),
            ("static_bundle_hash", self.static_bundle_hash),
            ("minute_dataset_hash", self.minute_dataset_hash),
            ("intraday_feature_bundle_hash", self.intraday_feature_bundle_hash),
            ("intraday_feature_set_hash", self.intraday_feature_set_hash),
            ("trading_calendar_hash", self.trading_calendar_hash),
        ):
            require_sha256(label, value)
        require_utc_second("decision_time", self.decision_time)
        if self.candidate_symbols != tuple(sorted(set(self.candidate_symbols))):
            raise ValueError("Candidate overlay symbols must be unique and sorted")
        if any(item.timeframe is Timeframe.DAILY for item in self.feature_artifact_references):
            raise ValueError("Candidate overlay cannot copy static Feature references")
        _validate_references(
            self.source_manifest_references,
            self.feature_artifact_references,
            self.candidate_symbols,
        )
        _limitations(self.limitations)
        if "NO_STATIC_FEATURE_DUPLICATION" not in self.limitations:
            raise ValueError("Candidate overlay authority limitation is missing")

    @classmethod
    def create(
        cls,
        *,
        candidate_set: CandidateSet,
        static_bundle: StaticUniverseFeatureBundle,
        minute_dataset: VerifiedMarketDataDataset,
        intraday_feature_bundle: VerifiedFeatureBundleV2,
        trading_calendar: TradingCalendarArtifact,
    ) -> CandidateIntradayFeatureOverlay:
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        static_bundle.verify_identity()
        dataset = minute_dataset.artifact
        bundle = intraday_feature_bundle.artifact
        selected = tuple(sorted(item.symbol for item in candidate_set.selected))
        if not selected or not set(selected).issubset(static_bundle.symbols):
            raise ValueError("Candidate overlay scope exceeds static Universe")
        candidate_source = (
            candidate_set.envelope.source_manifest_id,
            candidate_set.envelope.source_manifest_hash,
        )
        if candidate_source not in static_bundle.source_manifest_references:
            raise ValueError("CandidateSet and static Feature SourceManifest mismatch")
        if bundle.symbols != selected:
            raise ValueError("Intraday Feature Bundle must exactly cover Candidates")
        if any(
            item.artifact.timeframe is Timeframe.DAILY
            for item in intraday_feature_bundle.artifacts
        ):
            raise ValueError("Intraday Feature Bundle contains static Feature")
        if any(item.timeframe is Timeframe.DAILY for item in minute_dataset.bars):
            raise ValueError("Candidate minute Dataset contains daily Bars")
        if bundle.dataset_id != dataset.dataset_id or bundle.dataset_hash != dataset.content_hash:
            raise ValueError("Intraday Feature Bundle and minute Dataset mismatch")
        decision_time = candidate_set.envelope.decision_time.value
        if bundle.decision_time != decision_time or dataset.decision_time != decision_time:
            raise ValueError("Candidate overlay DecisionTime mismatch")
        if static_bundle.decision_date != decision_time.date():
            raise ValueError("Static Bundle and Candidate decision date mismatch")
        if not trading_calendar.contains(decision_time.date()):
            raise ValueError("Candidate overlay Trading Calendar excludes decision date")
        sources = tuple(
            sorted(
                set(static_bundle.source_manifest_references)
                | set(dataset.source_manifest_references),
                key=lambda item: (str(item[0]), item[1]),
            )
        )
        limitations = tuple(
            sorted(
                {
                    *static_bundle.limitations,
                    *bundle.limitations,
                    "CANDIDATE_ONLY_INTRADAY_OVERLAY",
                    "NO_STATIC_FEATURE_DUPLICATION",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        values: dict[str, Any] = {
            "candidate_set_id": candidate_set.envelope.artifact_id,
            "candidate_set_hash": candidate_set.envelope.content_hash,
            "static_bundle_id": static_bundle.artifact_id,
            "static_bundle_hash": static_bundle.content_hash,
            "minute_dataset_id": dataset.dataset_id,
            "minute_dataset_hash": dataset.content_hash,
            "intraday_feature_bundle_id": bundle.bundle_id,
            "intraday_feature_bundle_hash": bundle.content_hash,
            "intraday_feature_set_id": bundle.feature_set.feature_set_id,
            "intraday_feature_set_hash": bundle.feature_set.content_hash,
            "trading_calendar_id": trading_calendar.artifact_id,
            "trading_calendar_hash": trading_calendar.content_hash,
            "decision_time": decision_time,
            "candidate_symbols": selected,
            "source_manifest_references": sources,
            "feature_artifact_references": tuple(
                sorted(
                    bundle.feature_artifact_references,
                    key=lambda item: (
                        item.symbol,
                        item.feature_id,
                        item.timeframe.value,
                    ),
                )
            ),
            "data_eligibility": bundle.data_eligibility,
            "limitations": limitations,
        }
        semantic = _overlay_payload(**values)
        digest = canonical_hash(semantic)
        result = cls(
            schema_version=CANDIDATE_INTRADAY_OVERLAY_SCHEMA,
            artifact_id=ArtifactId(f"candidate-overlay-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            static_bundle_id=static_bundle.artifact_id,
            static_bundle_hash=static_bundle.content_hash,
            minute_dataset_id=dataset.dataset_id,
            minute_dataset_hash=dataset.content_hash,
            intraday_feature_bundle_id=bundle.bundle_id,
            intraday_feature_bundle_hash=bundle.content_hash,
            intraday_feature_set_id=bundle.feature_set.feature_set_id,
            intraday_feature_set_hash=bundle.feature_set.content_hash,
            trading_calendar_id=trading_calendar.artifact_id,
            trading_calendar_hash=trading_calendar.content_hash,
            decision_time=decision_time,
            candidate_symbols=selected,
            source_manifest_references=sources,
            feature_artifact_references=values["feature_artifact_references"],
            data_eligibility=bundle.data_eligibility,
            limitations=limitations,
        )
        result.verify_identity()
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _overlay_payload(**_overlay_values(self))

    def verify_identity(self) -> None:
        _verify_identity(self, "candidate-overlay")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CandidateIntradayFeatureOverlay:
        expected = {"artifact_id", "content_hash", *_overlay_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Candidate Intraday Overlay fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            static_bundle_id=ArtifactId(str(payload["static_bundle_id"])),
            static_bundle_hash=str(payload["static_bundle_hash"]),
            minute_dataset_id=DatasetId(str(payload["minute_dataset_id"])),
            minute_dataset_hash=str(payload["minute_dataset_hash"]),
            intraday_feature_bundle_id=ArtifactId(str(payload["intraday_feature_bundle_id"])),
            intraday_feature_bundle_hash=str(payload["intraday_feature_bundle_hash"]),
            intraday_feature_set_id=ArtifactId(str(payload["intraday_feature_set_id"])),
            intraday_feature_set_hash=str(payload["intraday_feature_set_hash"]),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            candidate_symbols=_strings(payload["candidate_symbols"], "candidate symbols"),
            source_manifest_references=_source_refs(payload["source_manifest_references"]),
            feature_artifact_references=_feature_refs(payload["feature_artifact_references"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def publish_static_universe_feature_bundle(
    *, root: Path, artifact: StaticUniverseFeatureBundle
) -> Path:
    return _publish(
        root,
        artifact.artifact_id,
        artifact.to_canonical_dict(),
        load_static_universe_feature_bundle,
        StaticUniverseFeatureBundle.from_canonical_dict,
    )


def load_static_universe_feature_bundle(path: Path) -> StaticUniverseFeatureBundle:
    return _load(path, StaticUniverseFeatureBundle.from_canonical_dict)


def publish_candidate_intraday_feature_overlay(
    *, root: Path, artifact: CandidateIntradayFeatureOverlay
) -> Path:
    return _publish(
        root,
        artifact.artifact_id,
        artifact.to_canonical_dict(),
        load_candidate_intraday_feature_overlay,
        CandidateIntradayFeatureOverlay.from_canonical_dict,
    )


def load_candidate_intraday_feature_overlay(path: Path) -> CandidateIntradayFeatureOverlay:
    return _load(path, CandidateIntradayFeatureOverlay.from_canonical_dict)


def _static_values(item: StaticUniverseFeatureBundle) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _static_value_names()}


def _static_value_names() -> tuple[str, ...]:
    return (
        "universe_id", "universe_hash", "decision_date", "daily_dataset_id",
        "daily_dataset_hash", "feature_bundle_id", "feature_bundle_hash",
        "feature_set_id", "feature_set_hash", "run_receipt_id", "run_receipt_hash",
        "static_decision_time", "symbols", "source_manifest_references",
        "feature_artifact_references", "data_eligibility", "code_revision", "limitations",
    )


def _static_payload_keys() -> set[str]:
    return {"schema_version", *_static_value_names()}


def _static_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": STATIC_UNIVERSE_FEATURE_BUNDLE_SCHEMA,
        "universe_id": str(values["universe_id"]),
        "universe_hash": values["universe_hash"],
        "decision_date": values["decision_date"].isoformat(),
        "daily_dataset_id": str(values["daily_dataset_id"]),
        "daily_dataset_hash": values["daily_dataset_hash"],
        "feature_bundle_id": str(values["feature_bundle_id"]),
        "feature_bundle_hash": values["feature_bundle_hash"],
        "feature_set_id": str(values["feature_set_id"]),
        "feature_set_hash": values["feature_set_hash"],
        "run_receipt_id": str(values["run_receipt_id"]),
        "run_receipt_hash": values["run_receipt_hash"],
        "static_decision_time": canonical_datetime(values["static_decision_time"]),
        "symbols": list(values["symbols"]),
        "source_manifest_references": _source_refs_payload(values["source_manifest_references"]),
        "feature_artifact_references": [item.to_canonical_dict() for item in values["feature_artifact_references"]],
        "data_eligibility": values["data_eligibility"].value,
        "code_revision": values["code_revision"],
        "limitations": list(values["limitations"]),
    }


def _overlay_values(item: CandidateIntradayFeatureOverlay) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _overlay_value_names()}


def _overlay_value_names() -> tuple[str, ...]:
    return (
        "candidate_set_id", "candidate_set_hash", "static_bundle_id", "static_bundle_hash",
        "minute_dataset_id", "minute_dataset_hash", "intraday_feature_bundle_id",
        "intraday_feature_bundle_hash", "intraday_feature_set_id", "intraday_feature_set_hash",
        "trading_calendar_id", "trading_calendar_hash", "decision_time", "candidate_symbols",
        "source_manifest_references", "feature_artifact_references", "data_eligibility", "limitations",
    )


def _overlay_payload_keys() -> set[str]:
    return {"schema_version", *_overlay_value_names()}


def _overlay_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_INTRADAY_OVERLAY_SCHEMA,
        "candidate_set_id": str(values["candidate_set_id"]),
        "candidate_set_hash": values["candidate_set_hash"],
        "static_bundle_id": str(values["static_bundle_id"]),
        "static_bundle_hash": values["static_bundle_hash"],
        "minute_dataset_id": str(values["minute_dataset_id"]),
        "minute_dataset_hash": values["minute_dataset_hash"],
        "intraday_feature_bundle_id": str(values["intraday_feature_bundle_id"]),
        "intraday_feature_bundle_hash": values["intraday_feature_bundle_hash"],
        "intraday_feature_set_id": str(values["intraday_feature_set_id"]),
        "intraday_feature_set_hash": values["intraday_feature_set_hash"],
        "trading_calendar_id": str(values["trading_calendar_id"]),
        "trading_calendar_hash": values["trading_calendar_hash"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "candidate_symbols": list(values["candidate_symbols"]),
        "source_manifest_references": _source_refs_payload(values["source_manifest_references"]),
        "feature_artifact_references": [item.to_canonical_dict() for item in values["feature_artifact_references"]],
        "data_eligibility": values["data_eligibility"].value,
        "limitations": list(values["limitations"]),
    }


def _validate_references(
    source_refs: tuple[tuple[ArtifactId, str], ...],
    feature_refs: tuple[FeatureArtifactReferenceV2, ...],
    symbols: tuple[str, ...],
) -> None:
    source_keys = tuple((str(item), digest) for item, digest in source_refs)
    if not source_keys or source_keys != tuple(sorted(set(source_keys))):
        raise ValueError("source manifest references must be non-empty and sorted")
    for _, digest in source_refs:
        require_sha256("source manifest hash", digest)
    feature_keys = tuple((item.symbol, item.feature_id, item.timeframe.value) for item in feature_refs)
    if not feature_keys or feature_keys != tuple(sorted(set(feature_keys))):
        raise ValueError("Feature references must be non-empty, unique, and sorted")
    if any(item.symbol not in symbols for item in feature_refs):
        raise ValueError("Feature reference exceeds declared symbol scope")


def _limitations(values: tuple[str, ...]) -> None:
    require_unique_text("limitation", values)
    if values != tuple(sorted(values)):
        raise ValueError("limitations must be sorted")


def _verify_identity(item: Any, prefix: str) -> None:
    digest = canonical_hash(item.semantic_payload())
    if item.content_hash != digest:
        raise ValueError("operational Feature composition hash mismatch")
    if str(item.artifact_id) != f"{prefix}-{digest.split(':', 1)[1][:24]}":
        raise ValueError("operational Feature composition identity mismatch")


def _source_refs_payload(values: tuple[tuple[ArtifactId, str], ...]) -> list[dict[str, str]]:
    return [{"artifact_id": str(item), "content_hash": digest} for item, digest in values]


def _source_refs(value: object) -> tuple[tuple[ArtifactId, str], ...]:
    return tuple(
        (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
        for item in _objects(value, "source references")
    )


def _feature_refs(value: object) -> tuple[FeatureArtifactReferenceV2, ...]:
    return tuple(
        FeatureArtifactReferenceV2.from_canonical_dict(item)
        for item in _objects(value, "Feature references")
    )


T = TypeVar("T")


def _publish(
    root: Path,
    artifact_id: ArtifactId,
    payload: Mapping[str, Any],
    loader: Callable[[Path], T],
    parser: Callable[[Mapping[str, Any]], T],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact_id)
    if final.exists():
        loader(final)
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        encoded = (canonical_json(payload) + "\n").encode()
        (stage / "artifact.json").write_bytes(encoded)
        checksums = {"artifact.json": f"sha256:{sha256(encoded).hexdigest()}"}
        (stage / "SHA256SUMS.json").write_text(canonical_json(checksums) + "\n", encoding="utf-8")
        _fsync(stage)
        _load(stage, parser, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        loader(final)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def _load(
    path: Path,
    parser: Callable[[Mapping[str, Any]], T],
    *,
    enforce_directory_identity: bool = True,
) -> T:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != {"artifact.json", "SHA256SUMS.json"}:
        raise ValueError("operational Feature package exact file set mismatch")
    raw = (root / "artifact.json").read_bytes()
    checksums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if checksums != {"artifact.json": f"sha256:{sha256(raw).hexdigest()}"}:
        raise ValueError("operational Feature package checksum mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError("operational Feature package JSON is not canonical")
    result = parser(payload)
    if enforce_directory_identity and root.name != str(getattr(result, "artifact_id")):
        raise ValueError("operational Feature package directory identity mismatch")
    return result


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _fsync(root: Path) -> None:
    for path in root.iterdir():
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CANDIDATE_INTRADAY_OVERLAY_SCHEMA",
    "STATIC_UNIVERSE_FEATURE_BUNDLE_SCHEMA",
    "CandidateIntradayFeatureOverlay",
    "StaticUniverseFeatureBundle",
    "load_candidate_intraday_feature_overlay",
    "load_static_universe_feature_bundle",
    "publish_candidate_intraday_feature_overlay",
    "publish_static_universe_feature_bundle",
]
