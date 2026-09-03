"""Permanent Target/Session-aligned prospective MarketArchive planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
)
from market_regime_alpha.market.application.archive import (
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.application.archive_manifest import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
    BarTimeframe,
    PriceBasis,
    ProspectiveArchiveGenerationPlan,
    ProspectiveArchiveMemberPlan,
    ProspectiveArchiveSliceSchedulePlan,
    TargetArchiveSessions,
    target_aligned_capture_windows,
)
from market_regime_alpha.market.ports import CaptureRequest, TargetArchiveContract
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_EMPTY_HEADERS_SHA256 = canonical_json_sha256({})


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveInstrument:
    instrument_id: UUID
    instrument_identifier_id: UUID
    provider_code: str

    def __post_init__(self) -> None:
        if not self.provider_code.startswith(("sh.", "sz.")):
            raise ValueError("prospective archive Provider instrument code is invalid")


def build_target_aligned_prospective_manifest(
    *,
    provider_product_id: UUID,
    code_artifact_id: UUID,
    config_artifact_id: UUID,
    contract: TargetArchiveContract,
    resolved_sessions: TargetArchiveSessions,
    instruments: tuple[ProspectiveArchiveInstrument, ...],
    series_code: str,
    generation: int,
    predecessor_market_archive_id: UUID | None,
    planned_not_before: datetime,
    provenance_sha256: str,
    reserved_free_bytes: int = 2_000_000_000,
    maximum_archive_bytes: int = 1_000_000_000,
    maximum_slice_bytes: int = 50_000_000,
) -> ArchiveOperatorManifest:
    """Freeze one future generation without weekday or mutable-name inference."""

    if planned_not_before.tzinfo is None or planned_not_before.utcoffset() is None:
        raise ValueError("planned_not_before must include an offset")
    if not instruments or len({item.instrument_id for item in instruments}) != len(
        instruments
    ):
        raise ValueError("prospective archive instrument roster is empty or duplicate")
    instruments = tuple(sorted(instruments, key=lambda item: item.provider_code))
    exchange = resolved_sessions.decision.exchange
    expected_prefix = {"XSHG": "sh.", "XSHE": "sz."}.get(exchange)
    if expected_prefix is None or any(
        not item.provider_code.startswith(expected_prefix) for item in instruments
    ):
        raise ValueError("prospective archive instrument roster crosses exchange calendar")
    windows = target_aligned_capture_windows(resolved_sessions)
    planned_not_before = planned_not_before.astimezone(UTC)
    if min(item.window_start for item in windows) < planned_not_before:
        raise ValueError("prospective generation cannot backdate an elapsed window")
    archive_id = _id(
        f"archive:{series_code}:{generation}:{resolved_sessions.decision.session_id}:"
        f"{contract.target_definition_id}"
    )
    archive_code = f"prospective_{series_code}_g{generation:04d}"
    member_plans = tuple(
        ProspectiveArchiveMemberPlan(
            instrument_id=item.instrument_id,
            instrument_identifier_id=item.instrument_identifier_id,
            ordinal=ordinal,
        )
        for ordinal, item in enumerate(instruments, start=1)
    )
    manifest_slices: list[ArchiveManifestSlice] = []
    schedules: list[ProspectiveArchiveSliceSchedulePlan] = []
    for instrument in instruments:
        for window in windows:
            ordinal = len(manifest_slices) + 1
            slice_id = _id(f"{archive_id}:slice:{ordinal}")
            query_date = (
                resolved_sessions.decision.session_date
                if window.target_checkpoint_id
                == resolved_sessions.reference_checkpoint.target_checkpoint_id
                else resolved_sessions.outcome.session_date
            )
            query = BaoStockArchiveQuery(
                BaoStockArchiveQueryKind.HISTORY_5M_RAW,
                query_date,
                query_date,
                instrument.provider_code,
            )
            capture = CaptureRequest(
                provider_product_id=provider_product_id,
                capture_key=f"{archive_code}/{ordinal:04d}",
                resource=query.resource,
                request_headers_hash=ContentHash(_EMPTY_HEADERS_SHA256),
            )
            slice_plan = ArchiveSlicePlan(
                market_archive_slice_id=slice_id,
                ordinal=ordinal,
                scope_key=(
                    f"{window.slot.value.lower()}:{instrument.provider_code}:"
                    f"{query_date.isoformat()}"
                ),
                event_window_start=window.window_start,
                event_window_end=window.window_end,
                request_sha256=canonical_json_sha256(capture),
                expected_fact_kind="MARKET_BAR_5M",
            )
            manifest_slices.append(
                ArchiveManifestSlice(slice_plan, capture, window.slot.value)
            )
            schedules.append(
                ProspectiveArchiveSliceSchedulePlan(
                    market_archive_slice_id=slice_id,
                    instrument_id=instrument.instrument_id,
                    ordinal=ordinal,
                    slot=window.slot,
                    trading_session_id=window.session_id,
                    target_checkpoint_id=window.target_checkpoint_id,
                    comparison_ordinal=window.comparison_ordinal,
                )
            )
    generation_plan = ProspectiveArchiveGenerationPlan(
        market_archive_id=archive_id,
        series_code=series_code,
        generation=generation,
        predecessor_market_archive_id=predecessor_market_archive_id,
        exchange=exchange,
        target_definition_id=contract.target_definition_id,
        target_version=contract.version,
        target_definition_sha256=contract.content_sha256,
        reference_checkpoint_id=(
            resolved_sessions.reference_checkpoint.target_checkpoint_id
        ),
        outcome_checkpoint_id=resolved_sessions.outcome_checkpoint.target_checkpoint_id,
        decision_session_id=resolved_sessions.decision.session_id,
        outcome_session_id=resolved_sessions.outcome.session_id,
        later_verification_session_id=(
            resolved_sessions.later_verification.session_id
        ),
        members=member_plans,
        schedules=tuple(schedules),
        provenance_sha256=provenance_sha256,
    )
    plans = tuple(item.plan for item in manifest_slices)
    return ArchiveOperatorManifest(
        StartMarketArchiveRequest(
            market_archive_id=archive_id,
            archive_code=archive_code,
            lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS,
            provider_product_id=provider_product_id,
            exchange_code=exchange,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            instrument_scope=f"{exchange}_DETERMINISTIC_ENGINEERING_PILOT",
            instrument_scope_sha256=canonical_json_sha256(
                tuple(
                    (item.instrument_id, item.instrument_identifier_id, item.provider_code)
                    for item in instruments
                )
            ),
            event_window_start=min(item.event_window_start for item in plans),
            event_window_end=max(item.event_window_end for item in plans),
            reserved_free_bytes=reserved_free_bytes,
            maximum_archive_bytes=maximum_archive_bytes,
            maximum_slice_bytes=maximum_slice_bytes,
            code_artifact_id=code_artifact_id,
            config_artifact_id=config_artifact_id,
            provenance_sha256=provenance_sha256,
            slices=plans,
            prospective_generation=generation_plan,
        ),
        tuple(manifest_slices),
    )


def _id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"mra:prospective-archive:v1:{key}")


__all__ = [
    "ProspectiveArchiveInstrument",
    "build_target_aligned_prospective_manifest",
]
