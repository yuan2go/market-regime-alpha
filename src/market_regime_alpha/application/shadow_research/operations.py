"""Application orchestration for the Research Shadow Operating Loop.

The service coordinates existing authorities.  It deliberately does not own
or reimplement Continuous Runtime, market-data acquisition, Order, Fill,
Broker, or Position behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.runtime_authority_evidence import (
    PostgresRuntimeAuthorityEvidenceRepository,
    RuntimeAuthorityEvidence,
)

from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    TradeHorizonOutcomeEvidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeSettlementSourceArchive,
)
from market_regime_alpha.application.controlled_operation.postgres_prospective_outcome import (
    PostgresProspectiveOutcomeRepository,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    ProspectiveShadowOutcome,
    SettlementSessionStatus,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.panel_v2 import (
    FrozenResearchPanelV2,
    build_research_panel_slice_v2,
    publish_research_panel_v2,
)
from market_regime_alpha.application.research_evaluation.postgres_panel_v2 import (
    PostgresResearchPanelRepository,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    CanonicalStateFactorSource,
    ResearchPanelEnrichment,
    extract_canonical_factors,
    publish_research_panel_enrichment,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetedShadowOutcome,
    build_targeted_shadow_outcome,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    ProspectiveEvidenceAttestation,
    RuntimeOrigin,
)
from market_regime_alpha.application.shadow_research.contracts import (
    ShadowDecision,
    ShadowSessionCommand,
    ShadowSessionSnapshot,
    ShadowSessionStatus,
)
from market_regime_alpha.application.shadow_research.postgres_attestation import (
    PostgresProspectiveAttestationRepository,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.forecasting.contracts import PathForecast
from market_regime_alpha.signals.v3 import SignalRunArtifactV3
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion


@dataclass(frozen=True, slots=True)
class ShadowSettlementResult:
    factual_outcome_v1: ProspectiveShadowOutcome
    targeted_outcome_v2: TargetedShadowOutcome
    attestation: ProspectiveEvidenceAttestation
    session: ShadowSessionSnapshot


class ResearchShadowOperations:
    """Crash-recoverable facade over the existing bounded owners."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._continuous = PostgresContinuousResearchJournal(
            factory,
            apply_migrations=False,
        )
        self._runtime_authority = PostgresRuntimeAuthorityEvidenceRepository(factory)
        self._shadow = PostgresShadowResearchRepository(factory)
        self._outcomes = PostgresProspectiveOutcomeRepository(factory, apply_migrations=False)
        self._targets = PostgresTargetOutcomeRepository(factory, apply_migrations=False)
        self._attestations = PostgresProspectiveAttestationRepository(factory, apply_migrations=False)
        self._panels = PostgresResearchPanelRepository(factory, apply_migrations=False)
        self._validation = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )

    def schedule(self, command: ShadowSessionCommand) -> ShadowSessionSnapshot:
        return self._shadow.schedule(command)

    def run_or_attach(self, session_id: ArtifactId, *, expected_version: int) -> ShadowSessionSnapshot:
        """Attach to the Canonical Runtime; no parallel Runtime is created."""

        snapshot = self._shadow.get_session(session_id)
        if snapshot.status is ShadowSessionStatus.RUNNING:
            return snapshot
        return self._shadow.mark_running(session_id, expected_version=expected_version)

    def freeze(
        self,
        session_id: ArtifactId,
        *,
        summary_id: ArtifactId,
        decision_frozen_at: datetime,
        expected_version: int,
    ) -> ShadowDecision:
        return self._shadow.freeze(
            session_id,
            summary_id=summary_id,
            decision_frozen_at=decision_frozen_at,
            expected_version=expected_version,
        )

    def outcome_pending(self, session_id: ArtifactId, *, expected_version: int) -> ShadowSessionSnapshot:
        snapshot = self._shadow.get_session(session_id)
        if snapshot.status is ShadowSessionStatus.OUTCOME_PENDING:
            return snapshot
        return self._shadow.mark_outcome_pending(session_id, expected_version=expected_version)

    def settle(
        self,
        *,
        decision_id: ArtifactId,
        source_archive: OutcomeSettlementSourceArchive,
        settlement_dataset: VerifiedMarketDataDataset,
        factual_evidence: TradeHorizonOutcomeEvidence,
        next_session_date: date,
        session_status: SettlementSessionStatus,
        target_protocol: OutcomeTargetProtocol,
        expected_shadow_version: int,
        created_at: datetime,
        code_revision: str,
        clock_mode: ClockMode,
        runtime_origin: RuntimeOrigin,
    ) -> ShadowSettlementResult:
        decision = self._shadow.replay(decision_id)
        runtime = self._continuous.get_run(decision.run_id)
        if runtime.command.code_revision != code_revision:
            raise ValueError("Attestation code revision does not match the frozen Runtime")
        if runtime.command.authority_mode is not RuntimeAuthorityMode.SHADOW:
            raise ValueError("Attestation Runtime is not SHADOW authority")
        try:
            runtime_evidence = self._runtime_authority.get(
                decision.run_id,
                decision.tick_id,
            )
        except KeyError:
            runtime_evidence = self._runtime_authority.record(
                RuntimeAuthorityEvidence.create(
                    run_id=decision.run_id,
                    tick_id=decision.tick_id,
                    clock_mode=ClockMode.UNKNOWN,
                    runtime_origin=RuntimeOrigin.UNKNOWN,
                    clock_source="RUNTIME_EVIDENCE_MISSING_AT_SETTLEMENT",
                    origin_source="RUNTIME_EVIDENCE_MISSING_AT_SETTLEMENT",
                    observed_at=decision.decision_frozen_at,
                    recorded_at=created_at,
                    code_revision=runtime.command.code_revision,
                )
            )
        # The CLI fields are compatibility assertions only.  They are never the
        # final source used by the Attestation.
        del clock_mode, runtime_origin
        try:
            factual = self._outcomes.get_for_decision(decision_id)
        except KeyError:
            factual = self._outcomes.build(
                decision_id=decision_id,
                source_archive=source_archive,
                settlement_dataset=settlement_dataset,
                factual_evidence=factual_evidence,
                next_session_date=next_session_date,
                session_status=session_status,
                created_at=created_at,
            )
            factual = self._outcomes.settle(factual, expected_shadow_version=expected_shadow_version)
        else:
            if factual.next_session_date != next_session_date or factual.session_status is not session_status:
                raise ValueError("Existing factual Outcome settlement request conflicts")
            self._outcomes.replay(
                factual.settlement_id,
                source_archive=source_archive,
                settlement_dataset=settlement_dataset,
                factual_evidence=factual_evidence,
            )
        self._targets.register_protocol(target_protocol)
        targeted = build_targeted_shadow_outcome(
            decision=decision,
            factual_outcome_v1=factual,
            settlement_dataset=settlement_dataset,
            protocol=target_protocol,
            created_at=created_at,
        )
        targeted = self._targets.settle(targeted)
        attestation = ProspectiveEvidenceAttestation.create(
            decision=decision,
            outcome=factual,
            source_acquisition_receipts=decision.provider_source_references,
            code_revision=code_revision,
            runtime_mode=runtime.command.authority_mode,
            runtime_authority=runtime_evidence,
            created_at=created_at,
        )
        attestation = self._attestations.record(attestation)
        return ShadowSettlementResult(
            factual_outcome_v1=factual,
            targeted_outcome_v2=targeted,
            attestation=attestation,
            session=self._shadow.get_session(decision.session_id),
        )

    def resume(self, session_id: ArtifactId, *, expected_version: int) -> ShadowSessionSnapshot:
        snapshot = self._shadow.get_session(session_id)
        if snapshot.status is ShadowSessionStatus.FAILED:
            return self._shadow.mark_running(
                session_id,
                expected_version=expected_version,
                recovered=True,
            )
        return snapshot

    def build_evaluation(
        self,
        *,
        decision_id: ArtifactId,
        targeted_outcome_id: ArtifactId,
        target_protocol_id: ArtifactId,
        dynamic_pool: DynamicStockPoolVersion,
        candidate_set: CandidateSet,
        state_policy_references: tuple[RuntimeArtifactReference, ...],
        artifact_root: Path,
        created_at: datetime,
    ) -> tuple[FrozenResearchPanelV2, Path]:
        decision = self._shadow.replay(decision_id)
        targeted = self._targets.replay(targeted_outcome_id)
        protocol = self._targets.get_protocol(target_protocol_id)
        if created_at < targeted.created_at:
            raise ValueError("Research Panel cannot predate Targeted Outcome")
        panel_slice = build_research_panel_slice_v2(
            decision=decision,
            dynamic_pool=dynamic_pool,
            candidate_set=candidate_set,
            targeted_outcome=targeted,
            target_protocol=protocol,
            state_policy_references=state_policy_references,
        )
        panel = FrozenResearchPanelV2.create(
            target_protocol=protocol,
            slices=(panel_slice,),
            created_at=created_at,
        )
        path = publish_research_panel_v2(root=artifact_root, panel=panel)
        return self._panels.register(panel, artifact_path=path), path

    def build_enriched_evaluation(
        self,
        *,
        decision_id: ArtifactId,
        targeted_outcome_id: ArtifactId,
        target_protocol_id: ArtifactId,
        dynamic_pool: DynamicStockPoolVersion,
        candidate_set: CandidateSet,
        state_policy_references: tuple[RuntimeArtifactReference, ...],
        dataset: VerifiedMarketDataDataset,
        feature_bundle: VerifiedFeatureBundleV2,
        signal_run: SignalRunArtifactV3 | None,
        forecasts: tuple[PathForecast, ...],
        state_sources: tuple[CanonicalStateFactorSource, ...],
        artifact_root: Path,
        created_at: datetime,
    ) -> tuple[FrozenResearchPanelV2, ResearchPanelEnrichment, Path, Path]:
        decision = self._shadow.replay(decision_id)
        if (
            str(dataset.artifact.dataset_id) != str(decision.dataset.artifact_id)
            or dataset.artifact.content_hash != decision.dataset.content_hash
            or str(feature_bundle.artifact.bundle_id) != str(decision.feature_bundle.artifact_id)
            or feature_bundle.artifact.content_hash != decision.feature_bundle.content_hash
        ):
            raise ValueError("Panel enrichment Dataset/Feature Bundle differs from frozen Shadow Decision")
        expected_optional = (
            (decision.dynamic_pool, dynamic_pool.pool_id, dynamic_pool.pool_hash, "Dynamic Pool"),
            (decision.candidate_set, candidate_set.envelope.artifact_id, candidate_set.envelope.content_hash, "Candidate Set"),
        )
        for expected, artifact_id, digest, label in expected_optional:
            if expected is None or str(expected.artifact_id) != str(artifact_id) or expected.content_hash != digest:
                raise ValueError(f"Panel enrichment {label} differs from frozen Shadow Decision")
        if signal_run is not None and (
            decision.signal is None
            or str(decision.signal.artifact_id) != str(signal_run.artifact_id)
            or decision.signal.content_hash != signal_run.envelope.content_hash
        ):
            raise ValueError("Panel enrichment Signal differs from frozen Shadow Decision")
        panel, panel_path = self.build_evaluation(
            decision_id=decision_id,
            targeted_outcome_id=targeted_outcome_id,
            target_protocol_id=target_protocol_id,
            dynamic_pool=dynamic_pool,
            candidate_set=candidate_set,
            state_policy_references=state_policy_references,
            artifact_root=artifact_root,
            created_at=created_at,
        )
        symbols = tuple(sorted({row.symbol for panel_slice in panel.slices for row in panel_slice.rows}))
        enrichment = extract_canonical_factors(
            panel_reference=ValidationArtifactReference("RESEARCH_PANEL_V2", panel.panel_id, panel.panel_hash),
            symbols=symbols,
            dataset=dataset,
            feature_bundle=feature_bundle,
            dynamic_pool=dynamic_pool,
            candidate_set=candidate_set,
            signal_run=signal_run,
            forecasts=forecasts,
            state_sources=state_sources,
            decision_time=decision.decision_time,
            extracted_at=created_at,
        )
        enrichment_path = publish_research_panel_enrichment(
            root=artifact_root / "enrichments",
            enrichment=enrichment,
        )
        self._validation.record_panel_enrichment(enrichment)
        return panel, enrichment, panel_path, enrichment_path

    def invalidate(
        self,
        session_id: ArtifactId,
        *,
        expected_version: int,
        reason_codes: tuple[str, ...],
    ) -> ShadowSessionSnapshot:
        return self._shadow.invalidate(
            session_id,
            expected_version=expected_version,
            reason_codes=reason_codes,
        )

    def replay(self, decision_id: ArtifactId) -> ShadowDecision:
        return self._shadow.replay(decision_id)

    def report(self, session_id: ArtifactId) -> dict[str, Any]:
        session = self._shadow.get_session(session_id)
        decision: ShadowDecision | None
        try:
            decision = self._shadow.get_decision_for_session(session_id)
        except KeyError:
            decision = None
        with self._factory.connection(read_only=True) as connection:
            outcome = connection.execute(
                """
                SELECT settlement_id, settlement_hash, availability_status,
                       outcome_available_at
                FROM prospective_outcome_settlement
                WHERE shadow_session_id = %s
                """,
                (str(session_id),),
            ).fetchone()
            targeted = (
                None
                if decision is None
                else connection.execute(
                    """
                    SELECT settlement_id, settlement_hash, target_protocol_id,
                           availability_status
                    FROM targeted_shadow_outcome WHERE shadow_decision_id = %s
                    ORDER BY created_at, settlement_id
                    """,
                    (str(decision.decision_id),),
                ).fetchall()
            )
            attestations = (
                ()
                if decision is None
                else connection.execute(
                    """
                    SELECT attestation_id, attestation_hash, status,
                           clock_mode, runtime_origin, prospective_proven
                    FROM prospective_evidence_attestation
                    WHERE shadow_decision_id = %s ORDER BY created_at, attestation_id
                    """,
                    (str(decision.decision_id),),
                ).fetchall()
            )
            panels = (
                ()
                if decision is None
                else connection.execute(
                    """
                    SELECT panel.panel_id, panel.panel_hash, panel.row_count,
                           slice.targeted_outcome_id
                    FROM research_evaluation_panel_slice_v2 AS slice
                    JOIN research_evaluation_panel_v2 AS panel
                      ON panel.panel_id = slice.panel_id
                    WHERE slice.shadow_decision_id = %s
                    ORDER BY panel.created_at, panel.panel_id
                    """,
                    (str(decision.decision_id),),
                ).fetchall()
            )
        return {
            "schema": "research_shadow_operations_report/v1",
            "session": _session_dict(session),
            "decision": None if decision is None else decision.to_canonical_dict(),
            "outcome": (
                None
                if outcome is None
                else {
                    "settlement_id": str(outcome[0]),
                    "settlement_hash": str(outcome[1]),
                    "availability_status": str(outcome[2]),
                    "outcome_available_at": outcome[3].isoformat(),
                }
            ),
            "targeted_outcomes": [
                {
                    "settlement_id": str(row[0]),
                    "settlement_hash": str(row[1]),
                    "target_protocol_id": str(row[2]),
                    "availability_status": str(row[3]),
                }
                for row in targeted or ()
            ],
            "attestations": [
                {
                    "attestation_id": str(row[0]),
                    "attestation_hash": str(row[1]),
                    "status": str(row[2]),
                    "clock_mode": str(row[3]),
                    "runtime_origin": str(row[4]),
                    "prospective_proven": bool(row[5]),
                }
                for row in attestations
            ],
            "evaluation_panels_v2": [
                {
                    "panel_id": str(row[0]),
                    "panel_hash": str(row[1]),
                    "row_count": int(row[2]),
                    "targeted_outcome_id": str(row[3]),
                }
                for row in panels
            ],
            "authority": {
                "research_shadow_engineering_ready": True,
                "prospective_proven": False,
                "alpha_proven": False,
                "order_authority": False,
                "broker_authority": False,
                "position_mutation": False,
            },
        }


def _session_dict(value: ShadowSessionSnapshot) -> dict[str, Any]:
    return {
        "session_id": str(value.command.session_id),
        "run_id": str(value.command.run_id),
        "trading_date": value.command.trading_date.isoformat(),
        "status": value.status.value,
        "outcome_status": value.outcome_status.value,
        "decision_id": None if value.decision_id is None else str(value.decision_id),
        "version": value.version,
        "reason_codes": list(value.reason_codes),
        "created_at": value.created_at.isoformat(),
        "updated_at": value.updated_at.isoformat(),
        "finished_at": None if value.finished_at is None else value.finished_at.isoformat(),
    }


__all__ = ["ResearchShadowOperations", "ShadowSettlementResult"]
