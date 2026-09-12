"""Validate the exact frozen historical acquisition request without external I/O."""

from datetime import datetime
from uuid import UUID

from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind as Kind
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.ports.sources import DatasetRequestFailureContext
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def historical_request_failure(*, slice_id: UUID, slice_sha256: str, scope_key: str,
    window_start: datetime, window_end: datetime, product_id: UUID, capture_id: UUID,
    capture_key: str, slice_request_sha256: str, capture_request_sha256: str,
    instrument_id: UUID, identifier: str) -> DatasetRequestFailureContext:
    kind_text, _, code = scope_key.partition(":")
    try:
        kind = Kind(kind_text)
    except ValueError as exc:
        raise ArtifactIntegrityError("unsupported historical failure request kind") from exc
    if kind not in {Kind.HISTORY_DAILY_RAW, Kind.HISTORY_DAILY_BACK_ADJUSTED} or code != identifier:
        raise ArtifactIntegrityError("historical failure request instrument/kind mismatch")
    query = BaoStockArchiveQuery(kind, window_start.date(), window_end.date(), code)
    request = CaptureRequest(product_id, capture_key, query.resource,
        ContentHash(canonical_json_sha256({"headers":"NONE","query":query.resource})))
    digest = canonical_json_sha256(request)
    if digest != slice_request_sha256 or digest != capture_request_sha256:
        raise ArtifactIntegrityError("historical failure request hash differs from frozen Capture/Archive")
    return DatasetRequestFailureContext(slice_id,slice_sha256,capture_id,digest,instrument_id,
        "RAW_UNADJUSTED" if kind is Kind.HISTORY_DAILY_RAW else "BACKWARD_ADJUSTED",window_start,window_end)
