"""Discover report work across Uses through existing publication/Runtime facts."""

from hashlib import sha256
import re
from typing import Any

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.research_qualification.ports.daily_prediction import DailyDeliveryWorkItem, DailyPublicationCursor
from market_regime_alpha.runtime.errors import ArtifactByteStoreError, ArtifactIntegrityError
from market_regime_alpha.shared.time import require_utc


_PUBLISHED_REPORTS = """
    FROM mra.runtime_run publication JOIN mra.runtime_schedule schedule USING(schedule_id)
    LEFT JOIN mra.runtime_run delivery ON delivery.parent_run_id=publication.run_id
      AND delivery.fire_key='daily-delivery:' || split_part(publication.fire_key, ':', 2) || ':' || %s
    LEFT JOIN mra.artifact artifact ON artifact.artifact_id=publication.config_artifact_id
      AND artifact.content_sha256=publication.config_hash
    WHERE schedule.schedule_code ~ '^daily-model-[0-9a-f]{32}$'
      AND publication.fire_key ~ '^daily:[0-9a-f-]{36}$'
      AND schedule.runtime_mode='SHADOW' AND publication.runtime_mode='SHADOW'
      AND publication.state='SUCCEEDED'
"""


def delivery_work_counts(pool: TargetPostgresPool, channel: str) -> dict[str, int]:
    _require_channel(channel)
    with pool.connection(read_only=True) as connection:
        rows = connection.execute("SELECT coalesce(delivery.state, 'NOT_REQUESTED'), count(*) "
                                  + _PUBLISHED_REPORTS + " GROUP BY delivery.state", (channel,)).fetchall()
    return {state: int(count) for state, count in rows}


def delivery_work_items(pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore, channel: str,
                        *, limit: int = 32, after: DailyPublicationCursor | None = None,
                        recent: bool = False) -> tuple[DailyDeliveryWorkItem, ...]:
    _require_channel(channel)
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError("daily delivery page size must be between 1 and 256")
    if after is not None:
        require_utc(after[0], field="delivery cursor requested_at")
    if type(recent) is not bool or (recent and after is not None):
        raise ValueError("recent delivery discovery has no history cursor")
    with pool.connection(read_only=True) as connection:
        rows = connection.execute("""SELECT publication.run_id, publication.requested_at, publication.code_sha,
            publication.config_hash, publication.schedule_id, schedule.schedule_code, publication.fire_key,
            artifact.content_sha256, artifact.size_bytes, coalesce(delivery.state, 'NOT_REQUESTED') """
            + _PUBLISHED_REPORTS + """
            AND (%s::timestamptz IS NULL OR (publication.requested_at,publication.run_id) > (%s::timestamptz,%s::uuid))
            """ + (" AND (delivery.state IS NULL OR delivery.state <> 'SUCCEEDED')" if recent else "")
            + (" ORDER BY publication.requested_at DESC,publication.run_id DESC" if recent else " ORDER BY publication.requested_at,publication.run_id")
            + " LIMIT %s", (channel, None if after is None else after[0], *(after or (None, None)), limit)).fetchall()
    if len({row[0] for row in rows}) != len(rows):
        raise ArtifactIntegrityError("daily delivery Runtime identity is ambiguous")
    result = []
    for row in rows:
        content, error = _content(byte_store, row[7], row[8])
        result.append(DailyDeliveryWorkItem(run_id=row[0], requested_at=row[1], code_sha=row[2],
            config_sha256=row[3], schedule_id=row[4], schedule_code=row[5], fire_key=row[6],
            plan_content=content, delivery_state=row[9], error_code=error))
    return tuple(result)


def _content(store: ResearchArtifactByteStore, digest: Any, size: Any) -> tuple[bytes | None, str | None]:
    if digest is None or size is None:
        return None, "FROZEN_PLAN_ARTIFACT_UNAVAILABLE"
    try:
        content = store.read_bytes(digest, expected_size=size)
        if sha256(content).hexdigest() != digest:
            raise ArtifactIntegrityError("frozen plan hash differs")
        return content, None
    except (OSError, ValueError, ArtifactByteStoreError, ArtifactIntegrityError):
        return None, "FROZEN_PLAN_BYTES_UNREADABLE"


def _require_channel(channel: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", channel):
        raise ValueError("daily delivery channel is invalid")
