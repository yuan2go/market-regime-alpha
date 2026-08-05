"""Deadline-bounded Candidate minute acquisition over immutable source archives."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Mapping, Protocol

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    Timeframe,
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.market_data.minute_source import (
    MinuteAttemptStatus,
    MinuteSourceAcquisition,
    MinuteSourceClient,
    MinuteSourceRequest,
    RawMinuteSourceAttempt,
    TencentMinuteSourceClient,
    acquire_and_archive_minute_source,
    load_raw_minute_attempt,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet


MINUTE_BATCH_COMMAND_SCHEMA = "candidate-minute-acquisition-command-v1"
MINUTE_COVERAGE_SCHEMA = "minute-acquisition-coverage-v1"
MINUTE_COVERAGE_PACKAGE_SCHEMA = "minute-acquisition-coverage-package-v1"
MINUTE_COVERAGE_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)


class MinuteCoverageState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DEADLINE_MISSED = "DEADLINE_MISSED"


class MinuteSymbolState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    LATE = "LATE"
    DEADLINE_NOT_STARTED = "DEADLINE_NOT_STARTED"


@dataclass(frozen=True, slots=True)
class CandidateMinuteAcquisitionCommand:
    schema_version: str
    command_id: ArtifactId
    command_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    candidate_symbols: tuple[str, ...]
    decision_time: datetime
    provider_profile_id: str
    concurrency_limit: int
    per_request_timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float
    hard_cutoff: datetime

    def __post_init__(self) -> None:
        if self.schema_version != MINUTE_BATCH_COMMAND_SCHEMA:
            raise ValueError("unsupported Candidate minute command schema")
        require_sha256("command_hash", self.command_hash)
        require_sha256("candidate_set_hash", self.candidate_set_hash)
        require_utc_second("decision_time", self.decision_time)
        require_utc_second("hard_cutoff", self.hard_cutoff)
        require_text("provider_profile_id", self.provider_profile_id)
        if self.candidate_symbols != tuple(sorted(set(self.candidate_symbols))):
            raise ValueError("Candidate minute symbols must be unique and sorted")
        if self.concurrency_limit <= 0:
            raise ValueError("concurrency_limit must be positive")
        if self.per_request_timeout_seconds <= 0:
            raise ValueError("per_request_timeout_seconds must be positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if self.hard_cutoff <= self.decision_time:
            raise ValueError("hard cutoff must follow DecisionTime")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        candidate_set: CandidateSet,
        decision_time: datetime,
        provider_profile_id: str,
        concurrency_limit: int,
        per_request_timeout_seconds: float,
        max_attempts: int,
        retry_backoff_seconds: float,
        hard_cutoff: datetime,
    ) -> CandidateMinuteAcquisitionCommand:
        candidate_set.envelope.verify_payload(candidate_set.artifact_payload())
        candidate_symbols = tuple(
            sorted(item.symbol for item in candidate_set.selected)
        )
        digest = canonical_hash(
            _command_payload(
                candidate_set_id=candidate_set.envelope.artifact_id,
                candidate_set_hash=candidate_set.envelope.content_hash,
                candidate_symbols=candidate_symbols,
                decision_time=decision_time,
                provider_profile_id=provider_profile_id,
                concurrency_limit=concurrency_limit,
                per_request_timeout_seconds=float(per_request_timeout_seconds),
                max_attempts=max_attempts,
                retry_backoff_seconds=float(retry_backoff_seconds),
                hard_cutoff=hard_cutoff,
            )
        )
        return cls(
            schema_version=MINUTE_BATCH_COMMAND_SCHEMA,
            command_id=ArtifactId(f"minute-batch-command-{digest.split(':', 1)[1][:24]}"),
            command_hash=digest,
            candidate_set_id=candidate_set.envelope.artifact_id,
            candidate_set_hash=candidate_set.envelope.content_hash,
            candidate_symbols=candidate_symbols,
            decision_time=decision_time,
            provider_profile_id=provider_profile_id,
            concurrency_limit=concurrency_limit,
            per_request_timeout_seconds=float(per_request_timeout_seconds),
            max_attempts=max_attempts,
            retry_backoff_seconds=float(retry_backoff_seconds),
            hard_cutoff=hard_cutoff,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _command_payload(**_command_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.command_hash:
            raise ValueError("Candidate minute command hash mismatch")
        expected = f"minute-batch-command-{digest.split(':', 1)[1][:24]}"
        if str(self.command_id) != expected:
            raise ValueError("Candidate minute command identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "command_id": str(self.command_id),
            "command_hash": self.command_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CandidateMinuteAcquisitionCommand:
        expected = {"command_id", "command_hash", *_command_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Candidate minute command fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            command_id=ArtifactId(str(payload["command_id"])),
            command_hash=str(payload["command_hash"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            candidate_symbols=_strings(payload["candidate_symbols"], "candidate symbols"),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            provider_profile_id=str(payload["provider_profile_id"]),
            concurrency_limit=int(payload["concurrency_limit"]),
            per_request_timeout_seconds=float(payload["per_request_timeout_seconds"]),
            max_attempts=int(payload["max_attempts"]),
            retry_backoff_seconds=float(payload["retry_backoff_seconds"]),
            hard_cutoff=parse_utc_second("hard_cutoff", payload["hard_cutoff"]),
        )


@dataclass(frozen=True, slots=True)
class MinuteAttemptReference:
    symbol: str
    attempt_number: int
    attempt_id: ArtifactId
    attempt_hash: str
    status: MinuteAttemptStatus
    request_started_at: datetime
    completed_at: datetime
    http_status: int | None
    error_code: str | None
    source_artifact_id: ArtifactId | None
    source_content_hash: str | None

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be positive")
        require_sha256("attempt_hash", self.attempt_hash)
        require_utc_second("request_started_at", self.request_started_at)
        require_utc_second("completed_at", self.completed_at)
        if (self.source_artifact_id is None) != (self.source_content_hash is None):
            raise ValueError("minute attempt source reference is incomplete")
        if self.source_content_hash is not None:
            require_sha256("source_content_hash", self.source_content_hash)

    @classmethod
    def from_attempt(
        cls, *, symbol: str, attempt_number: int, attempt: RawMinuteSourceAttempt
    ) -> MinuteAttemptReference:
        return cls(
            symbol=symbol,
            attempt_number=attempt_number,
            attempt_id=attempt.attempt_id,
            attempt_hash=attempt.content_hash,
            status=attempt.status,
            request_started_at=attempt.request_started_at,
            completed_at=attempt.completed_at,
            http_status=attempt.http_status,
            error_code=attempt.error_code,
            source_artifact_id=attempt.source_artifact_id,
            source_content_hash=attempt.source_content_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "attempt_number": self.attempt_number,
            "attempt_id": str(self.attempt_id),
            "attempt_hash": self.attempt_hash,
            "status": self.status.value,
            "request_started_at": canonical_datetime(self.request_started_at),
            "completed_at": canonical_datetime(self.completed_at),
            "http_status": self.http_status,
            "error_code": self.error_code,
            "source_artifact_id": (
                str(self.source_artifact_id)
                if self.source_artifact_id is not None
                else None
            ),
            "source_content_hash": self.source_content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MinuteAttemptReference:
        expected = {
            "symbol", "attempt_number", "attempt_id", "attempt_hash", "status",
            "request_started_at", "completed_at", "http_status", "error_code",
            "source_artifact_id", "source_content_hash",
        }
        if set(payload) != expected:
            raise ValueError("minute attempt reference fields mismatch")
        return cls(
            symbol=str(payload["symbol"]),
            attempt_number=int(payload["attempt_number"]),
            attempt_id=ArtifactId(str(payload["attempt_id"])),
            attempt_hash=str(payload["attempt_hash"]),
            status=MinuteAttemptStatus(str(payload["status"])),
            request_started_at=parse_utc_second(
                "request_started_at", payload["request_started_at"]
            ),
            completed_at=parse_utc_second("completed_at", payload["completed_at"]),
            http_status=(
                int(payload["http_status"])
                if payload["http_status"] is not None
                else None
            ),
            error_code=(
                str(payload["error_code"])
                if payload["error_code"] is not None
                else None
            ),
            source_artifact_id=(
                ArtifactId(str(payload["source_artifact_id"]))
                if payload["source_artifact_id"] is not None
                else None
            ),
            source_content_hash=(
                str(payload["source_content_hash"])
                if payload["source_content_hash"] is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MinuteSymbolCoverage:
    symbol: str
    state: MinuteSymbolState
    reason_codes: tuple[str, ...]
    attempt_references: tuple[MinuteAttemptReference, ...]
    accepted_source_artifact_id: ArtifactId | None
    accepted_source_content_hash: str | None

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("minute symbol reason codes must be non-empty and sorted")
        numbers = tuple(item.attempt_number for item in self.attempt_references)
        if numbers != tuple(range(1, len(numbers) + 1)):
            raise ValueError("minute symbol attempt numbers must be contiguous")
        if any(item.symbol != self.symbol for item in self.attempt_references):
            raise ValueError("minute attempt reference symbol mismatch")
        accepted = self.accepted_source_artifact_id is not None
        if accepted != (self.accepted_source_content_hash is not None):
            raise ValueError("accepted minute source reference is incomplete")
        if accepted and self.state is not MinuteSymbolState.SUCCEEDED:
            raise ValueError("only successful minute symbols can have an accepted source")
        if self.accepted_source_content_hash is not None:
            require_sha256("accepted_source_content_hash", self.accepted_source_content_hash)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "reason_codes": list(self.reason_codes),
            "attempt_references": [
                item.to_canonical_dict() for item in self.attempt_references
            ],
            "accepted_source_artifact_id": (
                str(self.accepted_source_artifact_id)
                if self.accepted_source_artifact_id is not None
                else None
            ),
            "accepted_source_content_hash": self.accepted_source_content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MinuteSymbolCoverage:
        expected = {
            "symbol", "state", "reason_codes", "attempt_references",
            "accepted_source_artifact_id", "accepted_source_content_hash",
        }
        if set(payload) != expected:
            raise ValueError("minute symbol coverage fields mismatch")
        return cls(
            symbol=str(payload["symbol"]),
            state=MinuteSymbolState(str(payload["state"])),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
            attempt_references=tuple(
                MinuteAttemptReference.from_canonical_dict(item)
                for item in _objects(payload["attempt_references"], "attempt references")
            ),
            accepted_source_artifact_id=(
                ArtifactId(str(payload["accepted_source_artifact_id"]))
                if payload["accepted_source_artifact_id"] is not None
                else None
            ),
            accepted_source_content_hash=(
                str(payload["accepted_source_content_hash"])
                if payload["accepted_source_content_hash"] is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MinuteLatencyDistribution:
    sample_count: int
    minimum_ms: int | None
    p50_ms: int | None
    p95_ms: int | None
    maximum_ms: int | None

    @classmethod
    def from_attempts(
        cls, attempts: tuple[MinuteAttemptReference, ...]
    ) -> MinuteLatencyDistribution:
        values = sorted(
            max(0, int((item.completed_at - item.request_started_at).total_seconds() * 1000))
            for item in attempts
        )
        if not values:
            return cls(0, None, None, None, None)
        return cls(
            sample_count=len(values),
            minimum_ms=values[0],
            p50_ms=_percentile(values, 0.50),
            p95_ms=_percentile(values, 0.95),
            maximum_ms=values[-1],
        )

    def __post_init__(self) -> None:
        values = (self.minimum_ms, self.p50_ms, self.p95_ms, self.maximum_ms)
        if self.sample_count == 0:
            if any(item is not None for item in values):
                raise ValueError("empty latency distribution cannot contain values")
        elif self.sample_count < 0 or any(item is None or item < 0 for item in values):
            raise ValueError("latency distribution is invalid")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "minimum_ms": self.minimum_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "maximum_ms": self.maximum_ms,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MinuteLatencyDistribution:
        expected = {"sample_count", "minimum_ms", "p50_ms", "p95_ms", "maximum_ms"}
        if set(payload) != expected:
            raise ValueError("minute latency distribution fields mismatch")
        return cls(
            sample_count=int(payload["sample_count"]),
            minimum_ms=_optional_int(payload["minimum_ms"]),
            p50_ms=_optional_int(payload["p50_ms"]),
            p95_ms=_optional_int(payload["p95_ms"]),
            maximum_ms=_optional_int(payload["maximum_ms"]),
        )


@dataclass(frozen=True, slots=True)
class MinuteAcquisitionCoverageArtifact:
    schema_version: str
    artifact_id: ArtifactId
    content_hash: str
    command: CandidateMinuteAcquisitionCommand
    request_started_at: datetime
    request_completed_at: datetime
    coverage_state: MinuteCoverageState
    candidate_count: int
    attempted_count: int
    succeeded_count: int
    failed_count: int
    late_count: int
    symbols_succeeded: tuple[str, ...]
    symbols_failed: tuple[str, ...]
    symbol_coverage: tuple[MinuteSymbolCoverage, ...]
    provider_latency: MinuteLatencyDistribution
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != MINUTE_COVERAGE_SCHEMA:
            raise ValueError("unsupported minute coverage schema")
        require_sha256("content_hash", self.content_hash)
        require_utc_second("request_started_at", self.request_started_at)
        require_utc_second("request_completed_at", self.request_completed_at)
        if self.request_completed_at < self.request_started_at:
            raise ValueError("minute batch completion precedes start")
        symbols = tuple(item.symbol for item in self.symbol_coverage)
        if symbols != self.command.candidate_symbols:
            raise ValueError("minute coverage scope differs from command")
        succeeded = tuple(
            item.symbol
            for item in self.symbol_coverage
            if item.state is MinuteSymbolState.SUCCEEDED
        )
        failed = tuple(item.symbol for item in self.symbol_coverage if item.symbol not in succeeded)
        attempted = sum(bool(item.attempt_references) for item in self.symbol_coverage)
        late = sum(item.state is MinuteSymbolState.LATE for item in self.symbol_coverage)
        if (
            self.candidate_count != len(symbols)
            or self.attempted_count != attempted
            or self.succeeded_count != len(succeeded)
            or self.failed_count != len(failed)
            or self.late_count != late
            or self.symbols_succeeded != succeeded
            or self.symbols_failed != failed
        ):
            raise ValueError("minute coverage counts are inconsistent")
        all_attempts = tuple(
            attempt for item in self.symbol_coverage for attempt in item.attempt_references
        )
        if self.provider_latency != MinuteLatencyDistribution.from_attempts(all_attempts):
            raise ValueError("minute provider latency distribution mismatch")
        if not self.reason_codes or self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("minute coverage reason codes must be non-empty and sorted")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        command: CandidateMinuteAcquisitionCommand,
        request_started_at: datetime,
        request_completed_at: datetime,
        symbol_coverage: tuple[MinuteSymbolCoverage, ...],
    ) -> MinuteAcquisitionCoverageArtifact:
        ordered = tuple(sorted(symbol_coverage, key=lambda item: item.symbol))
        succeeded = tuple(
            item.symbol for item in ordered if item.state is MinuteSymbolState.SUCCEEDED
        )
        failed = tuple(item.symbol for item in ordered if item.symbol not in succeeded)
        late_count = sum(item.state is MinuteSymbolState.LATE for item in ordered)
        deadline_issue = any(
            item.state in {MinuteSymbolState.LATE, MinuteSymbolState.DEADLINE_NOT_STARTED}
            for item in ordered
        )
        if not failed:
            state = MinuteCoverageState.COMPLETE
        elif succeeded:
            state = MinuteCoverageState.PARTIAL
        elif deadline_issue:
            state = MinuteCoverageState.DEADLINE_MISSED
        else:
            state = MinuteCoverageState.FAILED
        attempts = tuple(
            attempt for item in ordered for attempt in item.attempt_references
        )
        reasons = {
            f"MINUTE_COVERAGE_{state.value}",
            *(reason for item in ordered for reason in item.reason_codes),
        }
        attempted_count = sum(bool(item.attempt_references) for item in ordered)
        provider_latency = MinuteLatencyDistribution.from_attempts(attempts)
        reason_codes = tuple(sorted(reasons))
        digest = canonical_hash(
            _coverage_payload(
                command=command,
                request_started_at=request_started_at,
                request_completed_at=request_completed_at,
                coverage_state=state,
                candidate_count=len(ordered),
                attempted_count=attempted_count,
                succeeded_count=len(succeeded),
                failed_count=len(failed),
                late_count=late_count,
                symbols_succeeded=succeeded,
                symbols_failed=failed,
                symbol_coverage=ordered,
                provider_latency=provider_latency,
                reason_codes=reason_codes,
            )
        )
        return cls(
            schema_version=MINUTE_COVERAGE_SCHEMA,
            artifact_id=ArtifactId(f"minute-coverage-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            command=command,
            request_started_at=request_started_at,
            request_completed_at=request_completed_at,
            coverage_state=state,
            candidate_count=len(ordered),
            attempted_count=attempted_count,
            succeeded_count=len(succeeded),
            failed_count=len(failed),
            late_count=late_count,
            symbols_succeeded=succeeded,
            symbols_failed=failed,
            symbol_coverage=ordered,
            provider_latency=provider_latency,
            reason_codes=reason_codes,
        )

    @property
    def accepted_source_references(self) -> tuple[tuple[ArtifactId, str], ...]:
        return tuple(
            (item.accepted_source_artifact_id, item.accepted_source_content_hash)
            for item in self.symbol_coverage
            if item.accepted_source_artifact_id is not None
            and item.accepted_source_content_hash is not None
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _coverage_payload(**_coverage_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("minute coverage hash mismatch")
        expected = f"minute-coverage-{digest.split(':', 1)[1][:24]}"
        if str(self.artifact_id) != expected:
            raise ValueError("minute coverage identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> MinuteAcquisitionCoverageArtifact:
        expected = {"artifact_id", "content_hash", *_coverage_payload_keys()}
        if set(payload) != expected:
            raise ValueError("minute coverage fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            command=CandidateMinuteAcquisitionCommand.from_canonical_dict(
                _object(payload["command"], "command")
            ),
            request_started_at=parse_utc_second(
                "request_started_at", payload["request_started_at"]
            ),
            request_completed_at=parse_utc_second(
                "request_completed_at", payload["request_completed_at"]
            ),
            coverage_state=MinuteCoverageState(str(payload["coverage_state"])),
            candidate_count=int(payload["candidate_count"]),
            attempted_count=int(payload["attempted_count"]),
            succeeded_count=int(payload["succeeded_count"]),
            failed_count=int(payload["failed_count"]),
            late_count=int(payload["late_count"]),
            symbols_succeeded=_strings(payload["symbols_succeeded"], "symbols succeeded"),
            symbols_failed=_strings(payload["symbols_failed"], "symbols failed"),
            symbol_coverage=tuple(
                MinuteSymbolCoverage.from_canonical_dict(item)
                for item in _objects(payload["symbol_coverage"], "symbol coverage")
            ),
            provider_latency=MinuteLatencyDistribution.from_canonical_dict(
                _object(payload["provider_latency"], "provider latency")
            ),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
        )


class MinuteClientFactory(Protocol):
    def __call__(
        self, symbol: str, attempt_number: int, timeout_seconds: float
    ) -> MinuteSourceClient: ...


class CandidateMinuteBatchAcquirer:
    """Runs one-symbol requests with bounded concurrency and finite retries."""

    def __init__(
        self,
        *,
        client_factory: MinuteClientFactory | None = None,
        clock: Callable[[], datetime],
        sleeper: Callable[[float], None] = lambda _: None,
    ) -> None:
        self._client_factory = client_factory or _tencent_client_factory
        self._clock = clock
        self._sleeper = sleeper

    def run(
        self,
        *,
        command: CandidateMinuteAcquisitionCommand,
        output_root: Path,
    ) -> MinuteAcquisitionCoverageArtifact:
        command.verify_identity()
        started_at = self._clock()
        require_utc_second("batch started_at", started_at)
        source_root = output_root / "sources"
        attempt_root = output_root / "attempts" / str(command.command_id)
        with ThreadPoolExecutor(
            max_workers=command.concurrency_limit,
            thread_name_prefix="candidate-minute",
        ) as executor:
            futures = tuple(
                executor.submit(
                    self._run_symbol,
                    command=command,
                    symbol=symbol,
                    source_root=source_root,
                    attempt_root=attempt_root,
                )
                for symbol in command.candidate_symbols
            )
            coverage = tuple(future.result() for future in futures)
        completed_at = max(started_at, self._clock())
        result = MinuteAcquisitionCoverageArtifact.create(
            command=command,
            request_started_at=started_at,
            request_completed_at=completed_at,
            symbol_coverage=coverage,
        )
        publish_minute_acquisition_coverage(root=output_root / "coverage", artifact=result)
        return result

    def _run_symbol(
        self,
        *,
        command: CandidateMinuteAcquisitionCommand,
        symbol: str,
        source_root: Path,
        attempt_root: Path,
    ) -> MinuteSymbolCoverage:
        references: list[MinuteAttemptReference] = []
        usable_deadline = min(command.decision_time, command.hard_cutoff)
        for attempt_number in range(1, command.max_attempts + 1):
            now = self._clock()
            require_utc_second("minute attempt clock", now)
            if now >= usable_deadline:
                state = (
                    MinuteSymbolState.LATE
                    if references
                    else MinuteSymbolState.DEADLINE_NOT_STARTED
                )
                return _symbol_result(
                    symbol=symbol,
                    state=state,
                    reasons=("DECISION_TIME_DEADLINE_REACHED",),
                    references=references,
                )
            remaining = (usable_deadline - now).total_seconds()
            timeout = min(command.per_request_timeout_seconds, remaining)
            request = MinuteSourceRequest(
                symbols=(symbol,),
                timeframe=Timeframe.MINUTE_1,
                decision_time=command.decision_time,
            )
            attempt_dir = attempt_root / symbol / f"attempt-{attempt_number:02d}"
            try:
                acquisition = acquire_and_archive_minute_source(
                    client=self._client_factory(symbol, attempt_number, timeout),
                    request=request,
                    source_root=source_root,
                    attempt_root=attempt_dir,
                    clock=self._clock,
                )
            except Exception:
                failed = _only_attempt(attempt_dir)
                references.append(
                    MinuteAttemptReference.from_attempt(
                        symbol=symbol,
                        attempt_number=attempt_number,
                        attempt=failed,
                    )
                )
                if (
                    attempt_number < command.max_attempts
                    and _retryable(failed)
                    and self._clock() < usable_deadline
                ):
                    delay = command.retry_backoff_seconds * (2 ** (attempt_number - 1))
                    remaining = max(0.0, (usable_deadline - self._clock()).total_seconds())
                    if delay > 0 and remaining > 0:
                        self._sleeper(min(delay, remaining))
                    continue
                error_code = failed.error_code or "UNKNOWN_PROVIDER_FAILURE"
                return _symbol_result(
                    symbol=symbol,
                    state=MinuteSymbolState.FAILED,
                    reasons=(f"PROVIDER_{error_code}",),
                    references=references,
                )
            reference = MinuteAttemptReference.from_attempt(
                symbol=symbol,
                attempt_number=attempt_number,
                attempt=acquisition.attempt,
            )
            references.append(reference)
            if (
                acquisition.source_artifact.response_received_at > command.decision_time
                or acquisition.source_artifact.response_received_at > command.hard_cutoff
            ):
                return _symbol_result(
                    symbol=symbol,
                    state=MinuteSymbolState.LATE,
                    reasons=("RESPONSE_AVAILABLE_AFTER_DECISION_TIME",),
                    references=references,
                )
            return _symbol_result(
                symbol=symbol,
                state=MinuteSymbolState.SUCCEEDED,
                reasons=("SOURCE_ARCHIVED_BEFORE_DECISION_TIME",),
                references=references,
                acquisition=acquisition,
            )
        raise AssertionError("minute retry loop exhausted without settlement")


def publish_minute_acquisition_coverage(
    *, root: Path, artifact: MinuteAcquisitionCoverageArtifact
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        if load_minute_acquisition_coverage(final) != artifact:
            raise FileExistsError(f"conflicting minute coverage exists: {final}")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": MINUTE_COVERAGE_PACKAGE_SCHEMA,
                "artifact_id": str(artifact.artifact_id),
                "content_hash": artifact.content_hash,
                "required_files": sorted(MINUTE_COVERAGE_PACKAGE_FILES),
            },
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {
                name: _file_hash(stage / name)
                for name in ("artifact.json", "manifest.json")
            },
        )
        _load_coverage(stage, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_minute_acquisition_coverage(path: Path) -> MinuteAcquisitionCoverageArtifact:
    return _load_coverage(path, enforce_directory_identity=True)


def _load_coverage(
    path: Path, *, enforce_directory_identity: bool
) -> MinuteAcquisitionCoverageArtifact:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(
        MINUTE_COVERAGE_PACKAGE_FILES
    ):
        raise ValueError("minute coverage exact file set mismatch")
    checksums = _read_json(root / "SHA256SUMS.json")
    if set(checksums) != {"artifact.json", "manifest.json"}:
        raise ValueError("minute coverage checksum index mismatch")
    for name, digest in checksums.items():
        if _file_hash(root / name) != digest:
            raise ValueError(f"minute coverage checksum mismatch: {name}")
    manifest = _read_json(root / "manifest.json")
    artifact = MinuteAcquisitionCoverageArtifact.from_canonical_dict(
        _read_json(root / "artifact.json")
    )
    if (
        manifest.get("schema_version") != MINUTE_COVERAGE_PACKAGE_SCHEMA
        or manifest.get("required_files") != sorted(MINUTE_COVERAGE_PACKAGE_FILES)
        or manifest.get("artifact_id") != str(artifact.artifact_id)
        or manifest.get("content_hash") != artifact.content_hash
        or (enforce_directory_identity and root.name != str(artifact.artifact_id))
    ):
        raise ValueError("minute coverage package identity mismatch")
    return artifact


def _symbol_result(
    *,
    symbol: str,
    state: MinuteSymbolState,
    reasons: tuple[str, ...],
    references: list[MinuteAttemptReference],
    acquisition: MinuteSourceAcquisition | None = None,
) -> MinuteSymbolCoverage:
    return MinuteSymbolCoverage(
        symbol=symbol,
        state=state,
        reason_codes=tuple(sorted(set(reasons))),
        attempt_references=tuple(references),
        accepted_source_artifact_id=(
            acquisition.source_artifact.source_artifact_id
            if acquisition is not None
            else None
        ),
        accepted_source_content_hash=(
            acquisition.source_artifact.content_hash if acquisition is not None else None
        ),
    )


def _only_attempt(root: Path) -> RawMinuteSourceAttempt:
    paths = tuple(root.glob("*.json"))
    if len(paths) != 1:
        raise RuntimeError("minute acquisition did not publish exactly one Attempt")
    return load_raw_minute_attempt(paths[0])


def _retryable(attempt: RawMinuteSourceAttempt) -> bool:
    return (
        attempt.http_status == 429
        or (attempt.http_status is not None and 500 <= attempt.http_status <= 599)
        or (attempt.error_code or "")
        in {
            "CONNECTIONERROR",
            "TIMEOUTERROR",
            "URLERROR",
            "OSERROR",
        }
    )


def _tencent_client_factory(
    _symbol: str, _attempt_number: int, timeout_seconds: float
) -> MinuteSourceClient:
    return TencentMinuteSourceClient(timeout_seconds=timeout_seconds)


def _command_values(command: CandidateMinuteAcquisitionCommand) -> dict[str, Any]:
    return {
        "candidate_set_id": command.candidate_set_id,
        "candidate_set_hash": command.candidate_set_hash,
        "candidate_symbols": command.candidate_symbols,
        "decision_time": command.decision_time,
        "provider_profile_id": command.provider_profile_id,
        "concurrency_limit": command.concurrency_limit,
        "per_request_timeout_seconds": command.per_request_timeout_seconds,
        "max_attempts": command.max_attempts,
        "retry_backoff_seconds": command.retry_backoff_seconds,
        "hard_cutoff": command.hard_cutoff,
    }


def _command_payload_keys() -> set[str]:
    return {
        "schema_version", "candidate_set_id", "candidate_set_hash",
        "candidate_symbols", "decision_time", "provider_profile_id",
        "concurrency_limit", "per_request_timeout_seconds", "max_attempts",
        "retry_backoff_seconds", "hard_cutoff",
    }


def _command_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": MINUTE_BATCH_COMMAND_SCHEMA,
        "candidate_set_id": str(values["candidate_set_id"]),
        "candidate_set_hash": values["candidate_set_hash"],
        "candidate_symbols": list(values["candidate_symbols"]),
        "decision_time": canonical_datetime(values["decision_time"]),
        "provider_profile_id": values["provider_profile_id"],
        "concurrency_limit": values["concurrency_limit"],
        "per_request_timeout_seconds": values["per_request_timeout_seconds"],
        "max_attempts": values["max_attempts"],
        "retry_backoff_seconds": values["retry_backoff_seconds"],
        "hard_cutoff": canonical_datetime(values["hard_cutoff"]),
    }


def _coverage_values(artifact: MinuteAcquisitionCoverageArtifact) -> dict[str, Any]:
    return {
        "command": artifact.command,
        "request_started_at": artifact.request_started_at,
        "request_completed_at": artifact.request_completed_at,
        "coverage_state": artifact.coverage_state,
        "candidate_count": artifact.candidate_count,
        "attempted_count": artifact.attempted_count,
        "succeeded_count": artifact.succeeded_count,
        "failed_count": artifact.failed_count,
        "late_count": artifact.late_count,
        "symbols_succeeded": artifact.symbols_succeeded,
        "symbols_failed": artifact.symbols_failed,
        "symbol_coverage": artifact.symbol_coverage,
        "provider_latency": artifact.provider_latency,
        "reason_codes": artifact.reason_codes,
    }


def _coverage_payload_keys() -> set[str]:
    return {
        "schema_version", "command", "request_started_at", "request_completed_at",
        "coverage_state", "candidate_count", "attempted_count", "succeeded_count",
        "failed_count", "late_count", "symbols_succeeded", "symbols_failed",
        "symbol_coverage", "provider_latency", "reason_codes",
    }


def _coverage_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": MINUTE_COVERAGE_SCHEMA,
        "command": values["command"].to_canonical_dict(),
        "request_started_at": canonical_datetime(values["request_started_at"]),
        "request_completed_at": canonical_datetime(values["request_completed_at"]),
        "coverage_state": values["coverage_state"].value,
        "candidate_count": values["candidate_count"],
        "attempted_count": values["attempted_count"],
        "succeeded_count": values["succeeded_count"],
        "failed_count": values["failed_count"],
        "late_count": values["late_count"],
        "symbols_succeeded": list(values["symbols_succeeded"]),
        "symbols_failed": list(values["symbols_failed"]),
        "symbol_coverage": [item.to_canonical_dict() for item in values["symbol_coverage"]],
        "provider_latency": values["provider_latency"].to_canonical_dict(),
        "reason_codes": list(values["reason_codes"]),
    }


def _percentile(values: list[int], percentile: float) -> int:
    return values[max(0, min(len(values) - 1, int((len(values) - 1) * percentile)))]


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("latency value must be an integer or null")
    return int(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != (canonical_json(payload) + "\n").encode():
        raise ValueError(f"minute coverage JSON is not canonical: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CandidateMinuteAcquisitionCommand",
    "CandidateMinuteBatchAcquirer",
    "MinuteAcquisitionCoverageArtifact",
    "MinuteAttemptReference",
    "MinuteCoverageState",
    "MinuteLatencyDistribution",
    "MinuteSymbolCoverage",
    "MinuteSymbolState",
    "load_minute_acquisition_coverage",
    "publish_minute_acquisition_coverage",
]
