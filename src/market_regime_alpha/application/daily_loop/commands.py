"""Deterministic pre-acquisition and post-Source-Freeze run identities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, StableId
from market_regime_alpha.core.time import DecisionTime


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_CONTENT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RunRequestId(StableId):
    """Identity of one normalized command before provider acquisition."""


@dataclass(frozen=True, slots=True)
class DailyRunId(StableId):
    """Evidence-bound run identity created only after Source Freeze."""


class RunMode(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"


def _require_text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_content_hash(label: str, value: str) -> None:
    if not isinstance(value, str) or _CONTENT_HASH.fullmatch(value) is None:
        raise ValueError(f"{label} must be a sha256-prefixed lowercase digest")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DailyRunCommand:
    """All normalized request semantics known before acquisition."""

    SCHEMA_VERSION = "daily-run-command-v1"

    decision_date: date
    decision_time: DecisionTime
    run_mode: RunMode
    provider_profile_id: str
    universe_policy_id: str
    model_set_id: str
    configuration_identity: ArtifactId
    output_root: Path
    replay_source_manifest_id: ArtifactId | None = None
    content_hash: str = field(init=False)
    run_request_id: RunRequestId = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.decision_date, date):
            raise TypeError("decision_date must be a date")
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        local = self.decision_time.value.astimezone(_SHANGHAI)
        if local.date() != self.decision_date:
            raise ValueError("decision_date must equal the Asia/Shanghai Decision Time date")
        if local.timetz().replace(tzinfo=None) != time(14, 55):
            raise ValueError("daily loop requires 14:55 Asia/Shanghai Decision Time")
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be a RunMode")
        for label, value in (
            ("provider_profile_id", self.provider_profile_id),
            ("universe_policy_id", self.universe_policy_id),
            ("model_set_id", self.model_set_id),
        ):
            _require_text(label, value)
        if not isinstance(self.configuration_identity, ArtifactId):
            raise TypeError("configuration_identity must be an ArtifactId")
        if not isinstance(self.output_root, Path):
            raise TypeError("output_root must be a Path")
        object.__setattr__(self, "output_root", self.output_root.resolve())
        if self.run_mode is RunMode.REPLAY and self.replay_source_manifest_id is None:
            raise ValueError("REPLAY requires replay_source_manifest_id")
        if self.run_mode is RunMode.LIVE and self.replay_source_manifest_id is not None:
            raise ValueError("LIVE cannot carry replay_source_manifest_id")
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "run_request_id",
            RunRequestId(f"run-request-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "decision_date": self.decision_date.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "run_mode": self.run_mode.value,
            "provider_profile_id": self.provider_profile_id,
            "universe_policy_id": self.universe_policy_id,
            "model_set_id": self.model_set_id,
            "configuration_identity": str(self.configuration_identity),
            "output_root": str(self.output_root),
            "replay_source_manifest_id": (
                str(self.replay_source_manifest_id)
                if self.replay_source_manifest_id is not None
                else None
            ),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "run_request_id": str(self.run_request_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DailyRunCommand:
        expected = {
            "schema_version",
            "decision_date",
            "decision_time",
            "run_mode",
            "provider_profile_id",
            "universe_policy_id",
            "model_set_id",
            "configuration_identity",
            "output_root",
            "replay_source_manifest_id",
            "content_hash",
            "run_request_id",
        }
        if set(payload) != expected:
            raise ValueError("DailyRunCommand fields mismatch")
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported DailyRunCommand schema")
        replay_id = payload.get("replay_source_manifest_id")
        result = cls(
            decision_date=date.fromisoformat(
                _string(payload.get("decision_date"), "decision_date")
            ),
            decision_time=DecisionTime(
                _aware_datetime(payload.get("decision_time"), "decision_time")
            ),
            run_mode=RunMode(_string(payload.get("run_mode"), "run_mode")),
            provider_profile_id=_string(
                payload.get("provider_profile_id"),
                "provider_profile_id",
            ),
            universe_policy_id=_string(
                payload.get("universe_policy_id"),
                "universe_policy_id",
            ),
            model_set_id=_string(payload.get("model_set_id"), "model_set_id"),
            configuration_identity=ArtifactId(
                _string(
                    payload.get("configuration_identity"),
                    "configuration_identity",
                )
            ),
            output_root=Path(_string(payload.get("output_root"), "output_root")),
            replay_source_manifest_id=(
                ArtifactId(_string(replay_id, "replay_source_manifest_id"))
                if replay_id is not None
                else None
            ),
        )
        if result.content_hash != _string(
            payload.get("content_hash"),
            "content_hash",
        ):
            raise ValueError("DailyRunCommand content hash mismatch")
        if str(result.run_request_id) != _string(
            payload.get("run_request_id"),
            "run_request_id",
        ):
            raise ValueError("RunRequestId mismatch")
        return result


@dataclass(frozen=True, slots=True)
class DailyRunIdentity:
    """Post-freeze identity binding the request to exact source bytes."""

    SCHEMA_VERSION = "daily-run-identity-v1"

    run_request_id: RunRequestId
    run_request_hash: str
    code_revision: str
    configuration_hash: str
    source_manifest_id: ArtifactId
    source_manifest_content_hash: str
    source_content_hashes: tuple[str, ...]
    content_hash: str = field(init=False)
    daily_run_id: DailyRunId = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.run_request_id, RunRequestId):
            raise TypeError("run_request_id must be a RunRequestId")
        _require_content_hash("run_request_hash", self.run_request_hash)
        _require_text("code_revision", self.code_revision)
        _require_content_hash("configuration_hash", self.configuration_hash)
        if not isinstance(self.source_manifest_id, ArtifactId):
            raise TypeError("source_manifest_id must be an ArtifactId")
        _require_content_hash(
            "source_manifest_content_hash",
            self.source_manifest_content_hash,
        )
        if not self.source_content_hashes:
            raise ValueError("source_content_hashes must not be empty")
        if len(self.source_content_hashes) != len(set(self.source_content_hashes)):
            raise ValueError("source_content_hashes must be unique")
        if tuple(sorted(self.source_content_hashes)) != self.source_content_hashes:
            raise ValueError("source_content_hashes must be sorted")
        for value in self.source_content_hashes:
            _require_content_hash("source_content_hash", value)
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "daily_run_id",
            DailyRunId(f"daily-run-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "run_request_id": str(self.run_request_id),
            "run_request_hash": self.run_request_hash,
            "code_revision": self.code_revision,
            "configuration_hash": self.configuration_hash,
            "source_manifest_id": str(self.source_manifest_id),
            "source_manifest_content_hash": self.source_manifest_content_hash,
            "source_content_hashes": list(self.source_content_hashes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "daily_run_id": str(self.daily_run_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DailyRunIdentity:
        expected = {
            "schema_version",
            "run_request_id",
            "run_request_hash",
            "code_revision",
            "configuration_hash",
            "source_manifest_id",
            "source_manifest_content_hash",
            "source_content_hashes",
            "content_hash",
            "daily_run_id",
        }
        if set(payload) != expected:
            raise ValueError("DailyRunIdentity fields mismatch")
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported DailyRunIdentity schema")
        hashes = payload.get("source_content_hashes")
        if not isinstance(hashes, list) or any(
            not isinstance(item, str) for item in hashes
        ):
            raise ValueError("source_content_hashes must be an array of strings")
        result = cls(
            run_request_id=RunRequestId(
                _string(payload.get("run_request_id"), "run_request_id")
            ),
            run_request_hash=_string(
                payload.get("run_request_hash"),
                "run_request_hash",
            ),
            code_revision=_string(
                payload.get("code_revision"),
                "code_revision",
            ),
            configuration_hash=_string(
                payload.get("configuration_hash"),
                "configuration_hash",
            ),
            source_manifest_id=ArtifactId(
                _string(payload.get("source_manifest_id"), "source_manifest_id")
            ),
            source_manifest_content_hash=_string(
                payload.get("source_manifest_content_hash"),
                "source_manifest_content_hash",
            ),
            source_content_hashes=tuple(hashes),
        )
        if result.content_hash != _string(
            payload.get("content_hash"),
            "content_hash",
        ):
            raise ValueError("DailyRunIdentity content hash mismatch")
        if str(result.daily_run_id) != _string(
            payload.get("daily_run_id"),
            "daily_run_id",
        ):
            raise ValueError("DailyRunId mismatch")
        return result


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _aware_datetime(value: object, label: str) -> datetime:
    raw = _string(value, label)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed
