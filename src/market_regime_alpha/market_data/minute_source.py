"""Immutable Tencent minute-source evidence and canonical normalization.

The mutable DuckDB cache remains a research convenience.  This module is the
canonical path: exact response bytes are archived before parsing, normalization
is Decimal-only, and cumulative counter conflicts fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    canonical_decimal,
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.market_data.dataset import (
    FormalPitStatus,
    MarketDataDatasetArtifact,
)


RAW_MINUTE_SOURCE_SCHEMA = "raw-minute-source-artifact-v1"
RAW_MINUTE_ATTEMPT_SCHEMA = "raw-minute-source-attempt-v1"
RAW_MINUTE_PACKAGE_SCHEMA = "raw-minute-source-package-v1"
RAW_MINUTE_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
    "raw-response.bin",
)
TENCENT_MINUTE_PROVIDER_ID = ProviderId("provider-tencent-public")
TENCENT_MINUTE_PROFILE_ID = "tencent-public-minute-archive-v1"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
TENCENT_MINUTE_PRODUCT = "minute-query-1m"
ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1 = "ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1"
CANONICAL_VOLUME_POLICY_V1 = "CANONICAL_VOLUME_SHARES_V1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class MinuteAttemptStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class MinuteDataConflictError(ValueError):
    """Raw minute evidence cannot safely enter canonical data."""


@dataclass(frozen=True, slots=True)
class MinuteSourceRequest:
    symbols: tuple[str, ...]
    timeframe: Timeframe
    decision_time: datetime

    def __post_init__(self) -> None:
        if not self.symbols or self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("symbols must be non-empty, unique, and sorted")
        if self.timeframe is not Timeframe.MINUTE_1:
            raise ValueError("Tencent source request supports one-minute data only")
        require_utc_second("decision_time", self.decision_time)

    @property
    def request_identity(self) -> str:
        return canonical_hash(
            {
                "symbols": list(self.symbols),
                "timeframe": self.timeframe.value,
                "decision_time": canonical_datetime(self.decision_time),
            }
        )


@dataclass(frozen=True, slots=True)
class MinuteSourceResponse:
    request: MinuteSourceRequest
    request_started_at: datetime
    response_received_at: datetime
    http_status: int
    content_type: str
    raw_payload: bytes
    provider_timestamp: str | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_utc_second("request_started_at", self.request_started_at)
        require_utc_second("response_received_at", self.response_received_at)
        if self.response_received_at < self.request_started_at:
            raise ValueError("response cannot precede request")
        if not isinstance(self.http_status, int) or isinstance(self.http_status, bool):
            raise TypeError("http_status must be an integer")
        require_text("content_type", self.content_type)
        if not isinstance(self.raw_payload, bytes) or not self.raw_payload:
            raise ValueError("raw_payload must be non-empty bytes")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("limitations must be unique and sorted")


class MinuteSourceClient(Protocol):
    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse: ...


@dataclass(frozen=True, slots=True)
class MinuteSourceAcquisition:
    source_artifact: RawMinuteSourceArtifact
    attempt: RawMinuteSourceAttempt
    source_path: Path
    attempt_path: Path


@dataclass(frozen=True, slots=True)
class RawMinuteSourceArtifact:
    schema_version: str
    source_artifact_id: ArtifactId
    content_hash: str
    provider_id: ProviderId
    product: str
    request_identity: str
    requested_symbols: tuple[str, ...]
    requested_timeframe: Timeframe
    decision_time: datetime
    request_started_at: datetime
    response_received_at: datetime
    raw_payload_hash: str
    raw_payload_locator: str
    http_status: int
    content_type: str
    provider_timestamp: str | None
    retrieval_limitations: tuple[str, ...]
    _raw_payload: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.schema_version != RAW_MINUTE_SOURCE_SCHEMA:
            raise ValueError("unsupported raw minute source schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("request_identity", self.request_identity)
        require_sha256("raw_payload_hash", self.raw_payload_hash)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("request_started_at", self.request_started_at)
        require_utc_second("response_received_at", self.response_received_at)
        if f"sha256:{sha256(self._raw_payload).hexdigest()}" != self.raw_payload_hash:
            raise ValueError("raw payload hash mismatch")

    @property
    def raw_payload(self) -> bytes:
        return self._raw_payload

    @property
    def reference(self) -> SourceArtifactReference:
        return SourceArtifactReference(
            artifact_id=self.source_artifact_id,
            provider_id=self.provider_id,
            retrieved_at=RetrievedAt(self.response_received_at),
            content_hash=self.raw_payload_hash,
            locator=self.raw_payload_locator,
        )

    @classmethod
    def from_response(cls, response: MinuteSourceResponse) -> RawMinuteSourceArtifact:
        if response.http_status < 200 or response.http_status >= 300:
            raise MinuteDataConflictError(f"provider HTTP status is not successful: {response.http_status}")
        _validate_tencent_response_envelope(response.raw_payload, response.request)
        lowered_content_type = response.content_type.lower()
        limitations = tuple(
            sorted(
                {
                    *response.limitations,
                    *(("PROVIDER_CONTENT_TYPE_MISMATCH_VALID_JSON",) if "json" not in lowered_content_type else ()),
                }
            )
        )
        raw_hash = f"sha256:{sha256(response.raw_payload).hexdigest()}"
        semantic = {
            "schema_version": RAW_MINUTE_SOURCE_SCHEMA,
            "provider_id": str(TENCENT_MINUTE_PROVIDER_ID),
            "product": TENCENT_MINUTE_PRODUCT,
            "request_identity": response.request.request_identity,
            "requested_symbols": list(response.request.symbols),
            "requested_timeframe": response.request.timeframe.value,
            "decision_time": canonical_datetime(response.request.decision_time),
            "request_started_at": canonical_datetime(response.request_started_at),
            "response_received_at": canonical_datetime(response.response_received_at),
            "raw_payload_hash": raw_hash,
            "raw_payload_locator": f"content-addressed://{raw_hash.split(':', 1)[1]}",
            "http_status": response.http_status,
            "content_type": response.content_type,
            "provider_timestamp": response.provider_timestamp,
            "retrieval_limitations": list(limitations),
        }
        content_hash = canonical_hash(semantic)
        return cls(
            schema_version=RAW_MINUTE_SOURCE_SCHEMA,
            source_artifact_id=ArtifactId(f"raw-minute-source-{content_hash.split(':', 1)[1][:24]}"),
            content_hash=content_hash,
            provider_id=TENCENT_MINUTE_PROVIDER_ID,
            product=TENCENT_MINUTE_PRODUCT,
            request_identity=response.request.request_identity,
            requested_symbols=response.request.symbols,
            requested_timeframe=response.request.timeframe,
            decision_time=response.request.decision_time,
            request_started_at=response.request_started_at,
            response_received_at=response.response_received_at,
            raw_payload_hash=raw_hash,
            raw_payload_locator=f"content-addressed://{raw_hash.split(':', 1)[1]}",
            http_status=response.http_status,
            content_type=response.content_type,
            provider_timestamp=response.provider_timestamp,
            retrieval_limitations=limitations,
            _raw_payload=response.raw_payload,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_id": str(self.provider_id),
            "product": self.product,
            "request_identity": self.request_identity,
            "requested_symbols": list(self.requested_symbols),
            "requested_timeframe": self.requested_timeframe.value,
            "decision_time": canonical_datetime(self.decision_time),
            "request_started_at": canonical_datetime(self.request_started_at),
            "response_received_at": canonical_datetime(self.response_received_at),
            "raw_payload_hash": self.raw_payload_hash,
            "raw_payload_locator": self.raw_payload_locator,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "provider_timestamp": self.provider_timestamp,
            "retrieval_limitations": list(self.retrieval_limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "source_artifact_id": str(self.source_artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if expected != self.content_hash:
            raise ValueError("raw minute source semantic hash mismatch")
        if str(self.source_artifact_id) != (f"raw-minute-source-{expected.split(':', 1)[1][:24]}"):
            raise ValueError("raw minute source identity mismatch")

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any], *, raw_payload: bytes) -> RawMinuteSourceArtifact:
        expected = {
            "source_artifact_id",
            "content_hash",
            "schema_version",
            "provider_id",
            "product",
            "request_identity",
            "requested_symbols",
            "requested_timeframe",
            "decision_time",
            "request_started_at",
            "response_received_at",
            "raw_payload_hash",
            "raw_payload_locator",
            "http_status",
            "content_type",
            "provider_timestamp",
            "retrieval_limitations",
        }
        if set(payload) != expected:
            raise ValueError("raw minute source fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            content_hash=str(payload["content_hash"]),
            provider_id=ProviderId(str(payload["provider_id"])),
            product=str(payload["product"]),
            request_identity=str(payload["request_identity"]),
            requested_symbols=tuple(str(item) for item in payload["requested_symbols"]),
            requested_timeframe=Timeframe(str(payload["requested_timeframe"])),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            request_started_at=parse_utc_second("request_started_at", payload["request_started_at"]),
            response_received_at=parse_utc_second("response_received_at", payload["response_received_at"]),
            raw_payload_hash=str(payload["raw_payload_hash"]),
            raw_payload_locator=str(payload["raw_payload_locator"]),
            http_status=int(payload["http_status"]),
            content_type=str(payload["content_type"]),
            provider_timestamp=(str(payload["provider_timestamp"]) if payload["provider_timestamp"] is not None else None),
            retrieval_limitations=tuple(str(item) for item in payload["retrieval_limitations"]),
            _raw_payload=raw_payload,
        )
        result.verify_identity()
        return result


@dataclass(frozen=True, slots=True)
class RawMinuteSourceAttempt:
    schema_version: str
    attempt_id: ArtifactId
    content_hash: str
    request_identity: str
    status: MinuteAttemptStatus
    request_started_at: datetime
    completed_at: datetime
    http_status: int | None
    error_code: str | None
    error_message: str | None
    source_artifact_id: ArtifactId | None
    source_content_hash: str | None

    def __post_init__(self) -> None:
        if self.schema_version != RAW_MINUTE_ATTEMPT_SCHEMA:
            raise ValueError("unsupported raw minute attempt schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256("request_identity", self.request_identity)
        require_utc_second("request_started_at", self.request_started_at)
        require_utc_second("completed_at", self.completed_at)
        if self.completed_at < self.request_started_at:
            raise ValueError("minute source attempt completion precedes start")
        if self.status is MinuteAttemptStatus.SUCCEEDED:
            if (
                self.source_artifact_id is None
                or self.source_content_hash is None
                or self.error_code is not None
                or self.error_message is not None
            ):
                raise ValueError("successful minute attempt fields are inconsistent")
            require_sha256("source_content_hash", self.source_content_hash)
        elif (
            self.source_artifact_id is not None
            or self.source_content_hash is not None
            or self.error_code is None
            or self.error_message is None
        ):
            raise ValueError("failed minute attempt fields are inconsistent")
        self.verify_identity()

    @classmethod
    def failed(
        cls,
        *,
        request: MinuteSourceRequest,
        request_started_at: datetime,
        completed_at: datetime,
        error_code: str,
        error_message: str,
        http_status: int | None = None,
    ) -> RawMinuteSourceAttempt:
        return cls._create(
            request_identity=request.request_identity,
            status=MinuteAttemptStatus.FAILED,
            request_started_at=request_started_at,
            completed_at=completed_at,
            http_status=http_status,
            error_code=error_code,
            error_message=error_message,
            source_artifact_id=None,
            source_content_hash=None,
        )

    @classmethod
    def succeeded(cls, artifact: RawMinuteSourceArtifact) -> RawMinuteSourceAttempt:
        return cls._create(
            request_identity=artifact.request_identity,
            status=MinuteAttemptStatus.SUCCEEDED,
            request_started_at=artifact.request_started_at,
            completed_at=artifact.response_received_at,
            http_status=artifact.http_status,
            error_code=None,
            error_message=None,
            source_artifact_id=artifact.source_artifact_id,
            source_content_hash=artifact.content_hash,
        )

    @classmethod
    def _create(cls, **values: Any) -> RawMinuteSourceAttempt:
        semantic = {
            "schema_version": RAW_MINUTE_ATTEMPT_SCHEMA,
            "request_identity": values["request_identity"],
            "status": values["status"].value,
            "request_started_at": canonical_datetime(values["request_started_at"]),
            "completed_at": canonical_datetime(values["completed_at"]),
            "http_status": values["http_status"],
            "error_code": values["error_code"],
            "error_message": values["error_message"],
            "source_artifact_id": (str(values["source_artifact_id"]) if values["source_artifact_id"] is not None else None),
            "source_content_hash": values["source_content_hash"],
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=RAW_MINUTE_ATTEMPT_SCHEMA,
            attempt_id=ArtifactId(f"minute-attempt-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_identity": self.request_identity,
            "status": self.status.value,
            "request_started_at": canonical_datetime(self.request_started_at),
            "completed_at": canonical_datetime(self.completed_at),
            "http_status": self.http_status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "source_artifact_id": (str(self.source_artifact_id) if self.source_artifact_id is not None else None),
            "source_content_hash": self.source_content_hash,
        }

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.content_hash != expected:
            raise ValueError("raw minute attempt hash mismatch")
        if str(self.attempt_id) != f"minute-attempt-{expected.split(':', 1)[1][:24]}":
            raise ValueError("raw minute attempt identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": str(self.attempt_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RawMinuteSourceAttempt:
        if set(payload) != {
            "attempt_id",
            "content_hash",
            "schema_version",
            "request_identity",
            "status",
            "request_started_at",
            "completed_at",
            "http_status",
            "error_code",
            "error_message",
            "source_artifact_id",
            "source_content_hash",
        }:
            raise ValueError("raw minute attempt fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            attempt_id=ArtifactId(str(payload["attempt_id"])),
            content_hash=str(payload["content_hash"]),
            request_identity=str(payload["request_identity"]),
            status=MinuteAttemptStatus(str(payload["status"])),
            request_started_at=parse_utc_second("request_started_at", payload["request_started_at"]),
            completed_at=parse_utc_second("completed_at", payload["completed_at"]),
            http_status=(int(payload["http_status"]) if payload["http_status"] is not None else None),
            error_code=(str(payload["error_code"]) if payload["error_code"] is not None else None),
            error_message=(str(payload["error_message"]) if payload["error_message"] is not None else None),
            source_artifact_id=(ArtifactId(str(payload["source_artifact_id"])) if payload["source_artifact_id"] is not None else None),
            source_content_hash=(str(payload["source_content_hash"]) if payload["source_content_hash"] is not None else None),
        )


def publish_raw_minute_attempt(root: Path, attempt: RawMinuteSourceAttempt) -> Path:
    """Atomically publish immutable acquisition-attempt evidence."""

    attempt.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"{attempt.attempt_id}.json"
    if final.exists():
        raise FileExistsError(f"raw minute attempt already exists: {final}")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{attempt.attempt_id}.",
        suffix=".tmp",
        dir=root,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(
            attempt.to_canonical_dict(),
            handle,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temporary.rename(final)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    _fsync_directory(root)
    return final


def load_raw_minute_attempt(path: Path) -> RawMinuteSourceAttempt:
    attempt = RawMinuteSourceAttempt.from_canonical_dict(_read_json(path))
    if path.name != f"{attempt.attempt_id}.json":
        raise ValueError("raw minute attempt path identity mismatch")
    return attempt


def acquire_and_archive_minute_source(
    *,
    client: MinuteSourceClient,
    request: MinuteSourceRequest,
    source_root: Path,
    attempt_root: Path,
    clock: Callable[[], datetime] = lambda: normalize_canonical_datetime(datetime.now(timezone.utc)),
) -> MinuteSourceAcquisition:
    """Fetch once, archive exact bytes, and always retain immutable attempt evidence."""

    started_at = clock()
    response: MinuteSourceResponse | None = None
    try:
        response = client.fetch(request)
        if response.request != request:
            raise MinuteDataConflictError("provider response request identity mismatch")
        artifact = RawMinuteSourceArtifact.from_response(response)
        source_path = publish_raw_minute_source(source_root, artifact)
        attempt = RawMinuteSourceAttempt.succeeded(artifact)
        attempt_path = publish_raw_minute_attempt(attempt_root, attempt)
        return MinuteSourceAcquisition(
            source_artifact=artifact,
            attempt=attempt,
            source_path=source_path,
            attempt_path=attempt_path,
        )
    except Exception as exc:
        completed_at = clock()
        failed = RawMinuteSourceAttempt.failed(
            request=request,
            request_started_at=(response.request_started_at if response is not None else started_at),
            completed_at=(max(completed_at, response.response_received_at) if response is not None else max(completed_at, started_at)),
            error_code=type(exc).__name__.upper(),
            error_message=str(exc)[:512] or type(exc).__name__,
            http_status=(response.http_status if response is not None else getattr(exc, "code", None)),
        )
        publish_raw_minute_attempt(attempt_root, failed)
        raise


def publish_raw_minute_source(
    root: Path,
    artifact: RawMinuteSourceArtifact,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.source_artifact_id)
    if final.exists():
        raise FileExistsError(f"raw minute source already exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    try:
        _write_bytes(stage / "raw-response.bin", artifact.raw_payload)
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": RAW_MINUTE_PACKAGE_SCHEMA,
                "source_artifact_id": str(artifact.source_artifact_id),
                "content_hash": artifact.content_hash,
                "raw_payload_hash": artifact.raw_payload_hash,
                "required_files": sorted(RAW_MINUTE_PACKAGE_FILES),
            },
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in ("artifact.json", "manifest.json", "raw-response.bin")},
        )
        if {item.name for item in stage.iterdir()} != set(RAW_MINUTE_PACKAGE_FILES):
            raise RuntimeError("raw minute source exact file set mismatch")
        RawMinuteSourceReader().read(stage, enforce_directory_identity=False)
        if failure_injector is not None:
            failure_injector("AFTER_STAGING_VALIDATED")
        stage.rename(final)
        _fsync_directory(root)
        if failure_injector is not None:
            failure_injector("AFTER_ATOMIC_INSTALL")
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


class RawMinuteSourceReader:
    def read(self, path: Path, *, enforce_directory_identity: bool = True) -> RawMinuteSourceArtifact:
        if not path.is_dir():
            raise ValueError("raw minute source path is not a directory")
        if {item.name for item in path.iterdir()} != set(RAW_MINUTE_PACKAGE_FILES):
            raise ValueError("raw minute source exact file set mismatch")
        checksums = _read_json(path / "SHA256SUMS.json")
        expected_files = {"artifact.json", "manifest.json", "raw-response.bin"}
        if set(checksums) != expected_files:
            raise ValueError("raw minute source checksum index mismatch")
        for name, expected in checksums.items():
            if _file_hash(path / name) != expected:
                raise ValueError(f"raw minute source checksum mismatch: {name}")
        manifest = _read_json(path / "manifest.json")
        if manifest.get("schema_version") != RAW_MINUTE_PACKAGE_SCHEMA:
            raise ValueError("unsupported raw minute package schema")
        if manifest.get("required_files") != sorted(RAW_MINUTE_PACKAGE_FILES):
            raise ValueError("raw minute required file set mismatch")
        artifact = RawMinuteSourceArtifact.from_canonical_dict(
            _read_json(path / "artifact.json"),
            raw_payload=(path / "raw-response.bin").read_bytes(),
        )
        if (
            manifest.get("source_artifact_id") != str(artifact.source_artifact_id)
            or manifest.get("content_hash") != artifact.content_hash
            or manifest.get("raw_payload_hash") != artifact.raw_payload_hash
            or (enforce_directory_identity and path.name != str(artifact.source_artifact_id))
        ):
            raise ValueError("raw minute package semantic identity mismatch")
        return artifact


class TencentMinuteSourceClient:
    """Narrow network adapter whose result must be archived before parsing."""

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
        if len(request.symbols) != 1:
            raise ValueError("Tencent minute endpoint requires one symbol per request")
        symbol = request.symbols[0]
        code = f"{symbol[-2:].lower()}{symbol[:6]}"
        url = f"{TENCENT_MINUTE_URL}?{urlencode({'code': code})}"
        started = normalize_canonical_datetime(datetime.now(timezone.utc))
        http_request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Referer": "https://gu.qq.com/",
                "User-Agent": "Market-Regime-Alpha/Canonical-Minute-Archive-V1",
            },
        )
        with urlopen(http_request, timeout=self._timeout_seconds) as response:  # noqa: S310
            raw = response.read()
            received = normalize_canonical_datetime(datetime.now(timezone.utc))
            content_type = response.headers.get_content_type()
            http_status = int(response.status)
        return MinuteSourceResponse(
            request=request,
            request_started_at=started,
            response_received_at=received,
            http_status=http_status,
            content_type=content_type,
            raw_payload=raw,
            provider_timestamp=_provider_date_from_raw(raw),
            limitations=("PUBLIC_TENCENT_EXPLORATORY_ONLY",),
        )


@dataclass(frozen=True, slots=True)
class TencentCumulativeMinute:
    symbol: str
    market_date: date
    timestamp: datetime
    price: Decimal
    cumulative_volume_lots: Decimal
    cumulative_amount_cny: Decimal


@dataclass(frozen=True, slots=True)
class BoardLotRule:
    asset_type: AssetType
    shares_per_lot: Decimal


@dataclass(frozen=True, slots=True)
class CanonicalVolumeUnitPolicy:
    policy_id: ArtifactId
    content_hash: str
    policy_version: str
    rules: tuple[BoardLotRule, ...]

    @classmethod
    def a_share_v1(cls) -> CanonicalVolumeUnitPolicy:
        rules = (BoardLotRule(AssetType.A_SHARE, Decimal("100")),)
        semantic = {
            "policy_version": CANONICAL_VOLUME_POLICY_V1,
            "canonical_unit": VolumeUnit.SHARES.value,
            "rules": [
                {
                    "asset_type": item.asset_type.value,
                    "shares_per_lot": canonical_decimal(item.shares_per_lot),
                }
                for item in rules
            ],
        }
        digest = canonical_hash(semantic)
        return cls(
            policy_id=ArtifactId(f"volume-policy-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            policy_version=CANONICAL_VOLUME_POLICY_V1,
            rules=rules,
        )

    def to_shares(self, *, value: Decimal, unit: VolumeUnit, asset_type: AssetType) -> Decimal:
        if unit is VolumeUnit.SHARES:
            return value
        matches = [item for item in self.rules if item.asset_type is asset_type]
        if len(matches) != 1:
            raise MinuteDataConflictError(f"no board-lot authority for asset type {asset_type.value}")
        return value * matches[0].shares_per_lot


@dataclass(frozen=True, slots=True)
class MinuteNormalizationResult:
    source_manifest: SourceManifest
    one_minute_bars: tuple[CanonicalMarketBar, ...]
    five_minute_bars: tuple[CanonicalMarketBar, ...]
    resampling_policy_id: ArtifactId
    resampling_policy_hash: str
    missing_minutes: tuple[str, ...]


def parse_tencent_cumulative_minutes(
    artifact: RawMinuteSourceArtifact,
) -> tuple[TencentCumulativeMinute, ...]:
    artifact.verify_identity()
    if artifact.http_status < 200 or artifact.http_status >= 300:
        raise MinuteDataConflictError("provider HTTP status is not successful")
    try:
        payload = json.loads(artifact.raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MinuteDataConflictError("provider payload is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("code") not in {0, "0"}:
        raise MinuteDataConflictError("provider payload declares an error")
    if len(artifact.requested_symbols) != 1:
        raise MinuteDataConflictError("Tencent payload must bind exactly one symbol")
    symbol = artifact.requested_symbols[0]
    code = f"{symbol[-2:].lower()}{symbol[:6]}"
    stock = _mapping(_mapping(payload.get("data"), "data").get(code), "stock")
    minute = _mapping(stock.get("data"), "minute data")
    provider_date = str(minute.get("date") or "")
    if len(provider_date) != 8 or not provider_date.isdigit():
        raise MinuteDataConflictError("provider date is missing or invalid")
    market_date = date.fromisoformat(f"{provider_date[:4]}-{provider_date[4:6]}-{provider_date[6:]}")
    if artifact.provider_timestamp is not None and artifact.provider_timestamp != provider_date:
        raise MinuteDataConflictError("provider date disagrees with archived metadata")
    raw_rows = minute.get("data")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise MinuteDataConflictError("provider returned no minute rows")
    result: list[TencentCumulativeMinute] = []
    seen: set[datetime] = set()
    previous_timestamp: datetime | None = None
    previous_volume: Decimal | None = None
    previous_amount: Decimal | None = None
    for raw_row in raw_rows:
        parts = str(raw_row).split()
        if len(parts) < 4:
            raise MinuteDataConflictError("provider minute row has insufficient fields")
        try:
            local_timestamp = datetime.strptime(f"{provider_date}{parts[0]}", "%Y%m%d%H%M").replace(tzinfo=_SHANGHAI)
            timestamp = normalize_canonical_datetime(local_timestamp)
            price = Decimal(parts[1])
            cumulative_volume = Decimal(parts[2])
            cumulative_amount = Decimal(parts[3])
        except (ValueError, InvalidOperation) as exc:
            raise MinuteDataConflictError("provider minute row is invalid") from exc
        if price <= 0 or cumulative_volume < 0 or cumulative_amount < 0:
            raise MinuteDataConflictError("provider minute row contains invalid values")
        if timestamp in seen:
            raise MinuteDataConflictError("duplicate provider minute")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise MinuteDataConflictError("provider minutes are not strictly ordered")
        if previous_volume is not None and cumulative_volume < previous_volume:
            raise MinuteDataConflictError("DATA_CONFLICT:CUMULATIVE_VOLUME_DECREASE")
        if previous_amount is not None and cumulative_amount < previous_amount:
            raise MinuteDataConflictError("DATA_CONFLICT:CUMULATIVE_AMOUNT_DECREASE")
        seen.add(timestamp)
        result.append(
            TencentCumulativeMinute(
                symbol=symbol,
                market_date=market_date,
                timestamp=timestamp,
                price=price,
                cumulative_volume_lots=cumulative_volume,
                cumulative_amount_cny=cumulative_amount,
            )
        )
        previous_timestamp = timestamp
        previous_volume = cumulative_volume
        previous_amount = cumulative_amount
    return tuple(result)


def normalize_tencent_minute_source(
    *,
    artifact: RawMinuteSourceArtifact,
    asset_type: AssetType,
    volume_policy: CanonicalVolumeUnitPolicy,
) -> MinuteNormalizationResult:
    cumulative = parse_tencent_cumulative_minutes(artifact)
    previous_volume = Decimal("0")
    previous_amount = Decimal("0")
    one_minute: list[CanonicalMarketBar] = []
    for item in cumulative:
        volume_lots = item.cumulative_volume_lots - previous_volume
        amount = item.cumulative_amount_cny - previous_amount
        previous_volume = item.cumulative_volume_lots
        previous_amount = item.cumulative_amount_cny
        event_start = item.timestamp
        event_end = item.timestamp + timedelta(minutes=1)
        local_time = event_start.astimezone(_SHANGHAI).time()
        in_continuous_session = time(9, 30) <= local_time < time(11, 30) or time(13) <= local_time < time(15)
        if event_end > artifact.decision_time or not in_continuous_session:
            continue
        one_minute.append(
            CanonicalMarketBar.create(
                symbol=item.symbol,
                exchange=Exchange(item.symbol[-2:]),
                asset_type=asset_type,
                timeframe=Timeframe.MINUTE_1,
                market_date=item.market_date,
                event_start=event_start,
                event_end=event_end,
                available_at=max(event_end, artifact.response_received_at),
                open=item.price,
                high=item.price,
                low=item.price,
                close=item.price,
                previous_close=None,
                volume=volume_policy.to_shares(
                    value=volume_lots,
                    unit=VolumeUnit.LOTS,
                    asset_type=asset_type,
                ),
                volume_unit=VolumeUnit.SHARES,
                amount=amount,
                turnover_rate=None,
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.UNKNOWN,
                price_limit_state=PriceLimitState.UNKNOWN,
                source_artifact_id=artifact.source_artifact_id,
                source_content_hash=artifact.raw_payload_hash,
            )
        )
    if not one_minute:
        raise MinuteDataConflictError("no completed provider minutes at DecisionTime")
    five_policy = _resampling_policy()
    five_minute, missing = resample_one_to_five_minute(
        tuple(one_minute),
        source_artifact_id=artifact.source_artifact_id,
        source_content_hash=artifact.raw_payload_hash,
    )
    manifest = _minute_source_manifest(
        artifact=artifact,
        bars=tuple(one_minute),
        missing_minutes=missing,
        volume_policy=volume_policy,
        resampling_policy=five_policy,
    )
    return MinuteNormalizationResult(
        source_manifest=manifest,
        one_minute_bars=tuple(one_minute),
        five_minute_bars=five_minute,
        resampling_policy_id=five_policy[0],
        resampling_policy_hash=five_policy[1],
        missing_minutes=missing,
    )


def resample_one_to_five_minute(
    bars: tuple[CanonicalMarketBar, ...],
    *,
    source_artifact_id: ArtifactId,
    source_content_hash: str,
) -> tuple[tuple[CanonicalMarketBar, ...], tuple[str, ...]]:
    """Resample closed-open A-share windows; incomplete windows are withheld.

    Provider stamps identify the beginning of each one-minute interval.  Windows
    are [09:30,09:35), ..., [11:25,11:30), then [13:00,13:05), ...,
    [14:55,15:00).  Auction observations outside those intervals are excluded.
    """

    if not bars:
        raise ValueError("resampling requires one-minute bars")
    for bar in bars:
        if bar.timeframe is not Timeframe.MINUTE_1:
            raise ValueError("resampling input must be one-minute bars")
        if bar.volume_unit is not VolumeUnit.SHARES:
            raise MinuteDataConflictError("resampling requires canonical SHARES")
    ordered = tuple(sorted(bars, key=lambda item: item.event_start))
    if len({(item.symbol, item.market_date) for item in ordered}) != 1:
        raise ValueError("resampling scope must be one symbol and one session")
    by_start = {item.event_start: item for item in ordered}
    if len(by_start) != len(ordered):
        raise MinuteDataConflictError("duplicate one-minute bar")
    market_date = ordered[0].market_date
    symbol = ordered[0].symbol
    windows = _five_minute_windows(market_date)
    output: list[CanonicalMarketBar] = []
    missing: list[str] = []
    for start, end in windows:
        expected = tuple(start + timedelta(minutes=index) for index in range(5))
        present = tuple(by_start[item] for item in expected if item in by_start)
        if not present:
            continue
        absent = tuple(item for item in expected if item not in by_start)
        if absent:
            missing.extend(canonical_datetime(item) for item in absent)
            continue
        output.append(
            CanonicalMarketBar.create(
                symbol=symbol,
                exchange=ordered[0].exchange,
                asset_type=ordered[0].asset_type,
                timeframe=Timeframe.MINUTE_5,
                market_date=market_date,
                event_start=start,
                event_end=end,
                available_at=max(item.available_at for item in present),
                open=present[0].open,
                high=max(item.high for item in present),
                low=min(item.low for item in present),
                close=present[-1].close,
                previous_close=None,
                volume=sum((item.volume for item in present), Decimal("0")),
                volume_unit=VolumeUnit.SHARES,
                amount=sum((item.amount or Decimal("0") for item in present), Decimal("0")),
                turnover_rate=None,
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.UNKNOWN,
                price_limit_state=PriceLimitState.UNKNOWN,
                source_artifact_id=source_artifact_id,
                source_content_hash=source_content_hash,
            )
        )
    return tuple(output), tuple(sorted(set(missing)))


def build_combined_market_data_dataset(
    *,
    daily: MarketDataDatasetArtifact,
    minute: MarketDataDatasetArtifact,
    created_at: datetime,
) -> MarketDataDatasetArtifact:
    """Combine verified daily/minute datasets without inflating authority."""

    daily.verify_identity()
    minute.verify_identity()
    if daily.decision_time != minute.decision_time:
        raise ValueError("daily and minute DecisionTime mismatch")
    if daily.adjustment_policy.mode is not minute.adjustment_policy.mode:
        raise ValueError("daily and minute adjustment modes differ")
    if daily.coverage.expected_symbols != minute.coverage.expected_symbols:
        raise ValueError("daily and minute symbol scopes differ")
    duplicate_keys: set[tuple[str, Timeframe, datetime]] = set()
    bars: list[CanonicalMarketBar] = []
    for bar in (*daily.iter_bars(), *minute.iter_bars()):
        key = (bar.symbol, bar.timeframe, bar.event_start)
        if key in duplicate_keys:
            raise ValueError("daily/minute source conflict: duplicate canonical bar")
        duplicate_keys.add(key)
        bars.append(bar)
    daily_by_session = {(bar.symbol, bar.market_date): bar for bar in daily.iter_bars() if bar.timeframe is Timeframe.DAILY}
    minute_by_session: dict[tuple[str, date], list[CanonicalMarketBar]] = {}
    for bar in minute.iter_bars():
        if bar.timeframe is Timeframe.MINUTE_1:
            minute_by_session.setdefault((bar.symbol, bar.market_date), []).append(bar)
    for session_key, daily_bar in daily_by_session.items():
        minute_bars = minute_by_session.get(session_key, [])
        if not minute_bars:
            continue
        ordered_minutes = sorted(minute_bars, key=lambda item: item.event_start)
        last_minute = ordered_minutes[-1]
        if last_minute.event_end == daily_bar.event_end and last_minute.close != daily_bar.close:
            raise ValueError("daily/minute provider disagreement: completed-session close conflict")
    eligibility_rank = {
        DataEligibility.UNQUALIFIED: 0,
        DataEligibility.EXPLORATORY: 1,
        DataEligibility.REHEARSAL: 2,
        DataEligibility.FORMAL_RESEARCH: 3,
    }
    eligibility = min(
        (daily.data_eligibility, minute.data_eligibility),
        key=eligibility_rank.__getitem__,
    )
    formal_status = (
        FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE
        if daily.formal_pit_status is FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE
        and minute.formal_pit_status is FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE
        else FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED
    )
    return MarketDataDatasetArtifact.create(
        decision_time=daily.decision_time,
        created_at=created_at,
        bars=tuple(bars),
        expected_symbols=daily.coverage.expected_symbols,
        expected_timeframes=tuple(
            sorted(
                set(daily.coverage.expected_timeframes) | set(minute.coverage.expected_timeframes),
                key=lambda item: item.value,
            )
        ),
        adjustment_policy=daily.adjustment_policy,
        source_manifest_references=tuple(
            sorted(
                set(daily.source_manifest_references) | set(minute.source_manifest_references),
                key=lambda item: (str(item[0]), item[1]),
            )
        ),
        data_eligibility=eligibility,
        formal_pit_status=formal_status,
        limitations=tuple(sorted(set(daily.limitations) | set(minute.limitations) | {"COMBINED_DAILY_MINUTE_DATASET_V1"})),
    )


def minute_normalization_to_dataset(
    *,
    normalized: MinuteNormalizationResult,
    artifact: RawMinuteSourceArtifact,
    created_at: datetime,
) -> MarketDataDatasetArtifact:
    bars = (*normalized.one_minute_bars, *normalized.five_minute_bars)
    return MarketDataDatasetArtifact.create(
        decision_time=artifact.decision_time,
        created_at=created_at,
        bars=bars,
        expected_symbols=artifact.requested_symbols,
        expected_timeframes=(Timeframe.MINUTE_1, Timeframe.MINUTE_5),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="tencent-minute-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (
                normalized.source_manifest.source_manifest_id,
                normalized.source_manifest.content_hash,
            ),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=tuple(
            sorted(
                {
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "PUBLIC_TENCENT_EXPLORATORY_ONLY",
                    "TENCENT_CACHE_NOT_USED_AS_SOURCE_AUTHORITY",
                    f"VOLUME_POLICY:{CANONICAL_VOLUME_POLICY_V1}",
                    f"RESAMPLING_POLICY:{ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1}",
                }
            )
        ),
    )


def _minute_source_manifest(
    *,
    artifact: RawMinuteSourceArtifact,
    bars: tuple[CanonicalMarketBar, ...],
    missing_minutes: tuple[str, ...],
    volume_policy: CanonicalVolumeUnitPolicy,
    resampling_policy: tuple[ArtifactId, str],
) -> SourceManifest:
    latest = max(item.event_end for item in bars)
    status = SourceFieldQualityStatus.DEGRADED if missing_minutes else SourceFieldQualityStatus.COMPLETE
    reasons = ("MISSING_PROVIDER_MINUTES",) if missing_minutes else ()
    fields = tuple(
        SourceManifestField(
            field_id="minute-bars",
            symbol=symbol,
            critical_fact=CriticalSourceFact.PRICE,
            provider_id=artifact.provider_id,
            source_artifact_id=artifact.source_artifact_id,
            event_time=latest,
            available_time=AvailabilityTime(artifact.response_received_at),
            retrieved_time=RetrievedAt(artifact.response_received_at),
            decision_time=DecisionTime(artifact.decision_time),
            unit="CNY|SHARES",
            adjustment_basis="RAW_UNADJUSTED",
            finality=SourceFieldFinality.PRELIMINARY,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=status,
            reason_codes=reasons,
        )
        for symbol in artifact.requested_symbols
    )
    return SourceManifest(
        provider_profile_id=TENCENT_MINUTE_PROFILE_ID,
        decision_time=DecisionTime(artifact.decision_time),
        source_artifacts=(artifact.reference,),
        fields=fields,
        source_conflicts=(),
        limitations=tuple(
            sorted(
                {
                    *artifact.retrieval_limitations,
                    "PUBLIC_TENCENT_EXPLORATORY_ONLY",
                    f"RAW_SOURCE_ARTIFACT:{artifact.source_artifact_id}",
                    f"VOLUME_POLICY:{volume_policy.content_hash}",
                    f"RESAMPLING_POLICY:{resampling_policy[1]}",
                }
            )
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _resampling_policy() -> tuple[ArtifactId, str]:
    digest = canonical_hash(
        {
            "policy_version": ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1,
            "interval": "LEFT_CLOSED_RIGHT_OPEN",
            "morning": "09:30-11:30",
            "afternoon": "13:00-15:00",
            "incomplete_window": "WITHHOLD",
            "missing_minute": "WITHHOLD_WINDOW",
            "auction": "EXCLUDE_OUTSIDE_CONTINUOUS_SESSION",
            "ohlc": "FIRST_MAX_MIN_LAST",
            "volume_amount": "SUM",
        }
    )
    return (
        ArtifactId(f"minute-resampling-{digest.split(':', 1)[1][:24]}"),
        digest,
    )


def _five_minute_windows(market_date: date) -> tuple[tuple[datetime, datetime], ...]:
    windows: list[tuple[datetime, datetime]] = []
    for start_time, end_time in ((time(9, 30), time(11, 30)), (time(13), time(15))):
        current = datetime.combine(market_date, start_time, tzinfo=_SHANGHAI)
        session_end = datetime.combine(market_date, end_time, tzinfo=_SHANGHAI)
        while current < session_end:
            start = normalize_canonical_datetime(current)
            end = normalize_canonical_datetime(current + timedelta(minutes=5))
            windows.append((start, end))
            current += timedelta(minutes=5)
    return tuple(windows)


def _validate_tencent_response_envelope(
    raw: bytes,
    request: MinuteSourceRequest,
) -> None:
    """Admit Tencent's misdeclared JSON, while rejecting HTML/error payloads."""

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MinuteDataConflictError("provider response is not valid Tencent JSON") from exc
    if not isinstance(payload, dict):
        raise MinuteDataConflictError("provider response is not a Tencent JSON object")
    if payload.get("code") != 0:
        raise MinuteDataConflictError("provider response declares an error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MinuteDataConflictError("provider response lacks Tencent data object")
    for symbol in request.symbols:
        provider_symbol = f"{symbol[-2:].lower()}{symbol[:6]}"
        symbol_payload = data.get(provider_symbol)
        if not isinstance(symbol_payload, dict):
            raise MinuteDataConflictError("provider response lacks requested symbol")
        minute_payload = symbol_payload.get("data")
        if not isinstance(minute_payload, dict):
            raise MinuteDataConflictError("provider response lacks minute data object")
        provider_date = minute_payload.get("date")
        rows = minute_payload.get("data")
        if (
            not isinstance(provider_date, str)
            or len(provider_date) != 8
            or not provider_date.isdigit()
            or not isinstance(rows, list)
            or any(not isinstance(item, str) for item in rows)
        ):
            raise MinuteDataConflictError("provider response minute envelope is invalid")


def _provider_date_from_raw(raw: bytes) -> str | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    for stock in data.values():
        if isinstance(stock, dict) and isinstance(stock.get("data"), dict):
            value = stock["data"].get("date")
            if value is not None:
                return str(value)
    return None


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MinuteDataConflictError(f"provider {label} is not an object")
    return value


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


__all__ = [
    "CANONICAL_VOLUME_POLICY_V1",
    "ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1",
    "CanonicalVolumeUnitPolicy",
    "MinuteAttemptStatus",
    "MinuteDataConflictError",
    "MinuteNormalizationResult",
    "MinuteSourceClient",
    "MinuteSourceAcquisition",
    "MinuteSourceRequest",
    "MinuteSourceResponse",
    "RawMinuteSourceArtifact",
    "RawMinuteSourceAttempt",
    "RawMinuteSourceReader",
    "TencentMinuteSourceClient",
    "acquire_and_archive_minute_source",
    "build_combined_market_data_dataset",
    "minute_normalization_to_dataset",
    "load_raw_minute_attempt",
    "normalize_tencent_minute_source",
    "parse_tencent_cumulative_minutes",
    "publish_raw_minute_source",
    "publish_raw_minute_attempt",
    "resample_one_to_five_minute",
]
