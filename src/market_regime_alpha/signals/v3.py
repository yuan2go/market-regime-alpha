"""Canonical Decimal Signal V3 Artifact, Reader, publisher, and full replay."""

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

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.candidate_view import CandidateFeatureView
from market_regime_alpha.signals.decimal_model import (
    CanonicalSignalModelV2,
    CanonicalSignalSnapshotV3,
    SignalModelConfigurationV2,
)
from market_regime_alpha.signals.input_v3 import (
    SignalInputAssemblerV3,
    SignalInputMappingConfigurationV2,
    SignalObservationV3,
)
from market_regime_alpha.signals.policies import (
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)


SIGNAL_RUN_V3_SCHEMA = "signal-run-artifact-v3"
SIGNAL_RUN_V3_PACKAGE_SCHEMA = "signal-run-package-v3"
SIGNAL_RUN_V3_FILES = ("SHA256SUMS.json", "artifact.json", "manifest.json")


@dataclass(frozen=True, slots=True)
class SignalRunArtifactV3:
    envelope: ArtifactEnvelope
    candidate_set: CandidateSet
    candidate_feature_view: CandidateFeatureView
    feature_bundle_id: ArtifactId
    feature_bundle_hash: str
    market_data_dataset_id: ArtifactId
    market_data_dataset_hash: str
    mapping_configuration: SignalInputMappingConfigurationV2
    requirement_policy: SignalFactorRequirementPolicy
    freshness_policy: SignalFactorFreshnessPolicy
    trading_calendar: TradingCalendarArtifact
    signal_configuration: SignalModelConfigurationV2
    observations: tuple[SignalObservationV3, ...]
    snapshots: tuple[CanonicalSignalSnapshotV3, ...]

    def __post_init__(self) -> None:
        if self.envelope.artifact_type != "CANONICAL_SIGNAL_RUN_V3":
            raise ValueError("Signal V3 run Envelope type mismatch")
        if self.envelope.configuration_id != self.signal_configuration.configuration_id:
            raise ValueError("Signal V3 model configuration identity mismatch")
        self.candidate_feature_view.verify_identity()
        self.mapping_configuration.verify_identity()
        self.mapping_configuration.validate_requirement_policy(self.requirement_policy)
        self.freshness_policy.verify_identity()
        self.signal_configuration.verify_identity()
        symbols = tuple(item.symbol for item in self.snapshots)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Signal V3 snapshots must be unique and sorted")
        if symbols != tuple(item.symbol for item in self.observations):
            raise ValueError("Signal V3 observations and snapshots must align")
        if symbols != self.candidate_feature_view.candidate_symbols:
            raise ValueError("Signal V3 output scope differs from Candidate Feature View")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    @property
    def configuration(self) -> SignalModelConfigurationV2:
        return self.signal_configuration

    def artifact_payload(self) -> dict[str, Any]:
        return _artifact_payload(
            candidate_set=self.candidate_set,
            candidate_feature_view=self.candidate_feature_view,
            feature_bundle_id=self.feature_bundle_id,
            feature_bundle_hash=self.feature_bundle_hash,
            market_data_dataset_id=self.market_data_dataset_id,
            market_data_dataset_hash=self.market_data_dataset_hash,
            mapping_configuration=self.mapping_configuration,
            requirement_policy=self.requirement_policy,
            freshness_policy=self.freshness_policy,
            trading_calendar=self.trading_calendar,
            signal_configuration=self.signal_configuration,
            observations=self.observations,
            snapshots=self.snapshots,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "candidate_feature_view": self.candidate_feature_view.to_canonical_dict(),
            "feature_bundle_id": str(self.feature_bundle_id),
            "feature_bundle_hash": self.feature_bundle_hash,
            "market_data_dataset_id": str(self.market_data_dataset_id),
            "market_data_dataset_hash": self.market_data_dataset_hash,
            "mapping_configuration": self.mapping_configuration.to_canonical_dict(),
            "requirement_policy": self.requirement_policy.to_canonical_dict(),
            "freshness_policy": self.freshness_policy.to_canonical_dict(),
            "trading_calendar": self.trading_calendar.to_canonical_dict(),
            "signal_configuration": self.signal_configuration.to_canonical_dict(),
            "observations": [item.to_canonical_dict() for item in self.observations],
            "snapshots": [item.to_canonical_dict() for item in self.snapshots],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalRunArtifactV3:
        expected = {
            "envelope",
            "candidate_set",
            "candidate_feature_view",
            "feature_bundle_id",
            "feature_bundle_hash",
            "market_data_dataset_id",
            "market_data_dataset_hash",
            "mapping_configuration",
            "requirement_policy",
            "freshness_policy",
            "trading_calendar",
            "signal_configuration",
            "observations",
            "snapshots",
        }
        if set(payload) != expected:
            raise ValueError("Signal Run Artifact V3 fields mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(_object(payload["envelope"], "envelope")),
            candidate_set=CandidateSet.from_canonical_dict(_object(payload["candidate_set"], "candidate_set")),
            candidate_feature_view=CandidateFeatureView.from_canonical_dict(
                _object(payload["candidate_feature_view"], "candidate_feature_view")
            ),
            feature_bundle_id=ArtifactId(str(payload["feature_bundle_id"])),
            feature_bundle_hash=str(payload["feature_bundle_hash"]),
            market_data_dataset_id=ArtifactId(str(payload["market_data_dataset_id"])),
            market_data_dataset_hash=str(payload["market_data_dataset_hash"]),
            mapping_configuration=SignalInputMappingConfigurationV2.from_canonical_dict(
                _object(payload["mapping_configuration"], "mapping_configuration")
            ),
            requirement_policy=SignalFactorRequirementPolicy.from_canonical_dict(
                _object(payload["requirement_policy"], "requirement_policy")
            ),
            freshness_policy=SignalFactorFreshnessPolicy.from_canonical_dict(
                _object(payload["freshness_policy"], "freshness_policy")
            ),
            trading_calendar=TradingCalendarArtifact.from_canonical_dict(
                _object(payload["trading_calendar"], "trading_calendar")
            ),
            signal_configuration=SignalModelConfigurationV2.from_canonical_dict(
                _object(payload["signal_configuration"], "signal_configuration")
            ),
            observations=tuple(
                SignalObservationV3.from_canonical_dict(item)
                for item in _objects(payload["observations"], "observations")
            ),
            snapshots=tuple(
                CanonicalSignalSnapshotV3.from_canonical_dict(item)
                for item in _objects(payload["snapshots"], "snapshots")
            ),
        )


@dataclass(frozen=True, slots=True)
class VerifiedSignalRunArtifactV3:
    root: Path
    artifact: SignalRunArtifactV3
    checksums_hash: str


def run_signal_model_v3(
    *,
    candidate_set: CandidateSet,
    candidate_feature_view: CandidateFeatureView,
    feature_bundle: VerifiedFeatureBundleV2,
    verified_dataset: VerifiedMarketDataDataset,
    mapping_configuration: SignalInputMappingConfigurationV2,
    requirement_policy: SignalFactorRequirementPolicy,
    freshness_policy: SignalFactorFreshnessPolicy,
    trading_calendar: TradingCalendarArtifact,
    signal_configuration: SignalModelConfigurationV2,
    observations: tuple[SignalObservationV3, ...],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> SignalRunArtifactV3:
    selected = tuple(sorted(item.symbol for item in candidate_set.selected))
    by_symbol = {item.symbol: item for item in observations}
    if len(by_symbol) != len(observations) or tuple(sorted(by_symbol)) != selected:
        raise ValueError("Signal V3 observations must exactly cover selected Candidates")
    if selected != candidate_feature_view.candidate_symbols:
        raise ValueError("Signal V3 Candidate Feature View scope mismatch")
    snapshots = tuple(
        CanonicalSignalModelV2().run(
            candidate_set=candidate_set,
            observation=by_symbol[symbol],
            configuration=signal_configuration,
            decision_time=decision_time,
            created_at=created_at,
            code_revision=code_revision,
        )
        for symbol in selected
    )
    ordered_observations = tuple(by_symbol[symbol] for symbol in selected)
    input_pairs: dict[ArtifactId, str] = {
        candidate_set.envelope.artifact_id: candidate_set.envelope.content_hash,
        candidate_feature_view.view_id: candidate_feature_view.content_hash,
        feature_bundle.artifact.bundle_id: feature_bundle.artifact.content_hash,
        ArtifactId(str(verified_dataset.artifact.dataset_id)): verified_dataset.artifact.content_hash,
        mapping_configuration.configuration_id: mapping_configuration.configuration_hash,
        requirement_policy.policy_id: requirement_policy.policy_hash,
        freshness_policy.policy_id: freshness_policy.policy_hash,
        trading_calendar.artifact_id: trading_calendar.content_hash,
    }
    for observation in ordered_observations:
        input_pairs[observation.observation_id] = observation.content_hash
        for factor in observation.factors:
            existing = input_pairs.get(factor.source_artifact_id)
            if existing is not None and existing != factor.source_content_hash:
                raise ValueError("Signal V3 Feature Artifact hash conflict")
            input_pairs[factor.source_artifact_id] = factor.source_content_hash
    for snapshot in snapshots:
        input_pairs[snapshot.artifact_id] = snapshot.envelope.content_hash
    payload = _artifact_payload(
        candidate_set=candidate_set,
        candidate_feature_view=candidate_feature_view,
        feature_bundle_id=feature_bundle.artifact.bundle_id,
        feature_bundle_hash=feature_bundle.artifact.content_hash,
        market_data_dataset_id=ArtifactId(str(verified_dataset.artifact.dataset_id)),
        market_data_dataset_hash=verified_dataset.artifact.content_hash,
        mapping_configuration=mapping_configuration,
        requirement_policy=requirement_policy,
        freshness_policy=freshness_policy,
        trading_calendar=trading_calendar,
        signal_configuration=signal_configuration,
        observations=ordered_observations,
        snapshots=snapshots,
    )
    envelope = ArtifactEnvelope.create(
        artifact_type="CANONICAL_SIGNAL_RUN_V3",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        configuration_id=signal_configuration.configuration_id,
        configuration_hash=signal_configuration.configuration_hash,
        source_manifest_id=candidate_set.envelope.source_manifest_id,
        source_manifest_hash=candidate_set.envelope.source_manifest_hash,
        input_artifact_ids=tuple(input_pairs),
        input_content_hashes=tuple(input_pairs.values()),
        model_id=signal_configuration.model_id,
        model_version=signal_configuration.model_version,
        data_eligibility=candidate_set.envelope.data_eligibility,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_ONLY",
        reason_codes=("CANONICAL_DECIMAL_SIGNAL_V3",),
        limitations=(
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_CALIBRATED_PROBABILITY",
            "NO_ENTRY_ACTION",
            "NO_TRADING_AUTHORITY",
        ),
    )
    return SignalRunArtifactV3(
        envelope=envelope,
        candidate_set=candidate_set,
        candidate_feature_view=candidate_feature_view,
        feature_bundle_id=feature_bundle.artifact.bundle_id,
        feature_bundle_hash=feature_bundle.artifact.content_hash,
        market_data_dataset_id=ArtifactId(str(verified_dataset.artifact.dataset_id)),
        market_data_dataset_hash=verified_dataset.artifact.content_hash,
        mapping_configuration=mapping_configuration,
        requirement_policy=requirement_policy,
        freshness_policy=freshness_policy,
        trading_calendar=trading_calendar,
        signal_configuration=signal_configuration,
        observations=ordered_observations,
        snapshots=snapshots,
    )


def publish_signal_run_v3(*, root: Path, artifact: SignalRunArtifactV3) -> Path:
    artifact.envelope.verify_payload(artifact.artifact_payload())
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        existing = load_verified_signal_run_v3(final)
        if existing.artifact.to_canonical_dict() != artifact.to_canonical_dict():
            raise FileExistsError(f"conflicting Signal V3 Artifact exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(stage / "manifest.json", _manifest(artifact))
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in SIGNAL_RUN_V3_FILES
                if name != "SHA256SUMS.json"
            },
        )
        _fsync_directory(stage)
        _load_verified_signal_run_v3(stage, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_signal_run_v3(path: Path) -> VerifiedSignalRunArtifactV3:
    return _load_verified_signal_run_v3(path, enforce_directory_identity=True)


def _load_verified_signal_run_v3(
    path: Path, *, enforce_directory_identity: bool
) -> VerifiedSignalRunArtifactV3:
    root = path.resolve()
    _verify_files(root)
    artifact = SignalRunArtifactV3.from_canonical_dict(
        _read_object(root / "artifact.json")
    )
    if _read_object(root / "manifest.json") != _manifest(artifact):
        raise ValueError("Signal V3 manifest is not reconstructible")
    if enforce_directory_identity and root.name != str(artifact.artifact_id):
        raise ValueError("Signal V3 directory identity mismatch")
    return VerifiedSignalRunArtifactV3(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def replay_signal_run_v3(
    path: Path,
    *,
    feature_bundle: VerifiedFeatureBundleV2,
    verified_dataset: VerifiedMarketDataDataset,
    trading_calendar: TradingCalendarArtifact,
) -> VerifiedSignalRunArtifactV3:
    original = load_verified_signal_run_v3(path).artifact
    view = CandidateFeatureView.create(
        candidate_set=original.candidate_set,
        feature_bundle=feature_bundle,
        verified_dataset=verified_dataset,
        minimum_data_eligibility=original.candidate_feature_view.data_eligibility,
    )
    if view != original.candidate_feature_view:
        raise ValueError("Signal V3 replay Candidate Feature View mismatch")
    observations = SignalInputAssemblerV3().assemble(
        candidate_set=original.candidate_set,
        candidate_feature_view=view,
        feature_bundle=feature_bundle,
        verified_dataset=verified_dataset,
        mapping_configuration=original.mapping_configuration,
        requirement_policy=original.requirement_policy,
        freshness_policy=original.freshness_policy,
        trading_calendar=trading_calendar,
        decision_time=original.envelope.decision_time,
    )
    replayed = run_signal_model_v3(
        candidate_set=original.candidate_set,
        candidate_feature_view=view,
        feature_bundle=feature_bundle,
        verified_dataset=verified_dataset,
        mapping_configuration=original.mapping_configuration,
        requirement_policy=original.requirement_policy,
        freshness_policy=original.freshness_policy,
        trading_calendar=trading_calendar,
        signal_configuration=original.signal_configuration,
        observations=observations,
        decision_time=original.envelope.decision_time,
        created_at=original.envelope.created_at,
        code_revision=original.envelope.code_revision,
    )
    if replayed.to_canonical_dict() != original.to_canonical_dict():
        raise ValueError("Signal V3 replay differs from stored Artifact")
    return load_verified_signal_run_v3(path)


def _artifact_payload(
    *,
    candidate_set: CandidateSet,
    candidate_feature_view: CandidateFeatureView,
    feature_bundle_id: ArtifactId,
    feature_bundle_hash: str,
    market_data_dataset_id: ArtifactId,
    market_data_dataset_hash: str,
    mapping_configuration: SignalInputMappingConfigurationV2,
    requirement_policy: SignalFactorRequirementPolicy,
    freshness_policy: SignalFactorFreshnessPolicy,
    trading_calendar: TradingCalendarArtifact,
    signal_configuration: SignalModelConfigurationV2,
    observations: tuple[SignalObservationV3, ...],
    snapshots: tuple[CanonicalSignalSnapshotV3, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_RUN_V3_SCHEMA,
        "candidate_set": {
            "artifact_id": str(candidate_set.envelope.artifact_id),
            "content_hash": candidate_set.envelope.content_hash,
        },
        "candidate_feature_view": candidate_feature_view.to_canonical_dict(),
        "feature_bundle": {
            "artifact_id": str(feature_bundle_id),
            "content_hash": feature_bundle_hash,
        },
        "market_data_dataset": {
            "artifact_id": str(market_data_dataset_id),
            "content_hash": market_data_dataset_hash,
        },
        "mapping_configuration": mapping_configuration.to_canonical_dict(),
        "requirement_policy": requirement_policy.to_canonical_dict(),
        "freshness_policy": freshness_policy.to_canonical_dict(),
        "trading_calendar": trading_calendar.to_canonical_dict(),
        "signal_configuration": signal_configuration.to_canonical_dict(),
        "observations": [item.to_canonical_dict() for item in observations],
        "snapshots": [item.to_canonical_dict() for item in snapshots],
    }


def _manifest(artifact: SignalRunArtifactV3) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_RUN_V3_PACKAGE_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.envelope.content_hash,
        "candidate_set_id": str(artifact.candidate_set.envelope.artifact_id),
        "candidate_feature_view_id": str(artifact.candidate_feature_view.view_id),
        "feature_bundle_id": str(artifact.feature_bundle_id),
        "market_data_dataset_id": str(artifact.market_data_dataset_id),
        "mapping_configuration_id": str(artifact.mapping_configuration.configuration_id),
        "requirement_policy_id": str(artifact.requirement_policy.policy_id),
        "freshness_policy_id": str(artifact.freshness_policy.policy_id),
        "trading_calendar_id": str(artifact.trading_calendar.artifact_id),
        "signal_configuration_id": str(artifact.signal_configuration.configuration_id),
        "model_id": str(artifact.signal_configuration.model_id),
        "model_version": artifact.signal_configuration.model_version,
        "snapshot_ids": [str(item.artifact_id) for item in artifact.snapshots],
        "required_artifacts": sorted(SIGNAL_RUN_V3_FILES),
        "formal_oos_alpha": artifact.envelope.formal_oos_alpha,
        "trading_authority": artifact.envelope.trading_authority,
    }


def _verify_files(root: Path) -> None:
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(SIGNAL_RUN_V3_FILES):
        raise ValueError("Signal V3 exact file set mismatch")
    if any(not item.is_file() for item in root.iterdir()):
        raise ValueError("Signal V3 exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    if set(checksums) != set(SIGNAL_RUN_V3_FILES) - {"SHA256SUMS.json"}:
        raise ValueError("Signal V3 checksum coverage mismatch")
    for name, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or _file_hash(root / name) != expected_hash:
            raise ValueError(f"Signal V3 checksum mismatch: {name}")


def _write_json(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Signal V3 JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Signal V3 {label} must be an object")
    return value


def _objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Signal V3 {label} must be an array of objects")
    return value


__all__ = [
    "SignalRunArtifactV3",
    "VerifiedSignalRunArtifactV3",
    "load_verified_signal_run_v3",
    "publish_signal_run_v3",
    "replay_signal_run_v3",
    "run_signal_model_v3",
]
