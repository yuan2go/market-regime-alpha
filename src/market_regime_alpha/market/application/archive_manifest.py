"""Deterministic operator Artifact for an exact MarketArchive command roster.

The manifest is an application DTO only.  PostgreSQL MarketArchive, slice, and
prospective-generation relations remain the business Authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from uuid import UUID

from market_regime_alpha.market.application.archive import (
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
    BarTimeframe,
    PriceBasis,
    ProspectiveArchiveGenerationPlan,
    ProspectiveArchiveMemberPlan,
    ProspectiveArchiveScheduleSlot,
    ProspectiveArchiveSliceSchedulePlan,
)
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


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

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    def to_json(self) -> str:
        request = self.start_request
        payload: dict[str, object] = {
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
            "version": 2 if request.prospective_generation is not None else 1,
        }
        if request.prospective_generation is not None:
            generation = request.prospective_generation
            payload["prospective_generation"] = {
                "decision_session_id": str(generation.decision_session_id),
                "exchange": generation.exchange,
                "generation": generation.generation,
                "later_verification_session_id": str(
                    generation.later_verification_session_id
                ),
                "members": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "instrument_identifier_id": str(
                            item.instrument_identifier_id
                        ),
                        "ordinal": item.ordinal,
                    }
                    for item in generation.members
                ],
                "outcome_checkpoint_id": str(generation.outcome_checkpoint_id),
                "outcome_session_id": str(generation.outcome_session_id),
                "predecessor_market_archive_id": (
                    str(generation.predecessor_market_archive_id)
                    if generation.predecessor_market_archive_id is not None
                    else None
                ),
                "provenance_sha256": str(generation.provenance_sha256),
                "reference_checkpoint_id": str(
                    generation.reference_checkpoint_id
                ),
                "schedules": [
                    {
                        "comparison_ordinal": item.comparison_ordinal,
                        "instrument_id": str(item.instrument_id),
                        "market_archive_slice_id": str(
                            item.market_archive_slice_id
                        ),
                        "ordinal": item.ordinal,
                        "slot": item.slot.value,
                        "target_checkpoint_id": str(item.target_checkpoint_id),
                        "trading_session_id": str(item.trading_session_id),
                    }
                    for item in generation.schedules
                ],
                "series_code": generation.series_code,
                "target_definition_id": str(generation.target_definition_id),
                "target_definition_sha256": str(
                    generation.target_definition_sha256
                ),
                "target_version": generation.target_version,
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
            if not isinstance(raw, dict) or raw.get("version") not in {1, 2}:
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
            prospective_generation = _generation(raw)
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
                prospective_generation=prospective_generation,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("archive operator manifest is invalid") from exc
        return cls(request, tuple(slices))


def _generation(raw: dict[str, object]) -> ProspectiveArchiveGenerationPlan | None:
    if raw["version"] == 1:
        return None
    generation_raw = raw.get("prospective_generation")
    if not isinstance(generation_raw, dict):
        raise ValueError("prospective generation is required")
    return ProspectiveArchiveGenerationPlan(
        market_archive_id=UUID(str(raw["market_archive_id"])),
        series_code=str(generation_raw["series_code"]),
        generation=int(generation_raw["generation"]),
        predecessor_market_archive_id=(
            UUID(str(generation_raw["predecessor_market_archive_id"]))
            if generation_raw["predecessor_market_archive_id"] is not None
            else None
        ),
        exchange=str(generation_raw["exchange"]),
        target_definition_id=UUID(str(generation_raw["target_definition_id"])),
        target_version=int(generation_raw["target_version"]),
        target_definition_sha256=str(generation_raw["target_definition_sha256"]),
        reference_checkpoint_id=UUID(str(generation_raw["reference_checkpoint_id"])),
        outcome_checkpoint_id=UUID(str(generation_raw["outcome_checkpoint_id"])),
        decision_session_id=UUID(str(generation_raw["decision_session_id"])),
        outcome_session_id=UUID(str(generation_raw["outcome_session_id"])),
        later_verification_session_id=UUID(
            str(generation_raw["later_verification_session_id"])
        ),
        members=tuple(
            ProspectiveArchiveMemberPlan(
                instrument_id=UUID(str(item["instrument_id"])),
                instrument_identifier_id=UUID(
                    str(item["instrument_identifier_id"])
                ),
                ordinal=int(item["ordinal"]),
            )
            for item in generation_raw["members"]
        ),
        schedules=tuple(
            ProspectiveArchiveSliceSchedulePlan(
                market_archive_slice_id=UUID(str(item["market_archive_slice_id"])),
                instrument_id=UUID(str(item["instrument_id"])),
                ordinal=int(item["ordinal"]),
                slot=ProspectiveArchiveScheduleSlot(str(item["slot"])),
                trading_session_id=UUID(str(item["trading_session_id"])),
                target_checkpoint_id=UUID(str(item["target_checkpoint_id"])),
                comparison_ordinal=int(item["comparison_ordinal"]),
            )
            for item in generation_raw["schedules"]
        ),
        provenance_sha256=str(generation_raw["provenance_sha256"]),
    )


def _datetime(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("archive manifest datetime must be a string")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("archive manifest datetime must include an offset")
    return value


__all__ = ["ArchiveManifestSlice", "ArchiveOperatorManifest"]
