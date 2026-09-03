"""Selection-owned narrow SQL queries over canonical Market/PIT facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from market_regime_alpha.market.domain import MembershipStatus
from market_regime_alpha.selection.domain import (
    CriterionEvidence,
    EligibilityRule,
    EligibilityRuleKind,
    ExploratoryRetrospectiveSelectionScope,
    MarketEvidenceStatus,
    MarketLineage,
    MembershipEvidence,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime


class PostgresSelectionMarketQueries:
    """Read Market rows in the caller-owned Selection transaction."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def membership_as_of(
        self,
        *,
        scope: UniverseScopeSpecification,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
    ) -> MembershipEvidence:
        return self._membership_as_of(
            scope=scope,
            instrument_id=instrument_id,
            decision_time=decision_time,
            visibility_cutoff=decision_time.value,
        )

    def membership_for_exploratory_retrospective(
        self,
        *,
        scope: UniverseScopeSpecification,
        instrument_id: InstrumentId,
        retrospective: ExploratoryRetrospectiveSelectionScope,
    ) -> MembershipEvidence:
        self._require_retrospective_archive(retrospective)
        evidence = self._membership_as_of(
            scope=scope,
            instrument_id=instrument_id,
            decision_time=DecisionTime(retrospective.simulated_event_cutoff),
            visibility_cutoff=retrospective.knowledge_cutoff,
        )
        self._require_archive_lineage(evidence.lineage, retrospective)
        return evidence

    def _membership_as_of(
        self,
        *,
        scope: UniverseScopeSpecification,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
        visibility_cutoff: datetime,
    ) -> MembershipEvidence:
        classification = self._connection.execute(
            """
            SELECT classification.classification_id,
                   classification.source_capture_id,
                   classification.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.classification AS classification
            JOIN mra.data_capture AS capture
              ON capture.capture_id = classification.source_capture_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            WHERE classification.classification_scheme = %s
              AND classification.classification_code = %s
              AND capture.provider_product_id = %s
              AND classification.effective_from <= %s
              AND (
                  classification.effective_to IS NULL
                  OR classification.effective_to > %s
              )
              AND classification.decision_visible_at <= %s
              AND capture.status = 'CAPTURED'
            ORDER BY classification.effective_from DESC,
                     classification.decision_visible_at DESC,
                     classification.revision DESC,
                     classification.classification_id DESC
            LIMIT 1
            """,
            (
                scope.classification_scheme,
                scope.classification_code,
                scope.market_provider_product_id,
                decision_time.value,
                decision_time.value,
                visibility_cutoff,
            ),
        ).fetchone()
        classification_gap = self._classification_gap(
            scope=scope,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
        )
        if classification_gap is not None and (classification is None or classification_gap[3] >= classification[2]):
            gap_id = UUID(str(classification_gap[0]))
            capture_id = UUID(str(classification_gap[1]))
            return MembershipEvidence(
                status=(
                    MarketEvidenceStatus.STALE
                    if classification_gap[4] is not True
                    else MarketEvidenceStatus.CONFLICT
                    if str(classification_gap[2]) == "CONFLICT"
                    else MarketEvidenceStatus.GAP
                ),
                membership_status=None,
                classification_id=(UUID(str(classification[0])) if classification is not None else None),
                membership_revision_id=None,
                gap_id=gap_id,
                capture_id=capture_id,
                decision_visible_at=classification_gap[3],
                lineage=MarketLineage(gap_ids=(gap_id,), capture_ids=(capture_id,)),
            )
        if classification is None:
            return MembershipEvidence(
                status=MarketEvidenceStatus.MISSING,
                membership_status=None,
                classification_id=None,
                membership_revision_id=None,
                gap_id=None,
                capture_id=None,
                decision_visible_at=None,
                lineage=MarketLineage(),
            )
        classification_id = UUID(str(classification[0]))
        classification_capture_id = UUID(str(classification[1]))
        classification_lineage = MarketLineage(
            capture_ids=(classification_capture_id,),
        )
        if classification[3] is not True:
            return MembershipEvidence(
                status=MarketEvidenceStatus.STALE,
                membership_status=None,
                classification_id=classification_id,
                membership_revision_id=None,
                gap_id=None,
                capture_id=classification_capture_id,
                decision_visible_at=classification[2],
                lineage=classification_lineage,
            )
        member = self._connection.execute(
            """
            SELECT membership.membership_revision_id,
                   membership.classification_id,
                   membership.source_capture_id,
                   membership.membership_status,
                   membership.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ),
                   mra.market_artifact_is_readable(
                       instrument_artifact.integrity_state,
                       instrument_artifact.last_verified_at
                   )
            FROM mra.classification_membership_revision AS membership
            JOIN mra.classification AS classification
              ON classification.classification_id = membership.classification_id
            JOIN mra.data_capture AS capture
              ON capture.capture_id = membership.source_capture_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            JOIN mra.instrument AS instrument
              ON instrument.instrument_id = membership.instrument_id
            JOIN mra.data_capture AS instrument_capture
              ON instrument_capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS instrument_artifact
              ON instrument_artifact.artifact_id = instrument_capture.artifact_id
            WHERE membership.classification_id = %s
              AND capture.provider_product_id = %s
              AND membership.instrument_id = %s
              AND membership.effective_from <= %s
              AND (
                  membership.effective_to IS NULL
                  OR membership.effective_to > %s
              )
              AND membership.decision_visible_at <= %s
              AND capture.status = 'CAPTURED'
            ORDER BY membership.effective_from DESC,
                     membership.decision_visible_at DESC,
                     membership.revision DESC,
                     membership.membership_revision_id DESC
            LIMIT 1
            """,
            (
                classification_id,
                scope.market_provider_product_id,
                instrument_id.value,
                decision_time.value,
                decision_time.value,
                visibility_cutoff,
            ),
        ).fetchone()
        gap = self._membership_gap(
            scope=scope,
            instrument_id=instrument_id,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
        )
        if gap is not None and (member is None or gap[3] >= member[4]):
            gap_id = UUID(str(gap[0]))
            gap_capture_id = UUID(str(gap[1]))
            status = (
                MarketEvidenceStatus.STALE
                if gap[4] is not True
                else MarketEvidenceStatus.CONFLICT
                if str(gap[2]) == "CONFLICT"
                else MarketEvidenceStatus.GAP
            )
            return MembershipEvidence(
                status=status,
                membership_status=None,
                classification_id=classification_id,
                membership_revision_id=None,
                gap_id=gap_id,
                capture_id=gap_capture_id,
                decision_visible_at=gap[3],
                lineage=MarketLineage(
                    gap_ids=(gap_id,),
                    capture_ids=tuple(
                        sorted(
                            {classification_capture_id, gap_capture_id},
                            key=str,
                        )
                    ),
                ),
            )
        if member is None:
            return MembershipEvidence(
                status=MarketEvidenceStatus.MISSING,
                membership_status=None,
                classification_id=classification_id,
                membership_revision_id=None,
                gap_id=None,
                capture_id=classification_capture_id,
                decision_visible_at=classification[2],
                lineage=classification_lineage,
            )
        membership_revision_id = UUID(str(member[0]))
        capture_id = UUID(str(member[2]))
        lineage = MarketLineage(
            fact_revision_ids=(membership_revision_id,),
            capture_ids=tuple(sorted({classification_capture_id, capture_id}, key=str)),
        )
        if member[5] is not True or member[6] is not True:
            return MembershipEvidence(
                status=MarketEvidenceStatus.STALE,
                membership_status=MembershipStatus(str(member[3])),
                classification_id=UUID(str(member[1])),
                membership_revision_id=membership_revision_id,
                gap_id=None,
                capture_id=capture_id,
                decision_visible_at=member[4],
                lineage=lineage,
            )
        return MembershipEvidence(
            status=MarketEvidenceStatus.AVAILABLE,
            membership_status=MembershipStatus(str(member[3])),
            classification_id=UUID(str(member[1])),
            membership_revision_id=membership_revision_id,
            gap_id=None,
            capture_id=capture_id,
            decision_visible_at=member[4],
            lineage=lineage,
        )

    def _classification_gap(self, *, scope, decision_time, visibility_cutoff):
        return self._connection.execute(
            """
            SELECT gap.gap_id, gap.capture_id, gap.gap_kind,
                   gap.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.source_gap AS gap
            JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE gap.provider_product_id = %s
              AND gap.fact_kind = 'CLASSIFICATION'
              AND gap.classification_scheme = %s
              AND gap.classification_code = %s
              AND gap.effective_from <= %s
              AND (gap.effective_to IS NULL OR gap.effective_to > %s)
              AND gap.decision_visible_at <= %s
            ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
            LIMIT 1
            """,
            (
                scope.market_provider_product_id,
                scope.classification_scheme,
                scope.classification_code,
                decision_time.value,
                decision_time.value,
                visibility_cutoff,
            ),
        ).fetchone()

    def criterion_evidence_as_of(
        self,
        *,
        market_provider_product_id: UUID,
        rule: EligibilityRule,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
    ) -> CriterionEvidence:
        return self._criterion_evidence_as_of(
            market_provider_product_id=market_provider_product_id,
            rule=rule,
            instrument_id=instrument_id,
            decision_time=decision_time,
            visibility_cutoff=decision_time.value,
        )

    def criterion_evidence_for_exploratory_retrospective(
        self,
        *,
        market_provider_product_id: UUID,
        rule: EligibilityRule,
        instrument_id: InstrumentId,
        retrospective: ExploratoryRetrospectiveSelectionScope,
    ) -> CriterionEvidence:
        self._require_retrospective_archive(retrospective)
        evidence = self._criterion_evidence_as_of(
            market_provider_product_id=market_provider_product_id,
            rule=rule,
            instrument_id=instrument_id,
            decision_time=DecisionTime(retrospective.simulated_event_cutoff),
            visibility_cutoff=retrospective.knowledge_cutoff,
        )
        self._require_archive_lineage(evidence.lineage, retrospective)
        return evidence

    def _criterion_evidence_as_of(
        self,
        *,
        market_provider_product_id: UUID,
        rule: EligibilityRule,
        instrument_id: InstrumentId,
        decision_time: DecisionTime,
        visibility_cutoff: datetime,
    ) -> CriterionEvidence:
        if rule.rule_kind is EligibilityRuleKind.NOT_SPECIAL_TREATMENT:
            return self._effective_status(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                fact_kind="SPECIAL_TREATMENT_STATUS",
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
            )
        if rule.rule_kind is EligibilityRuleKind.MIN_LISTING_AGE:
            evidence = self._effective_status(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                fact_kind="LISTING_STATUS",
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
                include_effective_from=True,
            )
            if evidence.status is not MarketEvidenceStatus.AVAILABLE:
                return evidence
            if evidence.observed_status == "UNKNOWN":
                return evidence
            if evidence.observed_status != "LISTED":
                return evidence
            effective_from = evidence.effective_from
            if effective_from is None:
                raise AssertionError("Listing evidence lost effective_from")
            elapsed_days = (
                decision_time.value.astimezone(ZoneInfo("Asia/Shanghai")).date()
                - effective_from.astimezone(ZoneInfo("Asia/Shanghai")).date()
            ).days
            return CriterionEvidence(
                status=MarketEvidenceStatus.AVAILABLE,
                observed_decimal=Decimal(elapsed_days),
                lineage=evidence.lineage,
            )
        session = self._decision_session(
            market_provider_product_id=market_provider_product_id,
            instrument_id=instrument_id,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
        )
        if isinstance(session, CriterionEvidence):
            return session
        if rule.rule_kind is EligibilityRuleKind.NOT_SUSPENDED:
            return self._session_fact(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                session_id=UUID(str(session[0])),
                fact_kind="SECURITY_STATUS",
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
                session_lineage=session,
            )
        if rule.rule_kind is EligibilityRuleKind.LIMIT_METADATA_PRESENT:
            return self._limit_metadata(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                session_id=UUID(str(session[0])),
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
                session_lineage=session,
            )
        if rule.rule_kind is EligibilityRuleKind.MIN_LIQUIDITY:
            return self._liquidity(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                currency=rule.value_unit,
                window=rule.window_value,
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
            )
        raise AssertionError(f"unsupported Selection rule {rule.rule_kind.value}")

    def _membership_gap(
        self,
        *,
        scope,
        instrument_id,
        decision_time,
        visibility_cutoff,
    ):
        return self._connection.execute(
            """
            SELECT gap.gap_id, gap.capture_id, gap.gap_kind,
                   gap.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.source_gap AS gap
            JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE gap.provider_product_id = %s
              AND gap.fact_kind = 'CLASSIFICATION_MEMBERSHIP'
              AND gap.classification_scheme = %s
              AND gap.classification_code = %s
              AND gap.instrument_id = %s
              AND gap.effective_from <= %s
              AND (gap.effective_to IS NULL OR gap.effective_to > %s)
              AND gap.decision_visible_at <= %s
            ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
            LIMIT 1
            """,
            (
                scope.market_provider_product_id,
                scope.classification_scheme,
                scope.classification_code,
                instrument_id.value,
                decision_time.value,
                decision_time.value,
                visibility_cutoff,
            ),
        ).fetchone()

    def _effective_status(
        self,
        *,
        market_provider_product_id: UUID,
        instrument_id: InstrumentId,
        fact_kind: str,
        decision_time: DecisionTime,
        visibility_cutoff: datetime,
        include_effective_from: bool = False,
    ) -> CriterionEvidence:
        row = self._current_fact(
            market_provider_product_id=market_provider_product_id,
            instrument_id=instrument_id,
            fact_kind=fact_kind,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
            session_id=None,
            effective=True,
        )
        return self._criterion_from_fact(
            row,
            include_effective_from=include_effective_from,
        )

    def _decision_session(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        decision_time,
        visibility_cutoff,
    ):
        session_date = decision_time.value.astimezone(ZoneInfo("Asia/Shanghai")).date()
        row = self._connection.execute(
            """
            SELECT session.session_id, session.source_capture_id,
                   session.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ), instrument.currency,
                   mra.market_artifact_is_readable(
                       instrument_artifact.integrity_state,
                       instrument_artifact.last_verified_at
                   )
            FROM mra.instrument AS instrument
            JOIN mra.trading_session AS session
              ON session.exchange = instrument.exchange
            JOIN mra.data_capture AS capture
              ON capture.capture_id = session.source_capture_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            JOIN mra.data_capture AS instrument_capture
              ON instrument_capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS instrument_artifact
              ON instrument_artifact.artifact_id = instrument_capture.artifact_id
            WHERE instrument.instrument_id = %s
              AND session.session_date = %s
              AND capture.provider_product_id = %s
              AND session.decision_visible_at <= %s
              AND capture.status = 'CAPTURED'
            ORDER BY session.decision_visible_at DESC, session.session_id DESC
            LIMIT 1
            """,
            (
                instrument_id.value,
                session_date,
                market_provider_product_id,
                visibility_cutoff,
            ),
        ).fetchone()
        gap = self._session_gap(
            market_provider_product_id=market_provider_product_id,
            instrument_id=instrument_id,
            session_date=session_date,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
        )
        if gap is not None and (row is None or gap[3] >= row[2]):
            gap_id = UUID(str(gap[0]))
            capture_id = UUID(str(gap[1]))
            return CriterionEvidence(
                status=(
                    MarketEvidenceStatus.STALE
                    if gap[4] is not True
                    else MarketEvidenceStatus.CONFLICT
                    if str(gap[2]) == "CONFLICT"
                    else MarketEvidenceStatus.GAP
                ),
                lineage=MarketLineage(gap_ids=(gap_id,), capture_ids=(capture_id,)),
            )
        if row is None:
            return CriterionEvidence(
                status=MarketEvidenceStatus.MISSING,
                lineage=MarketLineage(),
            )
        session_id = UUID(str(row[0]))
        capture_id = UUID(str(row[1]))
        if row[3] is not True or row[5] is not True:
            return CriterionEvidence(
                status=MarketEvidenceStatus.STALE,
                lineage=MarketLineage(
                    session_ids=(session_id,),
                    capture_ids=(capture_id,),
                ),
            )
        return row

    def _session_gap(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        session_date,
        decision_time,
        visibility_cutoff,
    ):
        return self._connection.execute(
            """
            SELECT gap.gap_id, gap.capture_id, gap.gap_kind,
                   gap.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.instrument AS instrument
            JOIN mra.source_gap AS gap ON gap.exchange = instrument.exchange
            JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE instrument.instrument_id = %s
              AND gap.provider_product_id = %s
              AND gap.fact_kind = 'TRADING_SESSION'
              AND gap.session_date = %s
              AND gap.decision_visible_at <= %s
            ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
            LIMIT 1
            """,
            (
                instrument_id.value,
                market_provider_product_id,
                session_date,
                visibility_cutoff,
            ),
        ).fetchone()

    def _session_fact(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        session_id,
        fact_kind,
        decision_time,
        visibility_cutoff,
        session_lineage,
    ):
        row = self._current_fact(
            market_provider_product_id=market_provider_product_id,
            instrument_id=instrument_id,
            fact_kind=fact_kind,
            decision_time=decision_time,
            visibility_cutoff=visibility_cutoff,
            session_id=session_id,
            effective=False,
        )
        return self._criterion_from_fact(
            row,
            extra_session_id=session_id,
            extra_capture_id=UUID(str(session_lineage[1])),
        )

    def _limit_metadata(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        session_id,
        decision_time,
        visibility_cutoff,
        session_lineage,
    ):
        facts = tuple(
            self._current_fact(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                fact_kind=fact_kind,
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
                session_id=session_id,
                effective=False,
            )
            for fact_kind in (
                "LIMIT_UP_PRICE",
                "LIMIT_DOWN_PRICE",
                "REFERENCE_PRICE",
            )
        )
        evidences = tuple(self._criterion_from_fact(row) for row in facts)
        unavailable = next(
            (item for item in evidences if item.status is not MarketEvidenceStatus.AVAILABLE),
            None,
        )
        lineage = _merge_lineage(
            *(item.lineage for item in evidences),
            MarketLineage(
                session_ids=(session_id,),
                capture_ids=(UUID(str(session_lineage[1])),),
            ),
        )
        if unavailable is not None:
            return CriterionEvidence(status=unavailable.status, lineage=lineage)
        return CriterionEvidence(
            status=MarketEvidenceStatus.AVAILABLE,
            observed_count=3,
            lineage=lineage,
        )

    def _liquidity(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        currency,
        window,
        decision_time,
        visibility_cutoff,
    ):
        sessions = self._connection.execute(
            """
            SELECT session.session_id, session.source_capture_id,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ), instrument.currency,
                   mra.market_artifact_is_readable(
                       instrument_artifact.integrity_state,
                       instrument_artifact.last_verified_at
                   ), session.open_at, session.close_at
            FROM mra.instrument AS instrument
            JOIN mra.trading_session AS session
              ON session.exchange = instrument.exchange
            JOIN mra.data_capture AS capture
              ON capture.capture_id = session.source_capture_id
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            JOIN mra.data_capture AS instrument_capture
              ON instrument_capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS instrument_artifact
              ON instrument_artifact.artifact_id = instrument_capture.artifact_id
            WHERE instrument.instrument_id = %s
              AND capture.provider_product_id = %s
              AND session.close_at <= %s
              AND session.decision_visible_at <= %s
              AND capture.status = 'CAPTURED'
            ORDER BY session.session_date DESC, session.session_id DESC
            LIMIT %s
            """,
            (
                instrument_id.value,
                market_provider_product_id,
                decision_time.value,
                visibility_cutoff,
                window,
            ),
        ).fetchall()
        if len(sessions) != window:
            return CriterionEvidence(
                status=MarketEvidenceStatus.MISSING,
                lineage=_session_rows_lineage(sessions),
            )
        if any(row[2] is not True or row[4] is not True for row in sessions):
            return CriterionEvidence(
                status=MarketEvidenceStatus.STALE,
                lineage=_session_rows_lineage(sessions),
            )
        if any(str(row[3]) != currency for row in sessions):
            return CriterionEvidence(
                status=MarketEvidenceStatus.CONFLICT,
                lineage=_session_rows_lineage(sessions),
            )
        bars = tuple(
            self._daily_bar(
                market_provider_product_id=market_provider_product_id,
                instrument_id=instrument_id,
                session_id=UUID(str(session[0])),
                event_start=session[5],
                event_end=session[6],
                decision_time=decision_time,
                visibility_cutoff=visibility_cutoff,
            )
            for session in sessions
        )
        unavailable = next(
            (item for item in bars if item.status is not MarketEvidenceStatus.AVAILABLE),
            None,
        )
        lineage = _merge_lineage(
            _session_rows_lineage(sessions),
            *(item.lineage for item in bars),
        )
        if unavailable is not None:
            return CriterionEvidence(status=unavailable.status, lineage=lineage)
        amounts = [item.observed_decimal for item in bars]
        if any(item is None for item in amounts):
            raise AssertionError("available turnover evidence lost its value")
        mean = (sum((item for item in amounts if item is not None), Decimal(0)) / Decimal(window)).quantize(Decimal("0.0000000001"))
        return CriterionEvidence(
            status=MarketEvidenceStatus.AVAILABLE,
            observed_decimal=mean,
            lineage=lineage,
        )

    def _daily_bar(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        session_id,
        event_start,
        event_end,
        decision_time,
        visibility_cutoff,
    ):
        row = self._connection.execute(
            """
            SELECT bar.bar_revision_id, bar.capture_id, bar.turnover_value,
                   bar.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ),
                   mra.market_artifact_is_readable(
                       instrument_artifact.integrity_state,
                       instrument_artifact.last_verified_at
                   )
            FROM mra.market_bar_revision AS bar
            JOIN mra.data_capture AS capture ON capture.capture_id = bar.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            JOIN mra.instrument AS instrument ON instrument.instrument_id = bar.instrument_id
            JOIN mra.data_capture AS instrument_capture
              ON instrument_capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS instrument_artifact
              ON instrument_artifact.artifact_id = instrument_capture.artifact_id
            WHERE bar.instrument_id = %s
              AND bar.provider_product_id = %s
              AND bar.session_id = %s
              AND bar.timeframe = 'DAILY'
              AND bar.price_basis = 'RAW_UNADJUSTED'
              AND bar.event_start = %s
              AND bar.event_end = %s
              AND bar.decision_visible_at <= %s
              AND capture.status = 'CAPTURED'
            ORDER BY bar.decision_visible_at DESC, bar.revision DESC,
                     bar.bar_revision_id DESC
            LIMIT 1
            """,
            (
                instrument_id.value,
                market_provider_product_id,
                session_id,
                event_start,
                event_end,
                visibility_cutoff,
            ),
        ).fetchone()
        gap = self._connection.execute(
            """
            SELECT gap.gap_id, gap.capture_id, gap.gap_kind,
                   gap.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.source_gap AS gap
            JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE gap.provider_product_id = %s
              AND gap.instrument_id = %s
              AND gap.session_id = %s
              AND gap.fact_kind = 'MARKET_BAR'
              AND gap.timeframe = 'DAILY'
              AND gap.price_basis = 'RAW_UNADJUSTED'
              AND gap.event_start = %s
              AND gap.event_end = %s
              AND gap.decision_visible_at <= %s
            ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
            LIMIT 1
            """,
            (
                market_provider_product_id,
                instrument_id.value,
                session_id,
                event_start,
                event_end,
                visibility_cutoff,
            ),
        ).fetchone()
        if gap is not None and (row is None or gap[3] >= row[3]):
            gap_id = UUID(str(gap[0]))
            capture_id = UUID(str(gap[1]))
            return CriterionEvidence(
                status=(
                    MarketEvidenceStatus.STALE
                    if gap[4] is not True
                    else MarketEvidenceStatus.CONFLICT
                    if str(gap[2]) == "CONFLICT"
                    else MarketEvidenceStatus.GAP
                ),
                lineage=MarketLineage(
                    gap_ids=(gap_id,),
                    session_ids=(session_id,),
                    capture_ids=(capture_id,),
                ),
            )
        if row is None or row[2] is None:
            return CriterionEvidence(
                status=MarketEvidenceStatus.MISSING,
                lineage=MarketLineage(session_ids=(session_id,)),
            )
        bar_id = UUID(str(row[0]))
        capture_id = UUID(str(row[1]))
        lineage = MarketLineage(
            bar_revision_ids=(bar_id,),
            session_ids=(session_id,),
            capture_ids=(capture_id,),
        )
        if row[4] is not True or row[5] is not True:
            return CriterionEvidence(
                status=MarketEvidenceStatus.STALE,
                lineage=lineage,
            )
        return CriterionEvidence(
            status=MarketEvidenceStatus.AVAILABLE,
            observed_decimal=Decimal(row[2]),
            lineage=lineage,
        )

    def _current_fact(
        self,
        *,
        market_provider_product_id,
        instrument_id,
        fact_kind,
        decision_time,
        visibility_cutoff,
        session_id,
        effective,
    ):
        evidence_scope = "EFFECTIVE_INTERVAL" if effective else "DECISION_SESSION"
        fact = self._connection.execute(
            """
            SELECT fact.fact_revision_id, fact.capture_id, fact.status_value,
                   fact.numeric_value, fact.decision_visible_at,
                   fact.event_start,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   ),
                   mra.market_artifact_is_readable(
                       instrument_artifact.integrity_state,
                       instrument_artifact.last_verified_at
                   )
            FROM mra.instrument_fact_revision AS fact
            JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            JOIN mra.instrument AS instrument ON instrument.instrument_id = fact.instrument_id
            JOIN mra.data_capture AS instrument_capture
              ON instrument_capture.capture_id = instrument.source_capture_id
            JOIN mra.artifact AS instrument_artifact
              ON instrument_artifact.artifact_id = instrument_capture.artifact_id
            WHERE fact.instrument_id = %s
              AND fact.provider_product_id = %s
              AND fact.fact_kind = %s
              AND fact.evidence_scope = %s
              AND fact.session_id IS NOT DISTINCT FROM %s
              AND fact.decision_visible_at <= %s
              AND (
                  NOT %s
                  OR (
                      fact.event_start <= %s
                      AND (fact.event_end IS NULL OR fact.event_end > %s)
                  )
              )
              AND capture.status = 'CAPTURED'
            ORDER BY fact.event_start DESC, fact.decision_visible_at DESC,
                     fact.revision DESC, fact.fact_revision_id DESC
            LIMIT 1
            """,
            (
                instrument_id.value,
                market_provider_product_id,
                fact_kind,
                evidence_scope,
                session_id,
                visibility_cutoff,
                effective,
                decision_time.value,
                decision_time.value,
            ),
        ).fetchone()
        gap = self._connection.execute(
            """
            SELECT gap.gap_id, gap.capture_id, gap.gap_kind,
                   gap.decision_visible_at,
                   mra.market_artifact_is_readable(
                       artifact.integrity_state, artifact.last_verified_at
                   )
            FROM mra.source_gap AS gap
            JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE gap.instrument_id = %s
              AND gap.provider_product_id = %s
              AND gap.fact_kind = 'INSTRUMENT_FACT'
              AND gap.instrument_fact_kind = %s
              AND gap.evidence_scope = %s
              AND gap.session_id IS NOT DISTINCT FROM %s
              AND gap.decision_visible_at <= %s
              AND (
                  NOT %s
                  OR (
                      gap.effective_from <= %s
                      AND (gap.effective_to IS NULL OR gap.effective_to > %s)
                  )
              )
            ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
            LIMIT 1
            """,
            (
                instrument_id.value,
                market_provider_product_id,
                fact_kind,
                evidence_scope,
                session_id,
                visibility_cutoff,
                effective,
                decision_time.value,
                decision_time.value,
            ),
        ).fetchone()
        if gap is not None and (fact is None or gap[3] >= fact[4]):
            return ("GAP", *gap)
        return fact

    @staticmethod
    def _criterion_from_fact(
        row,
        *,
        extra_session_id: UUID | None = None,
        extra_capture_id: UUID | None = None,
        include_effective_from: bool = False,
    ):
        if row is None:
            return CriterionEvidence(
                status=MarketEvidenceStatus.MISSING,
                lineage=MarketLineage(
                    session_ids=(extra_session_id,) if extra_session_id else (),
                    capture_ids=(extra_capture_id,) if extra_capture_id else (),
                ),
            )
        if row[0] == "GAP":
            gap_id = UUID(str(row[1]))
            capture_id = UUID(str(row[2]))
            status = (
                MarketEvidenceStatus.STALE
                if row[5] is not True
                else MarketEvidenceStatus.CONFLICT
                if str(row[3]) == "CONFLICT"
                else MarketEvidenceStatus.GAP
            )
            return CriterionEvidence(
                status=status,
                lineage=MarketLineage(
                    gap_ids=(gap_id,),
                    session_ids=(extra_session_id,) if extra_session_id else (),
                    capture_ids=tuple(
                        sorted(
                            {capture_id, *([extra_capture_id] if extra_capture_id else [])},
                            key=str,
                        )
                    ),
                ),
            )
        fact_id = UUID(str(row[0]))
        capture_id = UUID(str(row[1]))
        lineage = MarketLineage(
            fact_revision_ids=(fact_id,),
            session_ids=(extra_session_id,) if extra_session_id else (),
            capture_ids=tuple(
                sorted(
                    {capture_id, *([extra_capture_id] if extra_capture_id else [])},
                    key=str,
                )
            ),
        )
        if row[6] is not True or row[7] is not True:
            return CriterionEvidence(
                status=MarketEvidenceStatus.STALE,
                lineage=lineage,
            )
        if row[2] is not None:
            return CriterionEvidence(
                status=MarketEvidenceStatus.AVAILABLE,
                observed_status=str(row[2]),
                effective_from=row[5] if include_effective_from else None,
                lineage=lineage,
            )
        if row[3] is not None:
            return CriterionEvidence(
                status=MarketEvidenceStatus.AVAILABLE,
                observed_decimal=Decimal(row[3]),
                lineage=lineage,
            )
        return CriterionEvidence(
            status=MarketEvidenceStatus.MISSING,
            lineage=lineage,
        )

    def _require_retrospective_archive(
        self,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None:
        row = self._connection.execute(
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
            FOR SHARE OF archive, seal
            """,
            (
                scope.market_archive_id,
                scope.market_archive_seal_id,
                scope.knowledge_cutoff,
            ),
        ).fetchone()
        if row is None:
            raise ValueError(
                "retrospective Selection requires an exact sealed archive"
            )

    def _require_archive_lineage(
        self,
        lineage: MarketLineage,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None:
        capture_ids = tuple(lineage.capture_ids)
        if not capture_ids:
            return
        rows = self._connection.execute(
            """
            SELECT capture_id
            FROM mra.market_archive_capture_observation
            WHERE market_archive_id = %s
              AND capture_id = ANY(%s::uuid[])
            FOR SHARE
            """,
            (scope.market_archive_id, list(capture_ids)),
        ).fetchall()
        if {UUID(str(row[0])) for row in rows} != set(capture_ids):
            raise ValueError(
                "retrospective Selection Market lineage is outside its exact archive"
            )


def _merge_lineage(*items: MarketLineage) -> MarketLineage:
    return MarketLineage(
        fact_revision_ids=tuple(sorted({value for item in items for value in item.fact_revision_ids}, key=str)),
        bar_revision_ids=tuple(sorted({value for item in items for value in item.bar_revision_ids}, key=str)),
        gap_ids=tuple(sorted({value for item in items for value in item.gap_ids}, key=str)),
        session_ids=tuple(sorted({value for item in items for value in item.session_ids}, key=str)),
        capture_ids=tuple(sorted({value for item in items for value in item.capture_ids}, key=str)),
    )


def _session_rows_lineage(rows) -> MarketLineage:
    return MarketLineage(
        session_ids=tuple(sorted({UUID(str(row[0])) for row in rows}, key=str)),
        capture_ids=tuple(sorted({UUID(str(row[1])) for row in rows}, key=str)),
    )


__all__ = ["PostgresSelectionMarketQueries"]
