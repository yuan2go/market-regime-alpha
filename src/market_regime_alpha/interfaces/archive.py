"""Controlled archive operator surface over the sole target composition root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from uuid import UUID

from market_regime_alpha.bootstrap import (
    TargetApplication,
    TargetSettings,
    database_identity,
)
from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveProvider,
    BaoStockArchiveQuery,
    BaoStockSdk,
    BaoStockSession,
)
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import (
    BaoStockArchiveNormalizer,
)
from market_regime_alpha.market.application import (
    ArchiveSliceExecutionRequest,
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe, PriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_NON_OPERATIONAL_DATABASE = re.compile(
    r"(^|[_-])(test(?:ing)?\d*|dev(?:elopment)?\d*|qual(?:ification)?\d*|fixture\d*|tmp\d*|temp\d*)([_-]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ArchiveManifestSlice:
    plan: ArchiveSlicePlan
    capture_request: CaptureRequest
    schedule_slot: str


@dataclass(frozen=True, slots=True)
class ArchiveOperatorManifest:
    start_request: StartMarketArchiveRequest
    slices: tuple[ArchiveManifestSlice, ...]

    def __post_init__(self) -> None:
        if tuple(item.plan for item in self.slices) != self.start_request.slices:
            raise ValueError("operator manifest slice roster differs from Start request")
        if any(
            item.plan.request_sha256 != canonical_json_sha256(item.capture_request)
            for item in self.slices
        ):
            raise ValueError("operator manifest CaptureRequest hash differs from slice")

    def to_json(self) -> str:
        request = self.start_request
        payload = {
            "archive_code": request.archive_code,
            "code_artifact_id": str(request.code_artifact_id),
            "config_artifact_id": str(request.config_artifact_id),
            "event_window_end": request.event_window_end.isoformat(),
            "event_window_start": request.event_window_start.isoformat(),
            "exchange_code": request.exchange_code,
            "instrument_scope": request.instrument_scope,
            "instrument_scope_sha256": request.instrument_scope_sha256,
            "lane": request.lane.value,
            "market_archive_id": str(request.market_archive_id),
            "maximum_archive_bytes": request.maximum_archive_bytes,
            "maximum_slice_bytes": request.maximum_slice_bytes,
            "price_basis": request.price_basis.value,
            "provenance_sha256": request.provenance_sha256,
            "provider_product_id": str(request.provider_product_id),
            "reserved_free_bytes": request.reserved_free_bytes,
            "slices": [
                {
                    "capture_request": {
                        "capture_key": item.capture_request.capture_key,
                        "provider_product_id": str(
                            item.capture_request.provider_product_id
                        ),
                        "request_headers_hash": str(
                            item.capture_request.request_headers_hash
                        ),
                        "resource": item.capture_request.resource,
                    },
                    "event_window_end": item.plan.event_window_end.isoformat(),
                    "event_window_start": item.plan.event_window_start.isoformat(),
                    "expected_fact_kind": item.plan.expected_fact_kind,
                    "market_archive_slice_id": str(
                        item.plan.market_archive_slice_id
                    ),
                    "ordinal": item.plan.ordinal,
                    "schedule_slot": item.schedule_slot,
                    "scope_key": item.plan.scope_key,
                }
                for item in self.slices
            ],
            "timeframe": request.timeframe.value,
            "version": 1,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> ArchiveOperatorManifest:
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("archive manifest version is unsupported")
            slice_rows = raw["slices"]
            if not isinstance(slice_rows, list) or not slice_rows:
                raise ValueError("archive manifest slices must be non-empty")
            slices: list[ArchiveManifestSlice] = []
            for item in slice_rows:
                capture_raw = item["capture_request"]
                capture = CaptureRequest(
                    provider_product_id=UUID(capture_raw["provider_product_id"]),
                    capture_key=str(capture_raw["capture_key"]),
                    resource=str(capture_raw["resource"]),
                    request_headers_hash=ContentHash(
                        str(capture_raw["request_headers_hash"])
                    ),
                )
                plan = ArchiveSlicePlan(
                    market_archive_slice_id=UUID(item["market_archive_slice_id"]),
                    ordinal=int(item["ordinal"]),
                    scope_key=str(item["scope_key"]),
                    event_window_start=_datetime(item["event_window_start"]),
                    event_window_end=_datetime(item["event_window_end"]),
                    request_sha256=canonical_json_sha256(capture),
                    expected_fact_kind=str(item["expected_fact_kind"]),
                )
                slices.append(
                    ArchiveManifestSlice(
                        plan=plan,
                        capture_request=capture,
                        schedule_slot=str(item["schedule_slot"]),
                    )
                )
            provider_product_id = UUID(raw["provider_product_id"])
            if any(
                item.capture_request.provider_product_id != provider_product_id
                for item in slices
            ):
                raise ValueError("archive manifest mixes ProviderProduct identities")
            request = StartMarketArchiveRequest(
                market_archive_id=UUID(raw["market_archive_id"]),
                archive_code=str(raw["archive_code"]),
                lane=ArchiveLane(raw["lane"]),
                provider_product_id=provider_product_id,
                exchange_code=str(raw["exchange_code"]),
                timeframe=BarTimeframe(raw["timeframe"]),
                price_basis=PriceBasis(raw["price_basis"]),
                instrument_scope=str(raw["instrument_scope"]),
                instrument_scope_sha256=str(raw["instrument_scope_sha256"]),
                event_window_start=_datetime(raw["event_window_start"]),
                event_window_end=_datetime(raw["event_window_end"]),
                reserved_free_bytes=int(raw["reserved_free_bytes"]),
                maximum_archive_bytes=int(raw["maximum_archive_bytes"]),
                maximum_slice_bytes=int(raw["maximum_slice_bytes"]),
                code_artifact_id=UUID(raw["code_artifact_id"]),
                config_artifact_id=UUID(raw["config_artifact_id"]),
                provenance_sha256=str(raw["provenance_sha256"]),
                slices=tuple(item.plan for item in slices),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("archive operator manifest is invalid") from exc
        return cls(request, tuple(slices))


def require_isolated_operational_target(
    settings: TargetSettings,
    *,
    expected_database_name: str,
) -> None:
    identity = database_identity(settings)
    validate_operational_target(
        database_name=identity.database_name,
        artifact_root=settings.artifact_root,
        expected_database_name=expected_database_name,
    )


def validate_operational_target(
    *,
    database_name: str,
    artifact_root: Path,
    expected_database_name: str,
) -> None:
    if database_name != expected_database_name:
        raise ValueError("operational archive database identity differs from operator intent")
    if database_name in {"postgres", "template0", "template1"} or _NON_OPERATIONAL_DATABASE.search(database_name):
        raise ValueError("archive operations reject system/disposable database identities")
    lowered_parts = {part.lower() for part in artifact_root.parts}
    if lowered_parts.intersection({"tmp", "temp", "test", "tests", "fixtures"}):
        raise ValueError("archive operations reject disposable Artifact roots")


def start_archive(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    actor_id: str,
) -> object:
    return application.market_archives.start(
        manifest.start_request,
        _context(manifest, actor_id, "start"),
    )


def resume_archive(
    application: TargetApplication,
    manifest: ArchiveOperatorManifest,
    *,
    sdk: BaoStockSdk,
    actor_id: str,
    operation_key: str,
    slice_ids: tuple[UUID, ...] | None = None,
) -> tuple[object, ...]:
    results: list[object] = []
    selected = set(slice_ids or ())
    if slice_ids is not None and (
        not slice_ids
        or len(selected) != len(slice_ids)
        or not selected.issubset(
            {item.plan.market_archive_slice_id for item in manifest.slices}
        )
    ):
        raise ValueError("selected archive slice roster is empty, duplicate, or unknown")
    with BaoStockSession(sdk) as session:
        provider = BaoStockArchiveProvider(session)
        for item in manifest.slices:
            if slice_ids is not None and item.plan.market_archive_slice_id not in selected:
                continue
            query = BaoStockArchiveQuery.from_resource(item.capture_request.resource)
            normalizer = BaoStockArchiveNormalizer(
                expected_query=query,
                revision_lineage=application.market_revision_lineage,
                trading_sessions=application.archive_trading_sessions,
            )
            results.append(
                application.archive_operations.execute_slice(
                    ArchiveSliceExecutionRequest(
                        market_archive_id=manifest.start_request.market_archive_id,
                        market_archive_slice_id=item.plan.market_archive_slice_id,
                        capture_request=item.capture_request,
                        schedule_slot=item.schedule_slot,
                    ),
                    provider=provider,
                    normalizer=normalizer,
                    context=_context(manifest, actor_id, f"{operation_key}-{item.plan.ordinal}"),
                )
            )
    return tuple(results)


def archive_report(application: TargetApplication, archive_id: UUID, kind: str) -> object:
    report = application.archive_inspection.inspect(archive_id)
    if kind == "inspect" or kind == "daily-health":
        return report
    if kind == "gap-report":
        return {
            "market_archive_id": archive_id,
            "gaps": tuple(
                item for item in report.slices if item.gap_id is not None
            ),
            "resource_stops": tuple(
                item for item in report.slices if item.status == "RESOURCE_LIMIT"
            ),
        }
    if kind == "revision-report":
        return {
            "market_archive_id": archive_id,
            "changed_observation_count": report.changed_observation_count,
            "market_revision_successor_count": report.market_revision_successor_count,
            "slices": tuple(
                item for item in report.slices if item.observation_count > 0
            ),
        }
    raise ValueError("archive report kind is unsupported")


def load_archive_manifest(path: Path) -> ArchiveOperatorManifest:
    return ArchiveOperatorManifest.from_json(path.read_text(encoding="utf-8"))


def _context(
    manifest: ArchiveOperatorManifest,
    actor_id: str,
    suffix: str,
) -> CommandContext:
    return CommandContext(
        idempotency_key=(
            f"archive:{manifest.start_request.market_archive_id}:{suffix}"
        ),
        actor_type=ActorType.OPERATOR,
        actor_id=actor_id,
        reason_code="WP17P_ARCHIVE_OPERATION",
    )


def _datetime(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("archive manifest datetime must be a string")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("archive manifest datetime must include an offset")
    return value


__all__ = [
    "ArchiveOperatorManifest",
    "archive_report",
    "load_archive_manifest",
    "require_isolated_operational_target",
    "resume_archive",
    "start_archive",
    "validate_operational_target",
]
