"""Immutable raw-source package for T+1 factual outcome settlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    CanonicalMarketBar,
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.market_data.dataset import MarketDataDatasetArtifact


OUTCOME_SOURCE_ARCHIVE_SCHEMA = "outcome-settlement-source-archive-v1"
OUTCOME_SOURCE_ARCHIVE_PACKAGE_SCHEMA = (
    "outcome-settlement-source-archive-package-v1"
)
RECORDED_OUTCOME_BARS_SOURCE_KIND = "RECORDED_OUTCOME_CANONICAL_BAR_INPUT_V1"
RECORDED_OUTCOME_BARS_SCHEMA = "recorded-outcome-canonical-bar-input-v1"


@dataclass(frozen=True, slots=True)
class OutcomeRawSourcePayload:
    source_artifact_id: ArtifactId
    source_kind: str
    media_type: str
    payload: bytes

    def __post_init__(self) -> None:
        require_text("source_kind", self.source_kind)
        require_text("media_type", self.media_type)
        if not self.payload:
            raise ValueError("Outcome raw source payload must not be empty")


@dataclass(frozen=True, slots=True)
class OutcomeSourceArchiveEntry:
    source_artifact_id: ArtifactId
    provider_id: ProviderId
    source_content_hash: str
    retrieved_at: datetime
    provider_locator: str
    source_kind: str
    media_type: str
    archived_locator: str
    payload_sha256: str

    def __post_init__(self) -> None:
        require_sha256("source_content_hash", self.source_content_hash)
        require_sha256("payload_sha256", self.payload_sha256)
        require_utc_second("retrieved_at", self.retrieved_at)
        for label, value in (
            ("provider_locator", self.provider_locator),
            ("source_kind", self.source_kind),
            ("media_type", self.media_type),
            ("archived_locator", self.archived_locator),
        ):
            require_text(label, value)
        locator = PurePosixPath(self.archived_locator)
        if (
            locator.is_absolute()
            or ".." in locator.parts
            or locator.as_posix() != self.archived_locator
            or not self.archived_locator.startswith("payloads/")
        ):
            raise ValueError("Outcome archived locator must be package-relative")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "source_artifact_id": str(self.source_artifact_id),
            "provider_id": str(self.provider_id),
            "source_content_hash": self.source_content_hash,
            "retrieved_at": canonical_datetime(self.retrieved_at),
            "provider_locator": self.provider_locator,
            "source_kind": self.source_kind,
            "media_type": self.media_type,
            "archived_locator": self.archived_locator,
            "payload_sha256": self.payload_sha256,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OutcomeSourceArchiveEntry:
        expected = {
            "source_artifact_id",
            "provider_id",
            "source_content_hash",
            "retrieved_at",
            "provider_locator",
            "source_kind",
            "media_type",
            "archived_locator",
            "payload_sha256",
        }
        if set(payload) != expected:
            raise ValueError("Outcome source archive entry fields mismatch")
        return cls(
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            provider_id=ProviderId(str(payload["provider_id"])),
            source_content_hash=str(payload["source_content_hash"]),
            retrieved_at=parse_utc_second("retrieved_at", payload["retrieved_at"]),
            provider_locator=str(payload["provider_locator"]),
            source_kind=str(payload["source_kind"]),
            media_type=str(payload["media_type"]),
            archived_locator=str(payload["archived_locator"]),
            payload_sha256=str(payload["payload_sha256"]),
        )


@dataclass(frozen=True, slots=True)
class OutcomeSettlementSourceArchive:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    next_session_date: date
    entries: tuple[OutcomeSourceArchiveEntry, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != OUTCOME_SOURCE_ARCHIVE_SCHEMA:
            raise ValueError("unsupported Outcome source archive schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("source_manifest_hash", self.source_manifest_hash)
        require_utc_second("created_at", self.created_at)
        keys = tuple(str(item.source_artifact_id) for item in self.entries)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("Outcome source archive entries must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Outcome source archive limitations must be sorted")
        for required in ("FACTUAL_OUTCOME_SOURCE_ONLY", "PROVIDER_NOT_QUALIFIED"):
            if required not in self.limitations:
                raise ValueError("Outcome source archive authority ceiling is incomplete")
        if any(
            item.source_content_hash != item.payload_sha256 for item in self.entries
        ):
            raise ValueError("Outcome source archive raw bytes do not match SourceManifest")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        source_manifest: SourceManifest,
        next_session_date: date,
        raw_payloads: tuple[OutcomeRawSourcePayload, ...],
        created_at: datetime,
        limitations: tuple[str, ...] = (
            "FACTUAL_OUTCOME_SOURCE_ONLY",
            "PROVIDER_NOT_QUALIFIED",
        ),
    ) -> OutcomeSettlementSourceArchive:
        payload_by_id = {item.source_artifact_id: item for item in raw_payloads}
        if len(payload_by_id) != len(raw_payloads):
            raise ValueError("Outcome raw source payload identities must be unique")
        manifest_ids = {item.artifact_id for item in source_manifest.source_artifacts}
        if set(payload_by_id) != manifest_ids:
            raise ValueError("Outcome raw source payloads must exactly match SourceManifest")
        entries = tuple(
            sorted(
                (
                    OutcomeSourceArchiveEntry(
                        source_artifact_id=reference.artifact_id,
                        provider_id=reference.provider_id,
                        source_content_hash=reference.content_hash,
                        retrieved_at=reference.retrieved_at.value,
                        provider_locator=reference.locator,
                        source_kind=payload_by_id[reference.artifact_id].source_kind,
                        media_type=payload_by_id[reference.artifact_id].media_type,
                        archived_locator=f"payloads/{reference.artifact_id}.bin",
                        payload_sha256=(
                            "sha256:"
                            + sha256(payload_by_id[reference.artifact_id].payload).hexdigest()
                        ),
                    )
                    for reference in source_manifest.source_artifacts
                ),
                key=lambda item: str(item.source_artifact_id),
            )
        )
        limitations = tuple(sorted(set(limitations)))
        digest = canonical_hash(
            _payload(
                source_manifest_id=source_manifest.source_manifest_id,
                source_manifest_hash=source_manifest.content_hash,
                next_session_date=next_session_date,
                entries=entries,
                created_at=created_at,
                limitations=limitations,
            )
        )
        return cls(
            schema_version=OUTCOME_SOURCE_ARCHIVE_SCHEMA,
            artifact_id=ArtifactId(
                f"outcome-source-archive-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            source_manifest_id=source_manifest.source_manifest_id,
            source_manifest_hash=source_manifest.content_hash,
            next_session_date=next_session_date,
            entries=entries,
            created_at=created_at,
            limitations=limitations,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            source_manifest_id=self.source_manifest_id,
            source_manifest_hash=self.source_manifest_hash,
            next_session_date=self.next_session_date,
            entries=self.entries,
            created_at=self.created_at,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Outcome source archive hash mismatch")
        expected = f"outcome-source-archive-{digest.split(':', 1)[1][:24]}"
        if str(self.artifact_id) != expected:
            raise ValueError("Outcome source archive identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OutcomeSettlementSourceArchive:
        expected = {
            "schema_version",
            "artifact_id",
            "content_hash",
            "source_manifest_id",
            "source_manifest_hash",
            "next_session_date",
            "entries",
            "created_at",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Outcome source archive fields mismatch")
        raw_entries = payload["entries"]
        if not isinstance(raw_entries, list) or any(
            not isinstance(item, Mapping) for item in raw_entries
        ):
            raise ValueError("Outcome source archive entries must be objects")
        raw_limitations = payload["limitations"]
        if not isinstance(raw_limitations, list) or any(
            not isinstance(item, str) for item in raw_limitations
        ):
            raise ValueError("Outcome source archive limitations must be strings")
        return cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            next_session_date=date.fromisoformat(str(payload["next_session_date"])),
            entries=tuple(
                OutcomeSourceArchiveEntry.from_canonical_dict(item)
                for item in raw_entries
            ),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            limitations=tuple(raw_limitations),
        )


def publish_outcome_settlement_source_archive(
    *,
    root: Path,
    artifact: OutcomeSettlementSourceArchive,
    raw_payloads: tuple[OutcomeRawSourcePayload, ...],
) -> Path:
    artifact.verify_identity()
    payload_by_id = {item.source_artifact_id: item.payload for item in raw_payloads}
    if set(payload_by_id) != {item.source_artifact_id for item in artifact.entries}:
        raise ValueError("Outcome archive publication payload scope mismatch")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(artifact.artifact_id)
    if destination.exists():
        if load_outcome_settlement_source_archive(destination) != artifact:
            raise ValueError("Outcome source archive identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact.artifact_id}.", dir=root))
    try:
        for entry in artifact.entries:
            target = staging / entry.archived_locator
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload_by_id[entry.source_artifact_id])
            with target.open("rb") as handle:
                os.fsync(handle.fileno())
        _write_json(staging / "artifact.json", artifact.to_canonical_dict())
        checksums = {
            item.relative_to(staging).as_posix(): _file_hash(item)
            for item in sorted(staging.rglob("*"))
            if item.is_file()
        }
        _write_json(staging / "SHA256SUMS.json", checksums)
        exact = tuple(
            sorted(
                (
                    "SHA256SUMS.json",
                    "artifact.json",
                    "manifest.json",
                    *(item.archived_locator for item in artifact.entries),
                )
            )
        )
        _write_json(
            staging / "manifest.json",
            {
                "schema_version": OUTCOME_SOURCE_ARCHIVE_PACKAGE_SCHEMA,
                "artifact_id": str(artifact.artifact_id),
                "content_hash": artifact.content_hash,
                "exact_file_set": list(exact),
                "checksums_sha256": _file_hash(staging / "SHA256SUMS.json"),
            },
        )
        _fsync_directory(staging / "payloads")
        _fsync_directory(staging)
        staging.rename(destination)
        _fsync_directory(root)
    except FileExistsError:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if load_outcome_settlement_source_archive(destination) != artifact:
        raise ValueError("published Outcome source archive mismatch")
    return destination


def load_outcome_settlement_source_archive(
    path: Path,
) -> OutcomeSettlementSourceArchive:
    root = path.resolve()
    manifest = _read_json(root / "manifest.json")
    expected_manifest = {
        "schema_version",
        "artifact_id",
        "content_hash",
        "exact_file_set",
        "checksums_sha256",
    }
    if set(manifest) != expected_manifest:
        raise ValueError("Outcome source archive package manifest fields mismatch")
    if manifest["schema_version"] != OUTCOME_SOURCE_ARCHIVE_PACKAGE_SCHEMA:
        raise ValueError("unsupported Outcome source archive package schema")
    actual = tuple(
        sorted(
            item.relative_to(root).as_posix()
            for item in root.rglob("*")
            if item.is_file()
        )
    )
    declared = tuple(manifest["exact_file_set"])
    if actual != declared:
        raise ValueError("Outcome source archive exact file set mismatch")
    if manifest["checksums_sha256"] != _file_hash(root / "SHA256SUMS.json"):
        raise ValueError("Outcome source archive checksum index mismatch")
    checksums = _read_json(root / "SHA256SUMS.json")
    expected_checksums = {
        item: _file_hash(root / item)
        for item in declared
        if item not in {"SHA256SUMS.json", "manifest.json"}
    }
    if checksums != expected_checksums:
        raise ValueError("Outcome source archive payload checksums mismatch")
    result = OutcomeSettlementSourceArchive.from_canonical_dict(
        _read_json(root / "artifact.json")
    )
    for entry in result.entries:
        if _file_hash(root / entry.archived_locator) != entry.payload_sha256:
            raise ValueError("Outcome source archive member hash mismatch")
    if (
        manifest["artifact_id"] != str(result.artifact_id)
        or manifest["content_hash"] != result.content_hash
    ):
        raise ValueError("Outcome source archive manifest identity mismatch")
    return result


def encode_recorded_outcome_bars(
    bars: tuple[CanonicalMarketBar, ...],
) -> bytes:
    values = []
    for bar in bars:
        payload = bar.semantic_payload()
        payload.pop("source_artifact_id")
        payload.pop("source_content_hash")
        values.append(payload)
    return (
        canonical_json(
            {
                "schema_version": RECORDED_OUTCOME_BARS_SCHEMA,
                "bars": values,
            }
        )
        + "\n"
    ).encode("utf-8")


def decode_recorded_outcome_bars(
    payload: bytes,
    *,
    source_artifact_id: ArtifactId,
    source_content_hash: str,
) -> tuple[CanonicalMarketBar, ...]:
    parsed = json.loads(payload)
    if payload != (canonical_json(parsed) + "\n").encode("utf-8"):
        raise ValueError("recorded Outcome bar payload is not canonical JSON")
    if not isinstance(parsed, Mapping) or set(parsed) != {"schema_version", "bars"}:
        raise ValueError("recorded Outcome bar payload fields mismatch")
    if parsed["schema_version"] != RECORDED_OUTCOME_BARS_SCHEMA:
        raise ValueError("unsupported recorded Outcome bar payload schema")
    raw_bars = parsed["bars"]
    if not isinstance(raw_bars, list) or any(
        not isinstance(item, Mapping) for item in raw_bars
    ):
        raise ValueError("recorded Outcome bars must be objects")
    result = []
    for raw in raw_bars:
        semantic = {
            **raw,
            "source_artifact_id": str(source_artifact_id),
            "source_content_hash": source_content_hash,
        }
        digest = canonical_hash(semantic)
        result.append(
            CanonicalMarketBar.from_canonical_dict(
                {
                    "bar_id": f"market-bar-{digest.split(':', 1)[1][:24]}",
                    "content_hash": digest,
                    **semantic,
                }
            )
        )
    return tuple(result)


def replay_outcome_dataset_from_source_archive(
    *,
    archive_path: Path,
    source_manifest: SourceManifest,
    expected_dataset: VerifiedMarketDataDataset,
) -> MarketDataDatasetArtifact:
    archive = load_outcome_settlement_source_archive(archive_path)
    if (
        archive.source_manifest_id != source_manifest.source_manifest_id
        or archive.source_manifest_hash != source_manifest.content_hash
    ):
        raise ValueError("Outcome source replay manifest lineage mismatch")
    bars: list[CanonicalMarketBar] = []
    for entry in archive.entries:
        if entry.source_kind != RECORDED_OUTCOME_BARS_SOURCE_KIND:
            raise ValueError(f"unsupported Outcome source replay kind: {entry.source_kind}")
        bars.extend(
            decode_recorded_outcome_bars(
                (archive_path / entry.archived_locator).read_bytes(),
                source_artifact_id=entry.source_artifact_id,
                source_content_hash=entry.source_content_hash,
            )
        )
    expected = expected_dataset.artifact
    return MarketDataDatasetArtifact.create(
        decision_time=expected.decision_time,
        created_at=expected.created_at,
        bars=tuple(bars),
        expected_symbols=expected.coverage.expected_symbols,
        expected_timeframes=expected.coverage.expected_timeframes,
        adjustment_policy=expected.adjustment_policy,
        source_manifest_references=expected.source_manifest_references,
        data_eligibility=expected.data_eligibility,
        formal_pit_status=expected.formal_pit_status,
        limitations=expected.limitations,
    )


def _payload(
    *,
    source_manifest_id: ArtifactId,
    source_manifest_hash: str,
    next_session_date: date,
    entries: tuple[OutcomeSourceArchiveEntry, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": OUTCOME_SOURCE_ARCHIVE_SCHEMA,
        "source_manifest_id": str(source_manifest_id),
        "source_manifest_hash": source_manifest_hash,
        "next_session_date": next_session_date.isoformat(),
        "entries": [item.to_canonical_dict() for item in entries],
        "created_at": canonical_datetime(created_at),
        "limitations": list(limitations),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Outcome source archive JSON must be an object")
    return payload


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "OutcomeRawSourcePayload",
    "OutcomeSettlementSourceArchive",
    "OutcomeSourceArchiveEntry",
    "RECORDED_OUTCOME_BARS_SOURCE_KIND",
    "decode_recorded_outcome_bars",
    "encode_recorded_outcome_bars",
    "load_outcome_settlement_source_archive",
    "publish_outcome_settlement_source_archive",
    "replay_outcome_dataset_from_source_archive",
]
