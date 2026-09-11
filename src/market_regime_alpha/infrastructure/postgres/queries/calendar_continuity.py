"""Read-only, byte-verified Provider calendar coverage; no weekday inference."""

from dataclasses import fields
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer, _session
from market_regime_alpha.infrastructure.providers.baostock_calendar_normalizer import BaoStockCalendarNormalizer, decode_calendar_response
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


def verify_calendar_coverage(row: dict[str, Any], sessions: list[dict[str, Any]], content: bytes, observed_at: datetime) -> dict[str, Any]:
    """Verify both legacy v2 and narrow v1 against their immutable owner receipts."""
    require_utc(observed_at, field="observed_at")
    if len(content) != row["size_bytes"] or sha256(content).hexdigest() != row["artifact_sha256"]:
        raise ArtifactIntegrityError("CALENDAR_ARTIFACT_BYTES_DIFFER")
    observation = decode_calendar_response(content)
    request = CaptureRequest(row["provider_product_id"], row["capture_key"], observation.query.resource, ContentHash(canonical_json_sha256({"headers": {}})))
    contracts = (BaoStockArchiveNormalizer.contract, BaoStockCalendarNormalizer.contract)
    matched = [contract for contract in contracts if canonical_json_sha256({"capture_id": row["capture_id"], "normalizer_contract": contract}) == row["normalization_request_hash"]]
    if (row["request_hash"] != canonical_json_sha256(request) or len(matched) != 1
            or row["receipt_status"] != "SUCCEEDED" or row["command_kind"] != "NORMALIZE_MARKET_PIT"
            or row["scope_id"] != str(row["capture_id"]) or row["result_aggregate_kind"] != "MARKET_NORMALIZATION"
            or row["result_aggregate_id"] != str(row["capture_id"]) or row["result_aggregate_version"] != 1
            or not row["capture_started_at"] <= row["capture_completed_at"] <= row["known_at"] <= row["normalized_at"] <= observed_at):
        raise ArtifactIntegrityError("CALENDAR_OWNER_RECEIPT_OR_TIME_DIFFERS")
    exchanges = ("XSHG", "XSHE") if matched[0] == BaoStockArchiveNormalizer.contract else ("XSHG",)
    expected = [_session(exchange, day, row["capture_id"]) for day in observation.open_dates for exchange in exchanges]
    if len(sessions) != len(expected) or len({item["session_id"] for item in sessions}) != len(sessions):
        raise ArtifactIntegrityError("CALENDAR_CANONICAL_ROSTER_DIFFERS")
    actual = {item["session_id"]: item for item in sessions}
    for item in expected:
        persisted = actual.get(item.session_id.value)
        if persisted is None or any(persisted[field.name] != getattr(item, field.name) for field in fields(item) if field.name not in {"source_capture_id", "session_id"}):
            raise ArtifactIntegrityError("CALENDAR_CANONICAL_SESSION_DIFFERS")
    roster = tuple({"reference_id": item["session_id"], "reference_kind": "TRADING_SESSION"} for item in sorted(sessions, key=lambda item: str(item["session_id"])))
    roster_hash = canonical_json_sha256(roster)
    if (row["reference_count"] != len(roster) or row["reference_roster_sha256"] != roster_hash
            or row["normalization_sha256"] != canonical_json_sha256({"capture_id": row["capture_id"],
                "normalization_receipt_id": row["normalization_receipt_id"], "reference_count": len(roster), "reference_roster_sha256": roster_hash})):
        raise ArtifactIntegrityError("CALENDAR_NORMALIZATION_HASH_DIFFERS")
    complete = not observation.missing_dates and row["source_gap_count"] == 0
    return {
        "state": "VERIFIED" if complete else "SOURCE_GAP",
        "reason_code": "COMPLETE_PROVIDER_CALENDAR" if complete else "CALENDAR_CIVIL_DATE_UNOBSERVED",
        "coverage_from": observation.query.start_date, "coverage_through": observation.query.end_date,
        "capture_id": row["capture_id"], "capture_key": row["capture_key"], "known_at": row["known_at"],
        "normalization_receipt_id": row["normalization_receipt_id"], "normalization_sha256": row["normalization_sha256"],
        "artifact_sha256": row["artifact_sha256"], "artifact_verified_at": observed_at,
        "normalizer": matched[0].implementation + ":" + matched[0].version,
        "session_ids": tuple(item["session_id"] for item in sorted(sessions, key=lambda item: item["session_date"]) if item["exchange"] == "XSHG"),
        "missing_civil_dates": observation.missing_dates, "source_gap_count": row["source_gap_count"],
        "provider_evidence_class": "EXPLORATORY", "business_writes": 0,
    }


