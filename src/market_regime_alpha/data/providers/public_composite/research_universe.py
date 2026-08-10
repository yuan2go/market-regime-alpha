"""BaoStock full Security Master acquisition for exploratory Research Universe."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
import json
import socket
from typing import Any, Callable

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
    AcquiredSourcePayload,
    PublicCompositeProviderResult,
    RawSourceRequestMetadata,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    source_archive_id,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    baostock_credentials,
)
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    FreeResearchUniverseSnapshot,
    build_free_research_universe_snapshot,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class FreeResearchUniverseAcquisition:
    provider_result: PublicCompositeProviderResult
    source_manifest: SourceManifest
    snapshot: FreeResearchUniverseSnapshot


class BaoStockResearchUniverseClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Research Universe timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self._clock = clock

    def acquire(self, *, as_of_date: date) -> FreeResearchUniverseAcquisition:
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            requested_at = self._clock()
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                response = _consume_result(bs.query_stock_basic())
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
            if response["error_code"] != "0" or not response["rows"]:
                raise AShareDataError(
                    "BaoStock full Security Master query returned no usable rows"
                )
            retrieved_at = self._clock()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if requested_at.tzinfo is None or retrieved_at.tzinfo is None:
            raise ValueError("Research Universe client clock must be timezone-aware")
        raw = json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        decision_time = DecisionTime(retrieved_at)
        source = AcquiredSourcePayload(
            provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
            product="query_stock_basic:all:v1",
            locator=f"baostock://query-stock-basic/all/{as_of_date.isoformat()}",
            raw_payload=raw,
            retrieved_time=RetrievedAt(retrieved_at),
            limitations=(
                "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES",
                "CURRENT_RETRIEVAL_TIME_ONLY",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "PUBLIC_DATA_EXPLORATORY_ONLY",
            ),
            request_metadata=RawSourceRequestMetadata(
                provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
                endpoint="query_stock_basic",
                request_parameters=(("scope", "ALL_SECURITIES"),),
                requested_at=requested_at,
                provider_timestamp=None,
                event_time=None,
                available_at=retrieved_at,
                decision_time=retrieved_at,
                http_status=None,
                content_type="application/json",
                response_size=len(raw),
                encoding="utf-8",
                symbol_scope=("ALL_SECURITIES",),
                field_scope=tuple(sorted(str(item) for item in response["fields"])),
            ),
        )
        provider_result = PublicCompositeProviderResult(
            profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
            decision_time=decision_time,
            raw_payloads=(source,),
            bars=(),
            quotes=(),
            source_conflicts=(),
            limitations=(
                "FREE_DATA_EXPLORATORY",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "NO_PROVIDER_FALLBACK",
                "SECURITY_MASTER_CURRENT_RETRIEVAL_ONLY",
            ),
        )
        manifest = SourceManifest(
            provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
            decision_time=decision_time,
            source_artifacts=provider_result.source_artifact_references,
            fields=(),
            source_conflicts=(),
            limitations=provider_result.limitations,
            data_eligibility=DataEligibility.EXPLORATORY,
        )
        archive_id = source_archive_id(
            provider_result=provider_result,
            source_manifest=manifest,
        )
        rows = _normalize_security_master_rows(
            fields=tuple(str(item) for item in response["fields"]),
            rows=tuple(tuple(str(item) for item in row) for row in response["rows"]),
        )
        snapshot = build_free_research_universe_snapshot(
            as_of_date=as_of_date,
            known_at=retrieved_at,
            provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
            provider_contract="baostock-query-stock-basic-all/v1",
            source_manifest_reference=ValidationArtifactReference(
                "SOURCE_MANIFEST",
                manifest.source_manifest_id,
                manifest.content_hash,
            ),
            raw_archive_id=archive_id,
            evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
            rows=rows,
        )
        return FreeResearchUniverseAcquisition(provider_result, manifest, snapshot)


def _consume_result(result: Any) -> dict[str, Any]:
    fields = [str(item) for item in getattr(result, "fields", ())]
    rows: list[list[str]] = []
    if getattr(result, "error_code", "0") == "0":
        while result.next():
            rows.append([str(item) for item in result.get_row_data()])
    return {
        "error_code": str(getattr(result, "error_code", "UNKNOWN")),
        "error_message": str(getattr(result, "error_msg", "")),
        "fields": fields,
        "rows": rows,
    }


def _normalize_security_master_rows(
    *,
    fields: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> tuple[dict[str, Any], ...]:
    if not fields or len(fields) != len(set(fields)) or "code" not in fields:
        raise AShareDataError("BaoStock Security Master fields are unusable")
    normalized: list[dict[str, Any]] = []
    code_index = fields.index("code")
    for index, row in enumerate(rows):
        if code_index >= len(row) or not row[code_index].strip():
            raise AShareDataError(
                "BaoStock malformed Security Master row has no security code: "
                f"row {index}"
            )
        malformed = len(row) != len(fields)
        values = {
            field: (row[field_index] if field_index < len(row) else "")
            for field_index, field in enumerate(fields)
        }
        if malformed:
            values["_provider_row_malformed"] = True
            values["_provider_row_field_count"] = len(row)
        normalized.append(values)
    return tuple(normalized)


__all__ = [
    "BaoStockResearchUniverseClient",
    "FreeResearchUniverseAcquisition",
]
