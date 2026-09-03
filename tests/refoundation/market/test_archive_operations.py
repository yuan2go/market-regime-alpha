from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from market_regime_alpha.market.application.archive_operations import (
    ArchiveSliceExecutionRequest,
    ArchiveSliceExecutionStatus,
    MarketArchiveOperations,
)
from market_regime_alpha.market.domain import ArchiveLane, CaptureStatus
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveCaptureDisposition,
    ArchiveSliceOperatingContract,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass
class _Capture:
    capture_id: UUID
    status: CaptureStatus


@dataclass
class _CaptureResult:
    capture: _Capture


class _Market:
    def __init__(self, status: CaptureStatus) -> None:
        self.status = status
        self.capture_calls = 0
        self.normalize_calls = 0
        self.capture_id = uuid4()

    def capture(self, request, provider, context, *, runtime_claim=None):
        self.capture_calls += 1
        return _CaptureResult(_Capture(self.capture_id, self.status))

    def normalize(self, capture_id, normalizer, context, *, runtime_claim=None):
        self.normalize_calls += 1
        return object()


class _Archives:
    def __init__(self) -> None:
        self.observations = 0
        self.gaps = 0
        self.resource_stops = 0

    def record_capture_observation(self, request, context, *, runtime_claim=None):
        self.observations += 1
        return object()

    def record_slice_gap(self, **kwargs):
        self.gaps += 1
        return object()

    def record_resource_stop(self, **kwargs):
        self.resource_stops += 1
        return object()


class _ReadPort:
    def __init__(self, contract: ArchiveSliceOperatingContract, gap_id: UUID | None = None) -> None:
        self.contract = contract
        self.gap_id = gap_id

    def load_slice_contract(self, market_archive_id, market_archive_slice_id):
        return self.contract

    def capture_disposition(self, capture_id):
        return ArchiveCaptureDisposition(
            capture_id=capture_id,
            status=CaptureStatus.PROVIDER_FAILURE,
            source_gap_ids=(self.gap_id,) if self.gap_id is not None else (),
        )


class _Resources:
    def __init__(self, free_bytes: int) -> None:
        self.free_bytes = free_bytes

    def available_bytes(self) -> int:
        return self.free_bytes


class _Clock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 9, 3, 8, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


def _context() -> CommandContext:
    return CommandContext(
        idempotency_key="wp17p-ops-test",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-test",
        reason_code="WP17P_ARCHIVE_TEST",
    )


def _request() -> tuple[ArchiveSliceExecutionRequest, ArchiveSliceOperatingContract]:
    archive_id = uuid4()
    slice_id = uuid4()
    capture = CaptureRequest(
        provider_product_id=uuid4(),
        capture_key="wp17p:ops:slice",
        resource="typed-resource",
        request_headers_hash="0" * 64,
    )
    execution = ArchiveSliceExecutionRequest(
        market_archive_id=archive_id,
        market_archive_slice_id=slice_id,
        capture_request=capture,
        schedule_slot="RETROSPECTIVE_BATCH",
    )
    contract = ArchiveSliceOperatingContract(
        market_archive_id=archive_id,
        market_archive_slice_id=slice_id,
        provider_product_id=capture.provider_product_id,
        request_sha256=canonical_json_sha256(capture),
        lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
        event_window_start=datetime(2026, 1, 5, tzinfo=UTC),
        event_window_end=datetime(2026, 1, 6, tzinfo=UTC),
        reserved_free_bytes=100,
        maximum_slice_bytes=50,
        terminal_status=None,
    )
    return execution, contract


def test_resource_preflight_stops_before_provider_io() -> None:
    request, contract = _request()
    market = _Market(CaptureStatus.CAPTURED)
    archives = _Archives()
    operations = MarketArchiveOperations(market, archives, _ReadPort(contract), _Resources(149), _Clock())

    result = operations.execute_slice(request, provider=object(), normalizer=object(), context=_context())

    assert result.status is ArchiveSliceExecutionStatus.RESOURCE_LIMIT
    assert market.capture_calls == 0
    assert archives.resource_stops == 1


def test_successful_slice_is_captured_normalized_then_observed() -> None:
    request, contract = _request()
    market = _Market(CaptureStatus.CAPTURED)
    archives = _Archives()
    operations = MarketArchiveOperations(market, archives, _ReadPort(contract), _Resources(150), _Clock())

    result = operations.execute_slice(request, provider=object(), normalizer=object(), context=_context())

    assert result.status is ArchiveSliceExecutionStatus.CAPTURED
    assert market.capture_calls == 1
    assert market.normalize_calls == 1
    assert archives.observations == 1


def test_prospective_slice_before_frozen_window_is_not_due_without_provider_io() -> None:
    request, base = _request()
    contract = ArchiveSliceOperatingContract(
        market_archive_id=base.market_archive_id,
        market_archive_slice_id=base.market_archive_slice_id,
        provider_product_id=base.provider_product_id,
        request_sha256=base.request_sha256,
        lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS,
        event_window_start=datetime(2026, 9, 3, 8, 1, tzinfo=UTC),
        event_window_end=datetime(2026, 9, 3, 8, 2, tzinfo=UTC),
        reserved_free_bytes=base.reserved_free_bytes,
        maximum_slice_bytes=base.maximum_slice_bytes,
        terminal_status=None,
    )
    market = _Market(CaptureStatus.CAPTURED)
    archives = _Archives()
    operations = MarketArchiveOperations(
        market,
        archives,
        _ReadPort(contract),
        _Resources(150),
        _Clock(datetime(2026, 9, 3, 8, tzinfo=UTC)),
    )

    result = operations.execute_slice(
        request, provider=object(), normalizer=object(), context=_context()
    )

    assert result.status is ArchiveSliceExecutionStatus.NOT_DUE
    assert market.capture_calls == 0
    assert market.normalize_calls == 0
    assert archives.observations == 0
    assert archives.gaps == 0
    assert archives.resource_stops == 0


def test_provider_failure_binds_the_exact_capture_gap_without_normalization() -> None:
    request, contract = _request()
    gap_id = uuid4()
    market = _Market(CaptureStatus.PROVIDER_FAILURE)
    archives = _Archives()
    operations = MarketArchiveOperations(market, archives, _ReadPort(contract, gap_id), _Resources(150), _Clock())

    result = operations.execute_slice(request, provider=object(), normalizer=object(), context=_context())

    assert result.status is ArchiveSliceExecutionStatus.GAP_RECORDED
    assert result.source_gap_id == gap_id
    assert market.normalize_calls == 0
    assert archives.gaps == 1


def test_changed_capture_request_fails_before_provider_io() -> None:
    request, contract = _request()
    changed = ArchiveSliceExecutionRequest(
        market_archive_id=request.market_archive_id,
        market_archive_slice_id=request.market_archive_slice_id,
        capture_request=CaptureRequest(
            provider_product_id=request.capture_request.provider_product_id,
            capture_key=request.capture_request.capture_key,
            resource="changed-resource",
            request_headers_hash=request.capture_request.request_headers_hash,
        ),
        schedule_slot=request.schedule_slot,
    )
    market = _Market(CaptureStatus.CAPTURED)
    operations = MarketArchiveOperations(market, _Archives(), _ReadPort(contract), _Resources(150), _Clock())

    try:
        operations.execute_slice(changed, provider=object(), normalizer=object(), context=_context())
    except ValueError as error:
        assert "frozen slice request" in str(error)
    else:
        raise AssertionError("changed request must fail closed")
    assert market.capture_calls == 0
