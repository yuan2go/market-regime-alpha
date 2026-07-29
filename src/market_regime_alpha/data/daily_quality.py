"""Fail-closed daily data quality gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite.contracts import (
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)


class DailyDataQualityStatus(str, Enum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"
    DATA_BLOCKED = "DATA_BLOCKED"


_GLOBAL_REQUIRED = (CriticalSourceFact.DECISION_TIME,)
_SYMBOL_REQUIRED = (
    CriticalSourceFact.PRICE,
    CriticalSourceFact.TRADING_STATUS,
    CriticalSourceFact.HISTORY_WINDOW,
    CriticalSourceFact.UNIVERSE_MEMBERSHIP,
    CriticalSourceFact.ELIGIBILITY,
)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DataQualityFinding:
    symbol: str | None
    field_id: str | None
    critical_fact: CriticalSourceFact | None
    reason_code: str
    blocking: bool

    def __post_init__(self) -> None:
        for label, value in (
            ("symbol", self.symbol),
            ("field_id", self.field_id),
        ):
            if value is not None and (
                not isinstance(value, str)
                or not value
                or value != value.strip()
            ):
                raise ValueError(f"{label} must be a trimmed string or None")
        if self.critical_fact is not None and not isinstance(
            self.critical_fact,
            CriticalSourceFact,
        ):
            raise TypeError("critical_fact must be a CriticalSourceFact or None")
        if (
            not isinstance(self.reason_code, str)
            or not self.reason_code
            or self.reason_code != self.reason_code.strip()
        ):
            raise ValueError("reason_code must be a non-empty trimmed string")
        if not isinstance(self.blocking, bool):
            raise TypeError("blocking must be boolean")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "field_id": self.field_id,
            "critical_fact": (
                self.critical_fact.value if self.critical_fact is not None else None
            ),
            "reason_code": self.reason_code,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    SCHEMA_VERSION = "phase-d-data-quality-report-v1"

    source_manifest_id: ArtifactId
    status: DailyDataQualityStatus
    required_symbols: tuple[str, ...]
    findings: tuple[DataQualityFinding, ...]
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    report_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if len(self.required_symbols) != len(set(self.required_symbols)):
            raise ValueError("required_symbols must be unique")
        if tuple(sorted(self.required_symbols)) != self.required_symbols:
            raise ValueError("required_symbols must be ordered")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("public daily quality is EXPLORATORY-only")
        if (
            self.status is DailyDataQualityStatus.DATA_BLOCKED
        ) != any(item.blocking for item in self.findings):
            raise ValueError("DATA_BLOCKED must exactly match blocking findings")
        content_hash = _canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "report_id",
            ArtifactId(f"data-quality-{content_hash.split(':', 1)[1][:24]}"),
        )

    @property
    def blocked_reason_codes(self) -> tuple[str, ...]:
        return tuple(
            item.reason_code for item in self.findings if item.blocking
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "source_manifest_id": str(self.source_manifest_id),
            "status": self.status.value,
            "required_symbols": list(self.required_symbols),
            "findings": [item.to_canonical_dict() for item in self.findings],
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "report_id": str(self.report_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DataQualityReport:
        expected = {
            "schema_version",
            "source_manifest_id",
            "status",
            "required_symbols",
            "findings",
            "data_eligibility",
            "content_hash",
            "report_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("DataQualityReport schema mismatch")
        findings: list[DataQualityFinding] = []
        for value in payload["findings"]:
            if not isinstance(value, Mapping) or set(value) != {
                "symbol",
                "field_id",
                "critical_fact",
                "reason_code",
                "blocking",
            }:
                raise ValueError("DataQualityFinding fields mismatch")
            fact = value["critical_fact"]
            if not isinstance(value["blocking"], bool):
                raise ValueError("DataQualityFinding blocking must be boolean")
            findings.append(
                DataQualityFinding(
                    symbol=(
                        str(value["symbol"])
                        if value["symbol"] is not None
                        else None
                    ),
                    field_id=(
                        str(value["field_id"])
                        if value["field_id"] is not None
                        else None
                    ),
                    critical_fact=(
                        CriticalSourceFact(str(fact))
                        if fact is not None
                        else None
                    ),
                    reason_code=str(value["reason_code"]),
                    blocking=value["blocking"],
                )
            )
        report = cls(
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            status=DailyDataQualityStatus(str(payload["status"])),
            required_symbols=tuple(
                str(item) for item in payload["required_symbols"]
            ),
            findings=tuple(findings),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            report.content_hash != payload["content_hash"]
            or str(report.report_id) != payload["report_id"]
        ):
            raise ValueError("DataQualityReport identity mismatch")
        return report


def evaluate_daily_data_quality(
    *,
    manifest: SourceManifest,
    required_symbols: tuple[str, ...],
) -> DataQualityReport:
    """Require complete critical facts and Point-in-Time availability."""

    symbols = tuple(sorted(required_symbols))
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("required_symbols must be non-empty and unique")
    findings: list[DataQualityFinding] = []
    for fact in _GLOBAL_REQUIRED:
        matches = [
            item
            for item in manifest.fields
            if item.symbol is None and item.critical_fact is fact
        ]
        if not matches:
            findings.append(
                DataQualityFinding(
                    symbol=None,
                    field_id=None,
                    critical_fact=fact,
                    reason_code=f"{fact.value}_MISSING:GLOBAL",
                    blocking=True,
                )
            )
        else:
            findings.extend(_field_findings(manifest, matches[0]))
    for symbol in symbols:
        for fact in _SYMBOL_REQUIRED:
            matches = [
                item
                for item in manifest.fields
                if item.symbol == symbol and item.critical_fact is fact
            ]
            if not matches:
                findings.append(
                    DataQualityFinding(
                        symbol=symbol,
                        field_id=None,
                        critical_fact=fact,
                        reason_code=f"{fact.value}_MISSING:{symbol}",
                        blocking=True,
                    )
                )
            else:
                findings.extend(_field_findings(manifest, matches[0]))
    for item in manifest.fields:
        if item.critical_fact is None:
            findings.extend(_field_findings(manifest, item))
    if any(item.blocking for item in findings):
        status = DailyDataQualityStatus.DATA_BLOCKED
    elif any(
        item.reason_code.startswith("INSUFFICIENT") for item in findings
    ):
        status = DailyDataQualityStatus.INSUFFICIENT
    elif findings or manifest.source_conflicts:
        status = DailyDataQualityStatus.DEGRADED
    else:
        status = DailyDataQualityStatus.COMPLETE
    if manifest.source_conflicts:
        findings.extend(
            DataQualityFinding(
                symbol=None,
                field_id=None,
                critical_fact=None,
                reason_code=f"SOURCE_CONFLICT:{value}",
                blocking=False,
            )
            for value in manifest.source_conflicts
        )
    return DataQualityReport(
        source_manifest_id=manifest.source_manifest_id,
        status=status,
        required_symbols=symbols,
        findings=tuple(findings),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _field_findings(
    manifest: SourceManifest,
    item: SourceManifestField,
) -> list[DataQualityFinding]:
    findings: list[DataQualityFinding] = []
    suffix = f"{item.symbol or 'GLOBAL'}:{item.field_id}"
    if item.available_time is None:
        exploratory_history = (
            item.critical_fact is CriticalSourceFact.HISTORY_WINDOW
            and HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
            in item.reason_codes
            and item.data_eligibility is DataEligibility.EXPLORATORY
        )
        findings.append(
            DataQualityFinding(
                symbol=item.symbol,
                field_id=item.field_id,
                critical_fact=item.critical_fact,
                reason_code=f"AVAILABLE_TIME_MISSING:{suffix}",
                blocking=item.critical_fact is not None
                and not exploratory_history,
            )
        )
    elif item.available_time.as_utc() > manifest.decision_time.as_utc():
        findings.append(
            DataQualityFinding(
                symbol=item.symbol,
                field_id=item.field_id,
                critical_fact=item.critical_fact,
                reason_code=f"AVAILABLE_AFTER_DECISION:{suffix}",
                blocking=item.critical_fact is not None,
            )
        )
    if (
        item.event_time is not None
        and item.event_time.astimezone(manifest.decision_time.value.tzinfo)
        > manifest.decision_time.value
    ):
        findings.append(
            DataQualityFinding(
                symbol=item.symbol,
                field_id=item.field_id,
                critical_fact=item.critical_fact,
                reason_code=f"EVENT_AFTER_DECISION:{suffix}",
                blocking=item.critical_fact is not None,
            )
        )
    if item.quality_status is SourceFieldQualityStatus.INSUFFICIENT:
        reasons = item.reason_codes or ("UNSPECIFIED",)
        findings.extend(
            DataQualityFinding(
                symbol=item.symbol,
                field_id=item.field_id,
                critical_fact=item.critical_fact,
                reason_code=f"INSUFFICIENT:{suffix}:{reason}",
                blocking=item.critical_fact is not None,
            )
            for reason in reasons
        )
    elif item.quality_status is SourceFieldQualityStatus.DEGRADED:
        reasons = item.reason_codes or ("UNSPECIFIED",)
        findings.extend(
            DataQualityFinding(
                symbol=item.symbol,
                field_id=item.field_id,
                critical_fact=item.critical_fact,
                reason_code=f"DEGRADED:{suffix}:{reason}",
                blocking=False,
            )
            for reason in reasons
        )
    return findings