class PostgresCalendarContinuityReads:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool = pool
        self._byte_store = byte_store

    def unresolved_work(self, provider_id: UUID) -> list[dict[str, Any]]:
        """Unknown effects and unresolved fences survive a civil-date boundary."""
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute("""SELECT run.run_id,run.state AS run_state,step.step_key,step.state AS step_state,
                    attempt.attempt_id,attempt.state AS attempt_state,attempt.fence_token,attempt.lease_until
                FROM mra.runtime_run run JOIN mra.runtime_schedule schedule USING(schedule_id)
                JOIN mra.runtime_step step USING(run_id)
                LEFT JOIN mra.runtime_attempt attempt ON attempt.attempt_id=step.current_attempt_id
                WHERE schedule.schedule_code=%s AND (run.state='WAITING' OR step.state='WAITING'
                    OR attempt.state IN ('CLAIMED','RUNNING','RECONCILIATION_REQUIRED')
                    OR (run.state IN ('QUEUED','RUNNING')
                        AND (run.requested_at AT TIME ZONE 'Asia/Shanghai')::date
                            < (statement_timestamp() AT TIME ZONE 'Asia/Shanghai')::date))
                ORDER BY run.requested_at,step.ordinal""", ("daily-calendar-collection-" + provider_id.hex,)).fetchall()

    def calendar_coverage(self, provider_id: UUID, observed_at: datetime) -> dict[str, Any]:
        require_utc(observed_at, field="observed_at")
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute("""
                SELECT capture.*, artifact.content_sha256 AS artifact_sha256, artifact.size_bytes,
                       normalization.normalization_receipt_id, normalization.reference_count,
                       normalization.reference_roster_sha256, normalization.content_sha256 AS normalization_sha256,
                       normalization.recorded_at AS normalized_at, receipt.request_hash AS normalization_request_hash,
                       receipt.status AS receipt_status, receipt.command_kind, receipt.scope_id,
                       receipt.result_aggregate_kind, receipt.result_aggregate_id, receipt.result_aggregate_version,
                       (SELECT count(*) FROM mra.source_gap gap WHERE gap.capture_id=capture.capture_id) AS source_gap_count
                FROM mra.data_capture capture
                LEFT JOIN mra.artifact artifact USING(artifact_id)
                LEFT JOIN mra.market_capture_reference_normalization normalization USING(capture_id)
                LEFT JOIN mra.command_receipt receipt ON receipt.receipt_id=normalization.normalization_receipt_id
                WHERE capture.provider_product_id=%s AND capture.capture_key LIKE 'calendar-continuity:%%'
                  AND capture.known_at<=%s AND capture.recorded_at<=%s
                ORDER BY capture.known_at DESC,capture.capture_id DESC LIMIT 1
            """, (provider_id, observed_at, observed_at)).fetchone()
            if row is None:
                return {"state": "UNAVAILABLE", "reason_code": "CALENDAR_CONTINUITY_CAPTURE_ABSENT", "business_writes": 0}
            if row["status"] != "CAPTURED" or row["normalization_receipt_id"] is None or row["normalized_at"] > observed_at:
                return {"state": "UNAVAILABLE", "reason_code": row["error_code"] or "CALENDAR_NORMALIZATION_PENDING", "capture_id": row["capture_id"], "business_writes": 0}
            sessions = cursor.execute("""SELECT session.* FROM mra.market_capture_trading_session_normalization binding
                JOIN mra.trading_session session USING(session_id) WHERE binding.capture_id=%s ORDER BY session.exchange,session.session_date""", (row["capture_id"],)).fetchall()
        content = self._byte_store.read_bytes(row["artifact_sha256"], expected_size=row["size_bytes"])
        return verify_calendar_coverage(row, sessions, content, observed_at)
