"""Content-addressed Continuous Research run and tick commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTINUOUS_RESEARCH_COMMAND_SCHEMA = "continuous-research-command-v1"
RUNTIME_TICK_COMMAND_SCHEMA = "continuous-runtime-tick-command-v1"


@dataclass(frozen=True, slots=True)
class ContinuousResearchCommand:
    schema_version: str
    run_id: ArtifactId
    command_hash: str
    idempotency_key: str
    trading_date: date
    requested_symbols: tuple[str, ...]
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    policy_id: ArtifactId
    policy_hash: str
    provider_configuration_id: ArtifactId
    provider_configuration_hash: str
    research_configuration_id: ArtifactId
    research_configuration_hash: str
    code_revision: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_RESEARCH_COMMAND_SCHEMA:
            raise ValueError("unsupported Continuous Research command schema")
        require_text("idempotency_key", self.idempotency_key)
        require_text("code_revision", self.code_revision)
        require_unique_text("requested_symbols", self.requested_symbols)
        if not self.requested_symbols or self.requested_symbols != tuple(
            sorted(self.requested_symbols)
        ):
            raise ValueError("requested_symbols must be non-empty, unique, and sorted")
        for label, value in (
            ("command_hash", self.command_hash),
            ("trading_calendar_hash", self.trading_calendar_hash),
            ("policy_hash", self.policy_hash),
            ("provider_configuration_hash", self.provider_configuration_hash),
            ("research_configuration_hash", self.research_configuration_hash),
        ):
            require_sha256(label, value)
        _require_authority_ceiling(self.limitations)
        self.verify_identity()

    @property
    def request_scope_hash(self) -> str:
        return canonical_hash({"requested_symbols": list(self.requested_symbols)})

    @classmethod
    def create(
        cls,
        *,
        idempotency_key: str,
        trading_date: date,
        requested_symbols: tuple[str, ...],
        trading_calendar_id: ArtifactId,
        trading_calendar_hash: str,
        policy_id: ArtifactId,
        policy_hash: str,
        provider_configuration_id: ArtifactId,
        provider_configuration_hash: str,
        research_configuration_id: ArtifactId,
        research_configuration_hash: str,
        code_revision: str,
        limitations: tuple[str, ...],
    ) -> ContinuousResearchCommand:
        values: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "trading_date": trading_date,
            "requested_symbols": tuple(sorted(set(requested_symbols))),
            "trading_calendar_id": trading_calendar_id,
            "trading_calendar_hash": trading_calendar_hash,
            "policy_id": policy_id,
            "policy_hash": policy_hash,
            "provider_configuration_id": provider_configuration_id,
            "provider_configuration_hash": provider_configuration_hash,
            "research_configuration_id": research_configuration_id,
            "research_configuration_hash": research_configuration_hash,
            "code_revision": code_revision,
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_run_payload(**values))
        return cls(
            schema_version=CONTINUOUS_RESEARCH_COMMAND_SCHEMA,
            run_id=ArtifactId(
                f"continuous-research-run-{digest.split(':', 1)[1][:24]}"
            ),
            command_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _run_payload(
            idempotency_key=self.idempotency_key,
            trading_date=self.trading_date,
            requested_symbols=self.requested_symbols,
            trading_calendar_id=self.trading_calendar_id,
            trading_calendar_hash=self.trading_calendar_hash,
            policy_id=self.policy_id,
            policy_hash=self.policy_hash,
            provider_configuration_id=self.provider_configuration_id,
            provider_configuration_hash=self.provider_configuration_hash,
            research_configuration_id=self.research_configuration_id,
            research_configuration_hash=self.research_configuration_hash,
            code_revision=self.code_revision,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.command_hash:
            raise ValueError("Continuous Research command hash mismatch")
        expected = f"continuous-research-run-{digest.split(':', 1)[1][:24]}"
        if str(self.run_id) != expected:
            raise ValueError("Continuous Research run identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "command_hash": self.command_hash,
            "request_scope_hash": self.request_scope_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ContinuousResearchCommand:
        expected = {
            "schema_version",
            "run_id",
            "command_hash",
            "request_scope_hash",
            "idempotency_key",
            "trading_date",
            "requested_symbols",
            "trading_calendar_id",
            "trading_calendar_hash",
            "policy_id",
            "policy_hash",
            "provider_configuration_id",
            "provider_configuration_hash",
            "research_configuration_id",
            "research_configuration_hash",
            "code_revision",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Continuous Research command fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            run_id=ArtifactId(str(payload["run_id"])),
            command_hash=str(payload["command_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            requested_symbols=_strings(payload["requested_symbols"], "requested_symbols"),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            provider_configuration_id=ArtifactId(
                str(payload["provider_configuration_id"])
            ),
            provider_configuration_hash=str(
                payload["provider_configuration_hash"]
            ),
            research_configuration_id=ArtifactId(
                str(payload["research_configuration_id"])
            ),
            research_configuration_hash=str(
                payload["research_configuration_hash"]
            ),
            code_revision=str(payload["code_revision"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        if result.request_scope_hash != str(payload["request_scope_hash"]):
            raise ValueError("Continuous Research request scope hash mismatch")
        return result


@dataclass(frozen=True, slots=True)
class RuntimeTickCommand:
    schema_version: str
    tick_id: ArtifactId
    tick_hash: str
    idempotency_key: str
    run_id: ArtifactId
    trading_date: date
    observed_at: datetime
    request_scope_hash: str
    provider_configuration_id: ArtifactId
    provider_configuration_hash: str
    research_configuration_id: ArtifactId
    research_configuration_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_TICK_COMMAND_SCHEMA:
            raise ValueError("unsupported Runtime Tick command schema")
        require_text("idempotency_key", self.idempotency_key)
        require_utc_second("observed_at", self.observed_at)
        for label, value in (
            ("tick_hash", self.tick_hash),
            ("request_scope_hash", self.request_scope_hash),
            ("provider_configuration_hash", self.provider_configuration_hash),
            ("research_configuration_hash", self.research_configuration_hash),
        ):
            require_sha256(label, value)
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        idempotency_key: str,
        run_id: ArtifactId,
        trading_date: date,
        observed_at: datetime,
        request_scope_hash: str,
        provider_configuration_id: ArtifactId,
        provider_configuration_hash: str,
        research_configuration_id: ArtifactId,
        research_configuration_hash: str,
    ) -> RuntimeTickCommand:
        values: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "run_id": run_id,
            "trading_date": trading_date,
            "observed_at": observed_at,
            "request_scope_hash": request_scope_hash,
            "provider_configuration_id": provider_configuration_id,
            "provider_configuration_hash": provider_configuration_hash,
            "research_configuration_id": research_configuration_id,
            "research_configuration_hash": research_configuration_hash,
        }
        digest = canonical_hash(_tick_payload(**values))
        return cls(
            schema_version=RUNTIME_TICK_COMMAND_SCHEMA,
            tick_id=ArtifactId(
                f"continuous-research-tick-{digest.split(':', 1)[1][:24]}"
            ),
            tick_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _tick_payload(
            idempotency_key=self.idempotency_key,
            run_id=self.run_id,
            trading_date=self.trading_date,
            observed_at=self.observed_at,
            request_scope_hash=self.request_scope_hash,
            provider_configuration_id=self.provider_configuration_id,
            provider_configuration_hash=self.provider_configuration_hash,
            research_configuration_id=self.research_configuration_id,
            research_configuration_hash=self.research_configuration_hash,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.tick_hash:
            raise ValueError("Runtime Tick command hash mismatch")
        expected = f"continuous-research-tick-{digest.split(':', 1)[1][:24]}"
        if str(self.tick_id) != expected:
            raise ValueError("Runtime Tick identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "tick_id": str(self.tick_id),
            "tick_hash": self.tick_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RuntimeTickCommand:
        expected = {"tick_id", "tick_hash", *_tick_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Runtime Tick command fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            tick_id=ArtifactId(str(payload["tick_id"])),
            tick_hash=str(payload["tick_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            run_id=ArtifactId(str(payload["run_id"])),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            observed_at=parse_utc_second("observed_at", payload["observed_at"]),
            request_scope_hash=str(payload["request_scope_hash"]),
            provider_configuration_id=ArtifactId(
                str(payload["provider_configuration_id"])
            ),
            provider_configuration_hash=str(
                payload["provider_configuration_hash"]
            ),
            research_configuration_id=ArtifactId(
                str(payload["research_configuration_id"])
            ),
            research_configuration_hash=str(
                payload["research_configuration_hash"]
            ),
        )


def _run_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTINUOUS_RESEARCH_COMMAND_SCHEMA,
        "idempotency_key": values["idempotency_key"],
        "trading_date": values["trading_date"].isoformat(),
        "requested_symbols": list(values["requested_symbols"]),
        "trading_calendar_id": str(values["trading_calendar_id"]),
        "trading_calendar_hash": values["trading_calendar_hash"],
        "policy_id": str(values["policy_id"]),
        "policy_hash": values["policy_hash"],
        "provider_configuration_id": str(values["provider_configuration_id"]),
        "provider_configuration_hash": values["provider_configuration_hash"],
        "research_configuration_id": str(values["research_configuration_id"]),
        "research_configuration_hash": values["research_configuration_hash"],
        "code_revision": values["code_revision"],
        "limitations": list(values["limitations"]),
    }


def _tick_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_TICK_COMMAND_SCHEMA,
        "idempotency_key": values["idempotency_key"],
        "run_id": str(values["run_id"]),
        "trading_date": values["trading_date"].isoformat(),
        "observed_at": canonical_datetime(values["observed_at"]),
        "request_scope_hash": values["request_scope_hash"],
        "provider_configuration_id": str(values["provider_configuration_id"]),
        "provider_configuration_hash": values["provider_configuration_hash"],
        "research_configuration_id": str(values["research_configuration_id"]),
        "research_configuration_hash": values["research_configuration_hash"],
    }


def _tick_payload_keys() -> set[str]:
    return {
        "schema_version",
        "idempotency_key",
        "run_id",
        "trading_date",
        "observed_at",
        "request_scope_hash",
        "provider_configuration_id",
        "provider_configuration_hash",
        "research_configuration_id",
        "research_configuration_hash",
    }


def _require_authority_ceiling(limitations: tuple[str, ...]) -> None:
    require_unique_text("command limitation", limitations)
    if limitations != tuple(sorted(limitations)):
        raise ValueError("Continuous Research limitations must be sorted")
    for required in (
        "ENTRY_BLOCKED",
        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        "FORMAL_PIT_NOT_ESTABLISHED",
        "NO_BROKER_AUTHORITY",
    ):
        if required not in limitations:
            raise ValueError("Continuous Research command authority ceiling is incomplete")


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


__all__ = [
    "CONTINUOUS_RESEARCH_COMMAND_SCHEMA",
    "RUNTIME_TICK_COMMAND_SCHEMA",
    "ContinuousResearchCommand",
    "RuntimeTickCommand",
]
