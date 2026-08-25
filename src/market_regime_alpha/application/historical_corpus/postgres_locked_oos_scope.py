"""Typed PostgreSQL owner for a label-blind Locked OOS scope."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.locked_oos_scope import (
    FrozenLockedOOSScope,
    LockedOOSAccessDecision,
    assess_locked_oos_access,
    freeze_locked_oos_scope,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_contracts import PITValidationOutcome
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.research import HistoricalConstituentTimeline


class PostgresLockedOOSScopeAuthority:
    """Persist one immutable roster without importing or reading Outcomes."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._research = PostgresResearchValidationRepository(factory)
        self._universe = PostgresFreeResearchUniverseRepository(factory)
        self._pit = PostgresPITAuthority(factory)
        self._calendars = PostgresPITTradingCalendarSnapshotRepository(factory)
        self._evidence = PostgresHistoricalEvidenceRepository(factory)

    def freeze(
        self,
        *,
        protocol_reference: ValidationArtifactReference,
        calendar_reference: ValidationArtifactReference,
        universe_timeline_reference: ValidationArtifactReference,
        external_final_target_session: date,
        data_cutoff: datetime,
        recorded_at: datetime,
    ) -> FrozenLockedOOSScope:
        protocol = self._load_protocol(protocol_reference)
        calendar = self._load_calendar(calendar_reference)
        timeline = self._load_timeline(universe_timeline_reference)
        scope = freeze_locked_oos_scope(
            protocol_reference=ValidationArtifactReference(
                "RESEARCH_EXPERIMENT_DEFINITION",
                protocol.definition_id,
                protocol.definition_hash,
            ),
            calendar=calendar,
            universe_timeline=timeline,
            external_final_target_session=external_final_target_session,
            data_cutoff=data_cutoff,
        )
        return self.record(scope=scope, recorded_at=recorded_at)

    def record(
        self,
        *,
        scope: FrozenLockedOOSScope,
        recorded_at: datetime,
    ) -> FrozenLockedOOSScope:
        self._verify_upstream_owners(scope)
        self._research.record(
            artifact_id=scope.scope_id,
            artifact_hash=scope.scope_hash,
            artifact_kind="FROZEN_LOCKED_OOS_SCOPE",
            evidence_authority="ENGINEERING_ONLY",
            payload=scope.identity_payload(),
            created_at=recorded_at,
        )

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO frozen_locked_oos_scope(
                    scope_id, scope_hash, protocol_id, protocol_hash,
                    trading_calendar_id, trading_calendar_hash,
                    universe_timeline_id, universe_timeline_hash,
                    external_final_target_session, data_cutoff,
                    decision_session_count, target_binding_count,
                    outcome_values_read, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, false, %s, %s
                )
                ON CONFLICT (scope_id) DO NOTHING
                """,
                (
                    str(scope.scope_id),
                    scope.scope_hash,
                    str(scope.protocol_reference.artifact_id),
                    scope.protocol_reference.content_hash,
                    str(scope.calendar_reference.artifact_id),
                    scope.calendar_reference.content_hash,
                    str(scope.universe_timeline_reference.artifact_id),
                    scope.universe_timeline_reference.content_hash,
                    scope.external_final_target_session,
                    scope.data_cutoff,
                    len(scope.decision_sessions),
                    len(scope.target_session_bindings),
                    Jsonb(scope.to_canonical_dict()),
                    recorded_at,
                ),
            )
            self._verify_projection(connection, scope)

        self._factory.run_transaction(operation)
        return self.get(scope.reference)

    def get(
        self,
        reference: ValidationArtifactReference,
    ) -> FrozenLockedOOSScope:
        if reference.artifact_kind != "FROZEN_LOCKED_OOS_SCOPE":
            raise ValueError("Locked OOS scope reference kind is invalid")
        payload = self._research.get_artifact_payload(reference)
        scope = FrozenLockedOOSScope.from_canonical_dict(
            {
                "scope_id": str(reference.artifact_id),
                "scope_hash": reference.content_hash,
                **payload,
            }
        )
        with self._factory.connection(read_only=True) as connection:
            self._verify_projection(connection, scope)
        self._verify_upstream_owners(scope)
        return scope

    def get_by_id(self, scope_id: ArtifactId) -> FrozenLockedOOSScope:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT scope_hash FROM frozen_locked_oos_scope "
                "WHERE scope_id = %s",
                (str(scope_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(scope_id))
        return self.get(
            ValidationArtifactReference(
                "FROZEN_LOCKED_OOS_SCOPE",
                scope_id,
                str(row[0]),
            )
        )

    def assess_access(
        self,
        *,
        scope_reference: ValidationArtifactReference,
        formal_pit_references: tuple[ValidationArtifactReference, ...],
        physical_correctness_reference: ValidationArtifactReference | None,
    ) -> LockedOOSAccessDecision:
        """Reload only gate Evidence; this method has no Outcome dependency."""

        scope = self.get(scope_reference)
        pit_supported = bool(formal_pit_references)
        for reference in formal_pit_references:
            if reference.artifact_kind != "FORMAL_PIT_EVIDENCE":
                raise ValueError("Locked OOS gate Formal PIT kind is invalid")
            evidence = self._pit.get_evidence(reference.artifact_id)
            if evidence.evidence_hash != reference.content_hash:
                raise ValueError("Locked OOS gate Formal PIT owner drifted")
            pit_supported = (
                pit_supported
                and evidence.outcome is PITValidationOutcome.SATISFIED
                and not evidence.rejection_codes
            )
        correctness_supported = False
        if physical_correctness_reference is not None:
            if (
                physical_correctness_reference.artifact_kind
                != "HISTORICAL_ALPHA_CORRECTNESS_EVIDENCE"
            ):
                raise ValueError(
                    "Locked OOS gate physical correctness kind is invalid"
                )
            correctness = self._evidence.get(
                physical_correctness_reference.artifact_id
            )
            if correctness.evidence_hash != (
                physical_correctness_reference.content_hash
            ):
                raise ValueError(
                    "Locked OOS gate physical correctness owner drifted"
                )
            correctness_supported = (
                correctness.evidence_kind
                is HistoricalEvidenceKind.ALPHA_CORRECTNESS
                and correctness.payload.get("status")
                == "CORRECTNESS_SUPPORTED"
                and isinstance(correctness.payload.get("proof"), dict)
                and correctness.payload["proof"].get("conclusion")
                == "CORRECTNESS_SUPPORTED"
            )
        return assess_locked_oos_access(
            scope=scope,
            formal_pit_supported=pit_supported,
            physical_correctness_supported=correctness_supported,
        )

    def _verify_upstream_owners(self, scope: FrozenLockedOOSScope) -> None:
        self._load_protocol(scope.protocol_reference)
        self._load_calendar(scope.calendar_reference)
        timeline = self._load_timeline(scope.universe_timeline_reference)
        expected = dict(scope.session_universe_references)
        timeline_by_session = {
            session: reference
            for session, effective in timeline.query_effective_dates
            for cohort in timeline.cohorts
            if cohort.effective_date == effective
            for reference in (cohort.snapshot_reference,)
        }
        if any(
            timeline_by_session.get(session) != reference
            for session, reference in expected.items()
        ):
            raise ValueError("Locked OOS scope Universe timeline drifted")
        for reference in sorted(
            set(expected.values()),
            key=lambda item: str(item.artifact_id),
        ):
            snapshot = self._universe.get(reference.artifact_id)
            if snapshot.snapshot_hash != reference.content_hash:
                raise ValueError("Locked OOS scope Universe owner drifted")

    def _load_protocol(self, reference: ValidationArtifactReference):
        if reference.artifact_kind != "RESEARCH_EXPERIMENT_DEFINITION":
            raise ValueError("Locked OOS protocol reference kind is invalid")
        protocol = self._research.get_historical_experiment_definition(
            reference.artifact_id
        )
        if protocol.definition_hash != reference.content_hash:
            raise ValueError("Locked OOS protocol owner drifted")
        return protocol

    def _load_calendar(
        self,
        reference: ValidationArtifactReference,
    ) -> TradingCalendarArtifact:
        if reference.artifact_kind != "TRADING_CALENDAR":
            raise ValueError("Locked OOS Calendar reference kind is invalid")
        calendar = self._calendars.get(reference.artifact_id)
        if calendar.content_hash != reference.content_hash:
            raise ValueError("Locked OOS Calendar owner drifted")
        return calendar

    def _load_timeline(
        self,
        reference: ValidationArtifactReference,
    ) -> HistoricalConstituentTimeline:
        if reference.artifact_kind != "HISTORICAL_CONSTITUENT_TIMELINE":
            raise ValueError("Locked OOS Timeline reference kind is invalid")
        timeline = self._universe.get_timeline(reference.artifact_id)
        if timeline.timeline_hash != reference.content_hash:
            raise ValueError("Locked OOS Timeline owner drifted")
        return timeline

    @staticmethod
    def _verify_projection(connection: Any, scope: FrozenLockedOOSScope) -> None:
        row = connection.execute(
            """
            SELECT scope_hash, protocol_id, protocol_hash,
                   trading_calendar_id, trading_calendar_hash,
                   universe_timeline_id, universe_timeline_hash,
                   external_final_target_session, data_cutoff,
                   decision_session_count, target_binding_count,
                   outcome_values_read, payload_json
            FROM frozen_locked_oos_scope WHERE scope_id = %s
            """,
            (str(scope.scope_id),),
        ).fetchone()
        expected = (
            scope.scope_hash,
            str(scope.protocol_reference.artifact_id),
            scope.protocol_reference.content_hash,
            str(scope.calendar_reference.artifact_id),
            scope.calendar_reference.content_hash,
            str(scope.universe_timeline_reference.artifact_id),
            scope.universe_timeline_reference.content_hash,
            scope.external_final_target_session,
            scope.data_cutoff,
            len(scope.decision_sessions),
            len(scope.target_session_bindings),
            False,
            scope.to_canonical_dict(),
        )
        actual = None if row is None else (*row[:12], dict(row[12]))
        if actual != expected:
            raise ValueError("Locked OOS scope PostgreSQL projection drifted")


__all__ = ["PostgresLockedOOSScopeAuthority"]
