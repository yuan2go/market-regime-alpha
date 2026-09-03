"""Research-owned narrow reads over canonical Selection and Market facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain import (
    DatasetSource,
    DatasetSourceRole,
)
from market_regime_alpha.research_qualification.ports.sources import (
    DatasetMarketSourceObservation,
    DatasetPopulationMember,
)
from market_regime_alpha.runtime.errors import (
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.time import DecisionTime


_MARKET_ROLES = frozenset(
    {
        DatasetSourceRole.MARKET_BAR_REVISION,
        DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION,
        DatasetSourceRole.MARKET_TRADING_SESSION,
        DatasetSourceRole.MARKET_SOURCE_GAP,
        DatasetSourceRole.MARKET_CAPTURE,
    }
)


class PostgresResearchSourceQueries:
    """Resolve exact source identities inside the caller-owned Research UoW."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def expected_population(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        decision_time: DecisionTime,
        lock: bool,
        exploratory_scope=None,
    ) -> tuple[DatasetPopulationMember, ...]:
        lock_scope = " FOR SHARE OF revision, policy" if lock else ""
        scope = self._connection.execute(
            """
            SELECT revision.universe_revision_id
            FROM mra.universe_revision AS revision
            CROSS JOIN mra.eligibility_policy AS policy
            WHERE revision.universe_revision_id = %s
              AND revision.decision_time = %s
              AND policy.eligibility_policy_id = %s
            """
            + lock_scope,
            (
                universe_revision_id,
                decision_time.value,
                eligibility_policy_id,
            ),
        ).fetchone()
        if scope is None:
            raise RuntimeNotFoundError(
                "Dataset Selection scope does not exist at the exact DecisionTime"
            )
        retrospective = self._connection.execute(
            """
            SELECT universe.market_archive_id,
                   universe.market_archive_seal_id,
                   universe.knowledge_cutoff,
                   universe.simulated_event_cutoff,
                   universe.scope_content_sha256,
                   eligibility.market_archive_id,
                   eligibility.market_archive_seal_id,
                   eligibility.knowledge_cutoff,
                   eligibility.simulated_event_cutoff,
                   eligibility.scope_content_sha256
            FROM mra.exploratory_retrospective_universe_revision AS universe
            JOIN mra.exploratory_retrospective_eligibility_batch AS eligibility
              ON eligibility.universe_revision_id = universe.universe_revision_id
            WHERE universe.universe_revision_id = %s
              AND eligibility.eligibility_policy_id = %s
            """
            + (" FOR SHARE OF universe, eligibility" if lock else ""),
            (universe_revision_id, eligibility_policy_id),
        ).fetchone()
        if exploratory_scope is None:
            if retrospective is not None:
                raise RuntimeStateConflictError(
                    "retrospective Selection population requires an exploratory Dataset scope"
                )
        else:
            expected = (
                exploratory_scope.market_archive_id,
                exploratory_scope.market_archive_seal_id,
                exploratory_scope.knowledge_cutoff,
                exploratory_scope.simulated_event_cutoff,
                str(exploratory_scope.content_sha256),
            )
            if retrospective is not None and (
                tuple(retrospective[:5]) != expected
                or tuple(retrospective[5:]) != expected
            ):
                raise RuntimeStateConflictError(
                    "exploratory Dataset requires the exact retrospective Selection scope"
                )
        lock_rows = " FOR SHARE OF member, assessment" if lock else ""
        rows = self._connection.execute(
            """
            SELECT member.instrument_id, member.universe_member_id,
                   assessment.eligibility_assessment_id
            FROM mra.universe_member AS member
            JOIN mra.eligibility_assessment AS assessment
              ON assessment.universe_member_id = member.universe_member_id
             AND assessment.universe_revision_id = member.universe_revision_id
             AND assessment.instrument_id = member.instrument_id
            WHERE member.universe_revision_id = %s
              AND member.membership_status = 'INCLUDED'
              AND assessment.eligibility_policy_id = %s
              AND assessment.decision_time = %s
              AND assessment.result = 'ELIGIBLE'
            ORDER BY member.instrument_id
            """
            + lock_rows,
            (
                universe_revision_id,
                eligibility_policy_id,
                decision_time.value,
            ),
        ).fetchall()
        return tuple(
            DatasetPopulationMember(
                instrument_id=UUID(str(row[0])),
                universe_member_id=UUID(str(row[1])),
                eligibility_assessment_id=UUID(str(row[2])),
            )
            for row in rows
        )

    def market_source_observations(
        self,
        sources: tuple[DatasetSource, ...],
        *,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]:
        by_role: dict[DatasetSourceRole, list[DatasetSource]] = defaultdict(list)
        for source in sources:
            if source.role in _MARKET_ROLES:
                by_role[source.role].append(source)
        observations: list[DatasetMarketSourceObservation] = []
        for role, role_sources in by_role.items():
            observations.extend(
                self._market_role_observations(
                    role,
                    tuple(role_sources),
                    lock=lock,
                )
            )
        expected_ids = {
            source.dataset_source_id
            for source in sources
            if source.role in _MARKET_ROLES
        }
        if {item.dataset_source_id for item in observations} != expected_ids:
            raise RuntimeNotFoundError(
                "one or more Dataset Market source identities do not exist"
            )
        return tuple(sorted(observations, key=lambda item: str(item.dataset_source_id)))

    def _market_role_observations(
        self,
        role: DatasetSourceRole,
        sources: tuple[DatasetSource, ...],
        *,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]:
        identity_attribute, sql, lock_clause = {
            DatasetSourceRole.MARKET_BAR_REVISION: (
                "market_bar_revision_id",
                """
                SELECT fact.bar_revision_id, fact.instrument_id,
                       fact.decision_visible_at,
                       mra.artifact_has_verified_integrity(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.market_bar_revision AS fact
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE fact.bar_revision_id = ANY(%s)
                """,
                " FOR SHARE OF fact, capture",
            ),
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: (
                "market_instrument_fact_revision_id",
                """
                SELECT fact.fact_revision_id, fact.instrument_id,
                       fact.decision_visible_at,
                       mra.artifact_has_verified_integrity(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.instrument_fact_revision AS fact
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE fact.fact_revision_id = ANY(%s)
                """,
                " FOR SHARE OF fact, capture",
            ),
            DatasetSourceRole.MARKET_TRADING_SESSION: (
                "market_trading_session_id",
                """
                SELECT session.session_id, NULL::uuid,
                       session.decision_visible_at,
                       mra.artifact_has_verified_integrity(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.trading_session AS session
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = session.source_capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE session.session_id = ANY(%s)
                """,
                " FOR SHARE OF session, capture",
            ),
            DatasetSourceRole.MARKET_SOURCE_GAP: (
                "market_source_gap_id",
                """
                SELECT gap.gap_id, gap.instrument_id,
                       gap.decision_visible_at,
                       CASE
                           WHEN capture.status = 'PROVIDER_FAILURE' THEN true
                           ELSE mra.artifact_has_verified_integrity(
                               artifact.integrity_state,
                               artifact.last_verified_at
                           )
                       END
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.gap_id = ANY(%s)
                """,
                " FOR SHARE OF gap, capture",
            ),
            DatasetSourceRole.MARKET_CAPTURE: (
                "market_capture_id",
                """
                SELECT capture.capture_id, NULL::uuid,
                       capture.decision_visible_at,
                       CASE
                           WHEN capture.status = 'PROVIDER_FAILURE' THEN true
                           ELSE mra.artifact_has_verified_integrity(
                               artifact.integrity_state,
                               artifact.last_verified_at
                           )
                       END
                FROM mra.data_capture AS capture
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE capture.capture_id = ANY(%s)
                """,
                " FOR SHARE OF capture",
            ),
        }[role]
        source_by_identity: dict[UUID, DatasetSource] = {}
        for source in sources:
            identity = getattr(source, identity_attribute)
            if identity is None:
                raise AssertionError("Dataset source lost its role-specific identity")
            if identity in source_by_identity:
                raise RuntimeStateConflictError(
                    "Dataset Market source identities must be unique per role"
                )
            source_by_identity[identity] = source
        rows = self._connection.execute(
            sql + (lock_clause if lock else ""),
            (list(source_by_identity),),
        ).fetchall()
        return tuple(
            DatasetMarketSourceObservation(
                dataset_source_id=source_by_identity[UUID(str(row[0]))].dataset_source_id,
                role=role,
                source_identity=UUID(str(row[0])),
                instrument_id=UUID(str(row[1])) if row[1] is not None else None,
                decision_visible_at=row[2],
                foundation_integrity=row[3] is True,
            )
            for row in rows
        )

    def formal_market_source_observations(
        self,
        sources: tuple[DatasetSource, ...],
        *,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]:
        if not self._connection.execute(
            """
            SELECT 1 FROM mra.formal_research_campaign AS campaign
            JOIN mra.formal_research_campaign_provider_decision AS binding
              ON binding.formal_research_campaign_id = campaign.formal_research_campaign_id
            WHERE campaign.formal_research_campaign_id = %s
              AND campaign.campaign_class = 'FORMAL_RESEARCH'
              AND binding.provider_qualification_decision_id = %s
            """ + (" FOR SHARE OF campaign, binding" if lock else ""),
            (formal_research_campaign_id, provider_qualification_decision_id),
        ).fetchone():
            raise RuntimeStateConflictError(
                "Formal Dataset campaign Provider binding is not eligible"
            )
        by_role: dict[DatasetSourceRole, list[DatasetSource]] = defaultdict(list)
        for source in sources:
            if source.role in _MARKET_ROLES:
                by_role[source.role].append(source)
        observations: list[DatasetMarketSourceObservation] = []
        mapping = {
            DatasetSourceRole.MARKET_BAR_REVISION: (
                "market_bar_revision_id", "qualified_market_bar_visibility",
                "bar_revision_id", "market_bar_revision", "bar_revision_id",
                "instrument_id",
            ),
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: (
                "market_instrument_fact_revision_id",
                "qualified_instrument_fact_visibility", "fact_revision_id",
                "instrument_fact_revision", "fact_revision_id", "instrument_id",
            ),
            DatasetSourceRole.MARKET_TRADING_SESSION: (
                "market_trading_session_id", "qualified_trading_session_visibility",
                "session_id", "trading_session", "session_id", None,
            ),
            DatasetSourceRole.MARKET_SOURCE_GAP: (
                "market_source_gap_id", "qualified_source_gap_visibility",
                "gap_id", "source_gap", "gap_id", "instrument_id",
            ),
        }
        for role, role_sources in by_role.items():
            if role is DatasetSourceRole.MARKET_CAPTURE:
                capture_source_by_id: dict[UUID, DatasetSource] = {}
                for source in role_sources:
                    identity = source.market_capture_id
                    if identity is None or identity in capture_source_by_id:
                        raise RuntimeStateConflictError(
                            "Formal Dataset Capture identities must be exact and unique"
                        )
                    capture_source_by_id[identity] = source
                rows = self._connection.execute(
                    """
                    SELECT member.capture_id, member.source_available_at
                    FROM mra.provider_qualification_capture_member AS member
                    WHERE member.provider_qualification_decision_id = %s
                      AND member.capture_id = ANY(%s::uuid[])
                      AND member.artifact_verified AND member.runtime_capture_lineage
                    """ + (" FOR SHARE OF member" if lock else ""),
                    (provider_qualification_decision_id, list(capture_source_by_id)),
                ).fetchall()
                observations.extend(
                    DatasetMarketSourceObservation(
                        dataset_source_id=capture_source_by_id[
                            UUID(str(row[0]))
                        ].dataset_source_id,
                        role=role, source_identity=UUID(str(row[0])),
                        instrument_id=None, decision_visible_at=row[1],
                        foundation_integrity=True,
                    )
                    for row in rows if row[1] is not None
                )
                continue
            target = mapping.get(role)
            if target is None:
                continue
            attribute, visibility_table, visibility_identity, source_table, source_identity, instrument_column = target
            source_by_id: dict[UUID, DatasetSource] = {}
            for source in role_sources:
                identity = getattr(source, attribute)
                if identity is None or identity in source_by_id:
                    raise RuntimeStateConflictError(
                        "Formal Dataset source identities must be exact and unique"
                    )
                source_by_id[identity] = source
            instrument_select = (
                f"source.{instrument_column}" if instrument_column else "NULL::uuid"
            )
            rows = self._connection.execute(
                f"""
                SELECT visibility.{visibility_identity}, {instrument_select},
                       visibility.qualified_decision_visible_at
                FROM mra.{visibility_table} AS visibility
                JOIN mra.{source_table} AS source
                  ON source.{source_identity} = visibility.{visibility_identity}
                WHERE visibility.provider_qualification_decision_id = %s
                  AND visibility.{visibility_identity} = ANY(%s::uuid[])
                """ + (" FOR SHARE OF visibility, source" if lock else ""),  # noqa: S608 -- closed mapping
                (provider_qualification_decision_id, list(source_by_id)),
            ).fetchall()
            observations.extend(
                DatasetMarketSourceObservation(
                    dataset_source_id=source_by_id[UUID(str(row[0]))].dataset_source_id,
                    role=role, source_identity=UUID(str(row[0])),
                    instrument_id=(UUID(str(row[1])) if row[1] is not None else None),
                    decision_visible_at=row[2], foundation_integrity=True,
                )
                for row in rows
            )
        expected = {
            source.dataset_source_id for source in sources if source.role in _MARKET_ROLES
        }
        if {item.dataset_source_id for item in observations} != expected:
            raise RuntimeNotFoundError(
                "one or more Formal Dataset sources lack qualified visibility"
            )
        return tuple(sorted(observations, key=lambda item: str(item.dataset_source_id)))

    def exploratory_market_source_observations(
        self,
        sources: tuple[DatasetSource, ...],
        *,
        market_archive_id: UUID,
        market_archive_seal_id: UUID,
        knowledge_cutoff: datetime,
        simulated_event_cutoff: datetime,
        lock: bool,
    ) -> tuple[DatasetMarketSourceObservation, ...]:
        scope = self._connection.execute(
            """
            SELECT seal.knowledge_cutoff
            FROM mra.market_archive AS archive
            JOIN mra.market_archive_seal AS seal
              ON seal.market_archive_id = archive.market_archive_id
            WHERE archive.market_archive_id = %s
              AND seal.market_archive_seal_id = %s
              AND archive.lane = 'RETROSPECTIVE_BACKFILL'
              AND archive.evidence_class = 'EXPLORATORY_RETROSPECTIVE'
              AND seal.knowledge_cutoff = %s
            """
            + (" FOR SHARE OF archive, seal" if lock else ""),
            (market_archive_id, market_archive_seal_id, knowledge_cutoff),
        ).fetchone()
        if scope is None or simulated_event_cutoff >= knowledge_cutoff:
            raise RuntimeStateConflictError("Exploratory Dataset archive dual-clock scope is invalid")
        observations = self.market_source_observations(sources, lock=lock)
        source_by_role_and_identity = {
            (item.role, item.source_identity): item for item in observations
        }
        enriched: list[DatasetMarketSourceObservation] = []
        by_role: dict[DatasetSourceRole, list[UUID]] = defaultdict(list)
        for item in observations:
            by_role[item.role].append(item.source_identity)
        if by_role.get(DatasetSourceRole.MARKET_CAPTURE):
            raise RuntimeStateConflictError(
                "Exploratory Dataset cannot use a Capture without an event-time fact identity"
            )
        mapping = {
            DatasetSourceRole.MARKET_BAR_REVISION: (
                "market_bar_revision",
                "bar_revision_id",
                "capture_id",
                "source.event_end",
            ),
            DatasetSourceRole.MARKET_INSTRUMENT_FACT_REVISION: (
                "instrument_fact_revision",
                "fact_revision_id",
                "capture_id",
                "source.event_start",
            ),
            DatasetSourceRole.MARKET_TRADING_SESSION: (
                "trading_session",
                "session_id",
                "source_capture_id",
                "source.decision_reference_at",
            ),
            DatasetSourceRole.MARKET_SOURCE_GAP: (
                "source_gap",
                "gap_id",
                "capture_id",
                "coalesce(source.event_end, source.effective_from, source.event_start)",
            ),
        }
        for role, identities in by_role.items():
            target = mapping.get(role)
            if target is None:
                continue
            table, identity_column, capture_column, event_expression = target
            rows = self._connection.execute(
                f"""
                SELECT source.{identity_column}, {event_expression},
                       EXISTS (
                           SELECT 1
                           FROM mra.market_archive_capture_observation AS observation
                           WHERE observation.market_archive_id = %s
                             AND observation.capture_id = source.{capture_column}
                             AND observation.known_at <= %s
                       ) OR (
                           %s = 'MARKET_TRADING_SESSION'
                           AND EXISTS (
                               SELECT 1
                               FROM mra.market_capture_trading_session_normalization AS normalization
                               JOIN mra.market_archive_capture_observation AS observation
                                 ON observation.capture_id = normalization.capture_id
                                AND observation.market_archive_id = %s
                                AND observation.known_at <= %s
                               WHERE normalization.session_id = source.{identity_column}
                           )
                       ) OR (
                           %s = 'MARKET_SOURCE_GAP'
                           AND EXISTS (
                               SELECT 1
                               FROM mra.market_archive_slice_gap AS gap_binding
                               WHERE gap_binding.market_archive_id = %s
                                 AND gap_binding.gap_id = source.{identity_column}
                           )
                       ) AS archive_bound
                FROM mra.{table} AS source
                WHERE source.{identity_column} = ANY(%s::uuid[])
                """,  # noqa: S608 -- every identifier comes from the closed mapping above
                (
                    market_archive_id,
                    knowledge_cutoff,
                    role.value,
                    market_archive_id,
                    knowledge_cutoff,
                    role.value,
                    market_archive_id,
                    identities,
                ),
            ).fetchall()
            for row in rows:
                identity = UUID(str(row[0]))
                prior = source_by_role_and_identity[(role, identity)]
                event_cutoff_at = row[1]
                if row[2] is not True or event_cutoff_at is None:
                    raise RuntimeStateConflictError(
                        "Exploratory Dataset source is not bound to the exact archive or has no event cutoff"
                    )
                enriched.append(
                    DatasetMarketSourceObservation(
                        dataset_source_id=prior.dataset_source_id,
                        role=prior.role,
                        source_identity=prior.source_identity,
                        instrument_id=prior.instrument_id,
                        decision_visible_at=prior.decision_visible_at,
                        foundation_integrity=prior.foundation_integrity,
                        event_cutoff_at=event_cutoff_at,
                    )
                )
        if {item.dataset_source_id for item in enriched} != {
            item.dataset_source_id for item in observations
        }:
            raise RuntimeNotFoundError("Exploratory Dataset archive source roster is incomplete")
        return tuple(sorted(enriched, key=lambda item: str(item.dataset_source_id)))


__all__ = ["PostgresResearchSourceQueries"]
