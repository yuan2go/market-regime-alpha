"""Narrow campaign-bound Formal PIT resolver; never exposes current/latest."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.formal_pit import (
    FormalPitSource,
    FormalPitSourceKind,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError


class PostgresFormalPitSourceReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def resolve_exact(
        self,
        *,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
        source_kind: FormalPitSourceKind,
        source_identity: UUID,
        requested_decision_time: datetime,
    ) -> FormalPitSource:
        mapping = {
            FormalPitSourceKind.MARKET_BAR_REVISION: (
                "qualified_market_bar_visibility", "bar_revision_id"
            ),
            FormalPitSourceKind.INSTRUMENT_FACT_REVISION: (
                "qualified_instrument_fact_visibility", "fact_revision_id"
            ),
            FormalPitSourceKind.CLASSIFICATION_MEMBERSHIP_REVISION: (
                "qualified_classification_membership_visibility",
                "membership_revision_id",
            ),
            FormalPitSourceKind.TRADING_SESSION: (
                "qualified_trading_session_visibility", "session_id"
            ),
            FormalPitSourceKind.SOURCE_GAP: (
                "qualified_source_gap_visibility", "gap_id"
            ),
        }
        table, identity_column = mapping[source_kind]
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT visibility.{identity_column}, visibility.capture_id,
                       visibility.source_content_sha256,
                       visibility.source_available_at,
                       visibility.qualified_decision_visible_at,
                       visibility.content_sha256
                FROM mra.formal_research_campaign AS campaign
                JOIN mra.formal_research_campaign_provider_decision AS binding
                  ON binding.formal_research_campaign_id = campaign.formal_research_campaign_id
                JOIN mra.{table} AS visibility
                  ON visibility.provider_qualification_decision_id =
                     binding.provider_qualification_decision_id
                WHERE campaign.formal_research_campaign_id = %s
                  AND campaign.campaign_class = 'FORMAL_RESEARCH'
                  AND binding.provider_qualification_decision_id = %s
                  AND visibility.{identity_column} = %s
                  AND visibility.qualified_decision_visible_at <= %s
                """,  # noqa: S608 -- closed source-specific mapping above
                (
                    formal_research_campaign_id,
                    provider_qualification_decision_id,
                    source_identity,
                    requested_decision_time,
                ),
            ).fetchall()
        if len(rows) != 1:
            raise RuntimeStateConflictError(
                "Formal PIT source is missing, ambiguous, unbound, or not visible"
            )
        row = rows[0]
        return FormalPitSource(
            formal_research_campaign_id=formal_research_campaign_id,
            provider_qualification_decision_id=provider_qualification_decision_id,
            source_kind=source_kind,
            source_identity=UUID(str(row[0])),
            capture_id=UUID(str(row[1])),
            source_content_sha256=str(row[2]),
            source_available_at=row[3],
            qualified_decision_visible_at=row[4],
            visibility_content_sha256=str(row[5]),
        )


__all__ = ["PostgresFormalPitSourceReadPort"]
