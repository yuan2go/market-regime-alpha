"""PostgreSQL owner for automatic Shadow observation policies and receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ObservationKind,
    OwnerObservationValue,
    ShadowOwnerLineageRequest,
    ShadowObservationPolicy,
    ShadowObservationReceipt,
    build_observation_receipt,
    build_portfolio_observation_receipt,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.panel_v2 import (
    FrozenResearchPanelV2,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetedShadowOutcome,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_evaluation.postgres_panel_v2 import (
    PostgresResearchPanelRepository,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.market_data import PriceLimitState, TradingStatus
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PostgresShadowObservationRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish(
        self,
        *,
        policy: ShadowObservationPolicy,
        receipt: ShadowObservationReceipt,
    ) -> ShadowObservationReceipt:
        if (
            receipt.policy_reference.artifact_id != policy.policy_id
            or receipt.policy_reference.content_hash != policy.policy_hash
        ):
            raise ValueError("Shadow Observation receipt does not bind Policy")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO shadow_observation_policy(
                    policy_id, policy_hash, policy_version, payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (policy_id) DO NOTHING
                """,
                (
                    str(policy.policy_id),
                    policy.policy_hash,
                    policy.policy_version,
                    Jsonb(policy.to_canonical_dict()),
                    policy.created_at,
                ),
            )
            stored_policy = connection.execute(
                "SELECT policy_hash, payload_json FROM shadow_observation_policy "
                "WHERE policy_id = %s",
                (str(policy.policy_id),),
            ).fetchone()
            if stored_policy is None or (
                str(stored_policy[0]) != policy.policy_hash
                or stored_policy[1] != policy.to_canonical_dict()
            ):
                raise ValueError("Shadow Observation Policy identity conflict")

            connection.execute(
                """
                INSERT INTO shadow_observation_receipt(
                    receipt_id, receipt_hash, observation_kind, build_status,
                    research_trading_date, trading_date, observed_at, symbol,
                    policy_id, policy_hash, formal_pit, formal_oos, calibrated,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, false, false, false, %s, %s
                ) ON CONFLICT (receipt_id) DO NOTHING
                """,
                (
                    str(receipt.receipt_id),
                    receipt.receipt_hash,
                    receipt.kind.value,
                    receipt.status.value,
                    receipt.research_trading_date,
                    receipt.trading_date,
                    receipt.observed_at,
                    receipt.symbol,
                    str(policy.policy_id),
                    policy.policy_hash,
                    Jsonb(receipt.to_canonical_dict()),
                    receipt.observed_at,
                ),
            )
            stored_receipt = connection.execute(
                "SELECT receipt_hash, payload_json FROM shadow_observation_receipt "
                "WHERE receipt_id = %s",
                (str(receipt.receipt_id),),
            ).fetchone()
            if stored_receipt is None or (
                str(stored_receipt[0]) != receipt.receipt_hash
                or stored_receipt[1] != receipt.to_canonical_dict()
            ):
                raise ValueError("Shadow Observation receipt identity conflict")

            for value in receipt.values:
                reference = value.source_reference
                if reference is None:
                    raise ValueError("Shadow Observation value owner is missing")
                connection.execute(
                    """
                    INSERT INTO shadow_observation_value(
                        receipt_id, value_name, provenance, source_artifact_id,
                        source_content_hash, effective_at, available_at, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id, value_name) DO NOTHING
                    """,
                    (
                        str(receipt.receipt_id),
                        value.name,
                        value.provenance.value,
                        str(reference.artifact_id),
                        reference.content_hash,
                        value.effective_at,
                        value.available_at,
                        Jsonb(value.to_canonical_dict()),
                    ),
                )
            for ordinal, reference in enumerate(receipt.source_references, start=1):
                connection.execute(
                    """
                    INSERT INTO shadow_observation_source_binding(
                        receipt_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id, ordinal) DO NOTHING
                    """,
                    (
                        str(receipt.receipt_id),
                        ordinal,
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                    ),
                )
            self._verify_projections(connection, receipt)
            self._verify_typed_owner_chain(connection, receipt)

        self._factory.run_transaction(operation)
        return self.get(receipt.receipt_id)

    def get_policy(self, policy_id: ArtifactId) -> ShadowObservationPolicy:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT policy_hash, payload_json FROM shadow_observation_policy "
                "WHERE policy_id = %s",
                (str(policy_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(policy_id))
        policy = ShadowObservationPolicy.from_canonical_dict(row[1])
        if str(row[0]) != policy.policy_hash:
            raise ValueError("Shadow Observation Policy owner hash diverged")
        return policy

    def get(self, receipt_id: ArtifactId) -> ShadowObservationReceipt:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT receipt_hash, payload_json FROM shadow_observation_receipt "
                "WHERE receipt_id = %s",
                (str(receipt_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], dict):
                raise KeyError(str(receipt_id))
            receipt = ShadowObservationReceipt.from_canonical_dict(row[1])
            if str(row[0]) != receipt.receipt_hash:
                raise ValueError("Shadow Observation receipt owner hash diverged")
            self._verify_projections(connection, receipt)
            self._verify_typed_owner_chain(connection, receipt)
        return receipt

    def replay(self, receipt_id: ArtifactId) -> ShadowObservationReceipt:
        return self.get(receipt_id)

    def find(
        self,
        *,
        kind: ObservationKind,
        research_trading_date: date,
        trading_date: date,
        observed_at: datetime,
        symbol: str | None,
        policy_id: ArtifactId,
    ) -> ShadowObservationReceipt:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT receipt_id FROM shadow_observation_receipt
                WHERE observation_kind = %s
                  AND research_trading_date = %s
                  AND trading_date = %s
                  AND observed_at = %s
                  AND symbol IS NOT DISTINCT FROM %s
                  AND policy_id = %s
                """,
                (
                    kind.value,
                    research_trading_date,
                    trading_date,
                    observed_at,
                    symbol,
                    str(policy_id),
                ),
            ).fetchone()
        if row is None:
            raise KeyError("Shadow Observation receipt not found")
        return self.get(ArtifactId(str(row[0])))

    @staticmethod
    def _verify_projections(
        connection: Any,
        receipt: ShadowObservationReceipt,
    ) -> None:
        value_rows = connection.execute(
            "SELECT payload_json FROM shadow_observation_value "
            "WHERE receipt_id = %s ORDER BY value_name",
            (str(receipt.receipt_id),),
        ).fetchall()
        source_rows = connection.execute(
            """
            SELECT artifact_kind, artifact_id, content_hash
            FROM shadow_observation_source_binding
            WHERE receipt_id = %s ORDER BY ordinal
            """,
            (str(receipt.receipt_id),),
        ).fetchall()
        if [row[0] for row in value_rows] != [
            item.to_canonical_dict() for item in receipt.values
        ]:
            raise ValueError("Shadow Observation value projection diverged")
        if [tuple(str(item) for item in row) for row in source_rows] != [
            (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            )
            for item in receipt.source_references
        ]:
            raise ValueError("Shadow Observation source projection diverged")

    @staticmethod
    def _verify_typed_owner_chain(
        connection: Any,
        receipt: ShadowObservationReceipt,
    ) -> None:
        required = {
            "SHADOW_DECISION",
            "RESEARCH_PANEL_V2",
            "CANDIDATE_SET",
            "OUTCOME_TARGET_PROTOCOL",
            "TARGETED_SHADOW_OUTCOME",
            "PANEL_ENRICHMENT",
        }
        typed_references = tuple(
            item
            for item in receipt.source_references
            if item.artifact_kind in required
        )
        if not typed_references:
            return
        if (
            len(typed_references) != len(required)
            or {item.artifact_kind for item in typed_references} != required
        ):
            raise ValueError("Typed Shadow Observation owner chain is incomplete")
        references = {item.artifact_kind: item for item in typed_references}
        queries = {
            "SHADOW_DECISION": (
                "shadow_research_decision", "decision_id", "decision_hash", "created_at", ""
            ),
            "RESEARCH_PANEL_V2": (
                "research_evaluation_panel_v2", "panel_id", "panel_hash", "created_at", ""
            ),
            "CANDIDATE_SET": (
                "state_runtime_candidate_artifact", "candidate_id", "candidate_hash", "created_at", ""
            ),
            "OUTCOME_TARGET_PROTOCOL": (
                "outcome_target_protocol", "protocol_id", "protocol_hash", "created_at", ""
            ),
            "TARGETED_SHADOW_OUTCOME": (
                "targeted_shadow_outcome", "settlement_id", "settlement_hash",
                "greatest(created_at, outcome_available_at)", ""
            ),
            "PANEL_ENRICHMENT": (
                "research_validation_artifact", "artifact_id", "artifact_hash", "created_at",
                " AND artifact_kind = 'PANEL_ENRICHMENT'",
            ),
        }
        for kind, reference in references.items():
            table, id_column, hash_column, time_column, predicate = queries[kind]
            owner = connection.execute(
                f"SELECT {hash_column}, {time_column} FROM {table} "
                f"WHERE {id_column} = %s{predicate}",
                (str(reference.artifact_id),),
            ).fetchone()
            if (
                owner is None
                or str(owner[0]) != reference.content_hash
                or (owner[1] is not None and receipt.observed_at < owner[1])
            ):
                raise ValueError(f"Typed Shadow Observation {kind} owner mismatch")
        PostgresShadowObservationRepository._verify_typed_relationships_and_values(
            connection,
            receipt,
            references,
        )

    @staticmethod
    def _verify_typed_relationships_and_values(
        connection: Any,
        receipt: ShadowObservationReceipt,
        references: dict[str, ValidationArtifactReference],
    ) -> None:
        decision_row = connection.execute(
            """
            SELECT decision.decision_hash, decision.decision_time,
                   shadow.trading_date
            FROM shadow_research_decision AS decision
            JOIN shadow_research_session AS shadow
              ON shadow.session_id = decision.session_id
            WHERE decision.decision_id = %s
            """,
            (str(references["SHADOW_DECISION"].artifact_id),),
        ).fetchone()
        panel_row = connection.execute(
            "SELECT payload_json FROM research_evaluation_panel_v2 "
            "WHERE panel_id = %s",
            (str(references["RESEARCH_PANEL_V2"].artifact_id),),
        ).fetchone()
        outcome_row = connection.execute(
            "SELECT payload_json FROM targeted_shadow_outcome "
            "WHERE settlement_id = %s",
            (str(references["TARGETED_SHADOW_OUTCOME"].artifact_id),),
        ).fetchone()
        enrichment_row = connection.execute(
            "SELECT payload_json FROM research_validation_artifact "
            "WHERE artifact_kind = 'PANEL_ENRICHMENT' AND artifact_id = %s",
            (str(references["PANEL_ENRICHMENT"].artifact_id),),
        ).fetchone()
        if (
            decision_row is None
            or panel_row is None
            or outcome_row is None
            or enrichment_row is None
            or not isinstance(panel_row[0], dict)
            or not isinstance(outcome_row[0], dict)
            or not isinstance(enrichment_row[0], dict)
        ):
            raise ValueError("Typed Shadow Observation relationship owner is missing")
        panel = FrozenResearchPanelV2.from_canonical_dict(panel_row[0])
        outcome = TargetedShadowOutcome.from_canonical_dict(outcome_row[0])
        enrichment = ResearchPanelEnrichment.from_canonical_dict(
            {
                "enrichment_id": str(references["PANEL_ENRICHMENT"].artifact_id),
                "enrichment_hash": references["PANEL_ENRICHMENT"].content_hash,
                **enrichment_row[0],
            }
        )
        slices = tuple(
            item
            for item in panel.slices
            if _same_reference(item.shadow_decision, references["SHADOW_DECISION"])
            and _same_reference(
                item.targeted_outcome,
                references["TARGETED_SHADOW_OUTCOME"],
            )
        )
        if len(slices) != 1:
            raise ValueError("Typed Shadow Observation Panel slice is ambiguous")
        panel_slice = slices[0]
        candidate = panel_slice.candidate_set
        expected_candidate = references["CANDIDATE_SET"]
        relationship_mismatches = tuple(
            label
            for label, matched in (
                (
                    "DECISION_HASH",
                    str(decision_row[0])
                    == references["SHADOW_DECISION"].content_hash,
                ),
                ("DECISION_DATE", decision_row[2] == receipt.research_trading_date),
                (
                    "PANEL_DATE",
                    panel_slice.trading_date == receipt.research_trading_date,
                ),
                (
                    "OUTCOME_DECISION",
                    _same_reference(
                        outcome.shadow_decision,
                        references["SHADOW_DECISION"],
                    ),
                ),
                (
                    "OUTCOME_SESSION",
                    outcome.next_session_date == receipt.trading_date,
                ),
                (
                    "OUTCOME_PROTOCOL_ID",
                    outcome.target_protocol_id
                    == references["OUTCOME_TARGET_PROTOCOL"].artifact_id,
                ),
                (
                    "OUTCOME_PROTOCOL_HASH",
                    outcome.target_protocol_hash
                    == references["OUTCOME_TARGET_PROTOCOL"].content_hash,
                ),
                (
                    "CANDIDATE",
                    candidate is not None
                    and candidate.artifact_id == expected_candidate.artifact_id
                    and candidate.content_hash == expected_candidate.content_hash,
                ),
                (
                    "ENRICHMENT_PANEL",
                    enrichment.panel_reference == references["RESEARCH_PANEL_V2"],
                ),
            )
            if not matched
        )
        if relationship_mismatches:
            raise ValueError(
                "Typed Shadow Observation relationship lineage drift: "
                + ",".join(relationship_mismatches)
            )
        label_rows = connection.execute(
            "SELECT label_id, label_hash, label_json "
            "FROM targeted_shadow_outcome_label "
            "WHERE settlement_id = %s ORDER BY label_id",
            (str(outcome.settlement_id),),
        ).fetchall()
        if [
            (str(row[0]), str(row[1]), row[2]) for row in label_rows
        ] != sorted(
            (
                str(item.label_id),
                item.label_hash,
                item.to_canonical_dict(),
            )
            for item in outcome.labels
        ):
            raise ValueError("Typed Shadow Observation Target projection drift")
        exposure_rows = connection.execute(
            "SELECT exposure_json FROM research_panel_factor_exposure "
            "WHERE enrichment_id = %s",
            (str(enrichment.enrichment_id),),
        ).fetchall()
        if {
            canonical_hash(row[0]) for row in exposure_rows
        } != {
            canonical_hash(item.to_canonical_dict())
            for item in enrichment.exposures
        } or len(exposure_rows) != len(enrichment.exposures):
            raise ValueError("Typed Shadow Observation Enrichment projection drift")
        runtime_references = {
            ValidationArtifactReference(
                getattr(item, "artifact_kind", None)
                or getattr(item, "reference_kind"),
                item.artifact_id,
                item.content_hash,
            )
            for item in (
                panel_slice.market_state,
                panel_slice.etf_state,
                panel_slice.theme_state,
                panel_slice.capital_state,
                panel_slice.dynamic_pool,
                panel_slice.candidate_set,
                panel_slice.signal,
                panel_slice.forecast,
            )
            if item is not None
        }
        value_references = {
            item.source_reference
            for item in receipt.values
            if item.source_reference is not None
        }
        expected_references = {
            *references.values(),
            *runtime_references,
            *value_references,
            receipt.policy_reference,
        }
        if set(receipt.source_references) != expected_references:
            raise ValueError("Typed Shadow Observation source set diverged")
        summary_row = connection.execute(
            "SELECT content_hash, created_at FROM research_daily_summary "
            "WHERE summary_id = %s",
            (str(panel_slice.summary.artifact_id),),
        ).fetchone()
        if (
            summary_row is None
            or str(summary_row[0]) != panel_slice.summary.content_hash
            or receipt.observed_at < summary_row[1]
        ):
            raise ValueError("Typed Shadow Observation Summary owner mismatch")
        for reference in runtime_references:
            if (
                reference.artifact_kind == "STATE_CONSTRAINED_CANDIDATE_SET"
                and reference.artifact_id
                == references["CANDIDATE_SET"].artifact_id
                and reference.content_hash
                == references["CANDIDATE_SET"].content_hash
            ):
                continue
            stage_rows = connection.execute(
                """
                SELECT output_artifact_hash,
                       greatest(available_at, stage_completed_at)
                FROM research_summary_stage
                WHERE summary_id = %s
                  AND output_artifact_id = %s
                  AND output_artifact_hash = %s
                """,
                (
                    str(panel_slice.summary.artifact_id),
                    str(reference.artifact_id),
                    reference.content_hash,
                ),
            ).fetchall()
            if (
                len(stage_rows) != 1
                or str(stage_rows[0][0]) != reference.content_hash
                or receipt.observed_at < stage_rows[0][1]
            ):
                raise ValueError(
                    "Typed Shadow Observation Runtime owner mismatch: "
                    f"{reference.artifact_kind}"
                )
        PostgresShadowObservationRepository._verify_value_owners(
            connection,
            receipt=receipt,
            outcome=outcome,
            enrichment=enrichment,
            decision_time=decision_row[1],
        )

    @staticmethod
    def _verify_value_owners(
        connection: Any,
        *,
        receipt: ShadowObservationReceipt,
        outcome: TargetedShadowOutcome,
        enrichment: ResearchPanelEnrichment,
        decision_time: datetime,
    ) -> None:
        policy_row = connection.execute(
            "SELECT policy_hash, created_at FROM shadow_observation_policy "
            "WHERE policy_id = %s",
            (str(receipt.policy_reference.artifact_id),),
        ).fetchone()
        if (
            policy_row is None
            or str(policy_row[0]) != receipt.policy_reference.content_hash
            or receipt.observed_at < policy_row[1]
        ):
            raise ValueError("Typed Shadow Observation Policy owner mismatch")
        labels = {
            ValidationArtifactReference(
                "TARGET_OUTCOME_LABEL", item.label_id, item.label_hash
            ): item
            for item in outcome.labels
        }
        enrichment_reference = ValidationArtifactReference(
            "PANEL_ENRICHMENT",
            enrichment.enrichment_id,
            enrichment.enrichment_hash,
        )
        outcome_reference = ValidationArtifactReference(
            "TARGETED_SHADOW_OUTCOME",
            outcome.settlement_id,
            outcome.settlement_hash,
        )
        exposure_sources = {
            (item.source_reference, item.source_value_path): item
            for item in enrichment.exposures
        }
        for value in receipt.values:
            reference = value.source_reference
            assert reference is not None
            if reference == receipt.policy_reference:
                if value.available_at != policy_row[1]:
                    raise ValueError("Typed Shadow Observation Policy value time drift")
                continue
            label = labels.get(reference)
            if label is not None:
                expected_effective = (
                    label.label_interval_start
                    if value.source_value_path.endswith(".decision_reference_price")
                    else label.label_interval_end
                )
                if (
                    value.available_at != label.outcome_available_at
                    or value.effective_at != expected_effective
                    or receipt.observed_at < label.outcome_available_at
                ):
                    raise ValueError("Typed Shadow Observation Target value time drift")
                continue
            if reference == outcome_reference:
                if (
                    value.available_at != outcome.outcome_available_at
                    or value.effective_at != outcome.outcome_available_at
                ):
                    raise ValueError("Typed Shadow Observation Outcome value time drift")
                continue
            if reference == enrichment_reference:
                if (
                    value.available_at != enrichment.extracted_at
                    or value.effective_at != decision_time
                    or value.source_value_path
                    != "exposures[liquidity.adv20].raw_numeric"
                ):
                    raise ValueError("Typed Shadow Observation Enrichment value drift")
                continue
            exposure = exposure_sources.get((reference, value.source_value_path))
            if exposure is None:
                raise ValueError("Typed Shadow Observation value owner is unsupported")
            expected_available = exposure.available_at or enrichment.extracted_at
            if (
                value.available_at != expected_available
                or receipt.observed_at < max(expected_available, enrichment.extracted_at)
                or value.effective_at != decision_time
            ):
                raise ValueError("Typed Shadow Observation exposure value time drift")


@dataclass(frozen=True, slots=True)
class ShadowOwnerContext:
    decision: Any
    panel: Any
    panel_slice: Any
    candidate_set: Any
    outcome: Any
    protocol: Any
    enrichment: ResearchPanelEnrichment
    available_at: datetime


class PostgresOwnerResolvedShadowObservationBuilder:
    """Reload current fact owners and publish replayable automatic inputs."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        self._observations = PostgresShadowObservationRepository(
            factory,
            apply_migrations=apply_migrations,
        )
        self._shadow = PostgresShadowResearchRepository(
            factory,
            apply_migrations=False,
        )
        self._state = PostgresStateSystemRepository(
            factory,
            apply_migrations=False,
        )
        self._panels = PostgresResearchPanelRepository(
            factory,
            apply_migrations=False,
        )
        self._targets = PostgresTargetOutcomeRepository(
            factory,
            apply_migrations=False,
        )

    def resolve_lineage(
        self,
        *,
        research_trading_date: date,
        lineage: ShadowOwnerLineageRequest,
    ) -> ShadowOwnerContext:
        return self._context(
            research_trading_date=research_trading_date,
            lineage=lineage,
        )

    def build_strategy(
        self,
        *,
        research_trading_date: date,
        observed_at: datetime,
        policy: ShadowObservationPolicy,
        lineage: ShadowOwnerLineageRequest,
        symbol: str | None = None,
    ) -> ShadowObservationReceipt:
        context = self._context(
            research_trading_date=research_trading_date,
            lineage=lineage,
        )
        if observed_at < context.available_at:
            raise ValueError(
                "Automatic Strategy observation predates owner availability"
            )
        selected = context.candidate_set.selected
        selected_by_symbol = {item.symbol: item for item in selected}
        resolved_symbol = symbol or (None if not selected else selected[0].symbol)
        if resolved_symbol is None or resolved_symbol not in selected_by_symbol:
            values: tuple[OwnerObservationValue, ...] = ()
            receipt = build_observation_receipt(
                kind=ObservationKind.STRATEGY,
                research_trading_date=research_trading_date,
                trading_date=context.outcome.next_session_date,
                observed_at=observed_at,
                symbol=resolved_symbol,
                policy=policy,
                values=values,
                source_references=self._context_references(context),
            )
            return self._observations.publish(policy=policy, receipt=receipt)

        fill_label = self._optional_label(
            context,
            symbol=resolved_symbol,
            checkpoint=policy.fill_checkpoint,
        )
        mark_label = self._optional_label(
            context,
            symbol=resolved_symbol,
            checkpoint=policy.mark_checkpoint,
        )
        policy_reference = ValidationArtifactReference(
            "SHADOW_OBSERVATION_POLICY",
            policy.policy_id,
            policy.policy_hash,
        )
        outcome_reference = ValidationArtifactReference(
            "TARGETED_SHADOW_OUTCOME",
            context.outcome.settlement_id,
            context.outcome.settlement_hash,
        )
        fill_reference = (
            outcome_reference
            if fill_label is None
            else _label_reference(fill_label)
        )
        mark_reference = (
            outcome_reference
            if mark_label is None
            else _label_reference(mark_label)
        )
        blocked_fill = fill_label is None or _fill_blocked(fill_label)
        fillability = Decimal("0") if blocked_fill else policy.fillability
        observed_fill_price = (
            None if blocked_fill or fill_label is None else fill_label.checkpoint_price
        )
        exit_cost = (
            None
            if mark_label is None or mark_label.checkpoint_price is None
            else mark_label.checkpoint_price
            * policy.intended_quantity
            * policy.exit_cost_bps
            / Decimal("10000")
        )
        values = tuple(
            sorted(
                (
                    _owner_value(
                        "decision_reference_price",
                        None if fill_label is None else fill_label.decision_reference_price,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        fill_reference,
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.label_interval_start,
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.outcome_available_at,
                        f"labels[{policy.fill_checkpoint.value}].decision_reference_price",
                    ),
                    _owner_value(
                        "observed_fill_price",
                        observed_fill_price,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        fill_reference,
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.label_interval_end,
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.outcome_available_at,
                        f"labels[{policy.fill_checkpoint.value}].checkpoint_price",
                    ),
                    _owner_value(
                        "current_price",
                        None if mark_label is None else mark_label.checkpoint_price,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        mark_reference,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.label_interval_end,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.outcome_available_at,
                        f"labels[{policy.mark_checkpoint.value}].checkpoint_price",
                    ),
                    _owner_value(
                        "mfe",
                        None if mark_label is None else mark_label.mfe,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        mark_reference,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.label_interval_end,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.outcome_available_at,
                        f"labels[{policy.mark_checkpoint.value}].mfe",
                    ),
                    _owner_value(
                        "mae",
                        None if mark_label is None else mark_label.mae,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        mark_reference,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.label_interval_end,
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.outcome_available_at,
                        f"labels[{policy.mark_checkpoint.value}].mae",
                    ),
                    *(
                        _owner_value(
                            name,
                            value,
                            ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                            policy_reference,
                            policy.created_at,
                            policy.created_at,
                            f"policy.{name}",
                        )
                        for name, value in (
                            ("intended_quantity", policy.intended_quantity),
                            ("fillability", fillability),
                            ("slippage_bps", policy.slippage_bps),
                            ("impact_bps", policy.impact_bps),
                            ("commission_bps", policy.commission_bps),
                            ("sessions_held", context.protocol.session_offset),
                            ("signal_reversed", False),
                            ("market_deteriorated", False),
                            ("theme_deteriorated", False),
                            ("capital_deteriorated", False),
                            ("exit_cost", exit_cost),
                        )
                    ),
                ),
                key=lambda item: item.name,
            )
        )
        receipt = build_observation_receipt(
            kind=ObservationKind.STRATEGY,
            research_trading_date=research_trading_date,
            trading_date=context.outcome.next_session_date,
            observed_at=observed_at,
            symbol=resolved_symbol,
            policy=policy,
            values=values,
            source_references=self._context_references(context),
        )
        return self._observations.publish(policy=policy, receipt=receipt)

    def build_portfolio(
        self,
        *,
        research_trading_date: date,
        trading_date: date,
        observed_at: datetime,
        policy: ShadowObservationPolicy,
        lineage: ShadowOwnerLineageRequest,
        required_symbols: tuple[str, ...] = (),
    ) -> ShadowObservationReceipt:
        context = self._context(
            research_trading_date=research_trading_date,
            lineage=lineage,
        )
        if observed_at < context.available_at:
            raise ValueError(
                "Automatic Portfolio observation predates owner availability"
            )
        if trading_date != context.outcome.next_session_date:
            raise ValueError(
                "Automatic Portfolio trading date must equal Outcome next session"
            )
        selected = {item.symbol: item for item in context.candidate_set.selected}
        symbols = tuple(sorted(set(required_symbols) | set(selected)))
        policy_reference = ValidationArtifactReference(
            "SHADOW_OBSERVATION_POLICY",
            policy.policy_id,
            policy.policy_hash,
        )
        values: list[OwnerObservationValue] = []
        market_observations: list[dict[str, Any]] = []
        for symbol in symbols:
            fill_label = self._optional_label(
                context,
                symbol=symbol,
                checkpoint=policy.fill_checkpoint,
            )
            mark_label = self._optional_label(
                context,
                symbol=symbol,
                checkpoint=policy.mark_checkpoint,
            )
            adv = next(
                (
                    item
                    for item in context.enrichment.exposures
                    if item.symbol == symbol and item.factor_id == "liquidity.adv20"
                ),
                None,
            )
            outcome_reference = ValidationArtifactReference(
                "TARGETED_SHADOW_OUTCOME",
                context.outcome.settlement_id,
                context.outcome.settlement_hash,
            )
            enrichment_reference = ValidationArtifactReference(
                "PANEL_ENRICHMENT",
                context.enrichment.enrichment_id,
                context.enrichment.enrichment_hash,
            )
            fill_ref = (
                outcome_reference
                if fill_label is None
                else _label_reference(fill_label)
            )
            mark_ref = (
                outcome_reference
                if mark_label is None
                else _label_reference(mark_label)
            )
            adv_ref = enrichment_reference if adv is None else adv.source_reference
            fill_available = (
                context.outcome.outcome_available_at
                if fill_label is None
                else fill_label.outcome_available_at
            )
            mark_available = (
                context.outcome.outcome_available_at
                if mark_label is None
                else mark_label.outcome_available_at
            )
            conditions = set() if fill_label is None else set(fill_label.market_conditions)
            trading_status = _trading_status(conditions)
            limit_state = _price_limit_state(conditions)
            observed_values = (
                (
                    "reference_price",
                    None if fill_label is None else fill_label.decision_reference_price,
                    fill_ref,
                    (
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.label_interval_start
                    ),
                    fill_available,
                    f"labels[{policy.fill_checkpoint.value}].decision_reference_price",
                ),
                (
                    "mark_price",
                    None if mark_label is None else mark_label.checkpoint_price,
                    mark_ref,
                    (
                        context.outcome.outcome_available_at
                        if mark_label is None
                        else mark_label.label_interval_end
                    ),
                    mark_available,
                    f"labels[{policy.mark_checkpoint.value}].checkpoint_price",
                ),
                (
                    "average_daily_amount",
                    None if adv is None else adv.raw_numeric,
                    adv_ref,
                    context.decision.decision_time,
                    (
                        context.enrichment.extracted_at
                        if adv is None or adv.available_at is None
                        else adv.available_at
                    ),
                    (
                        "exposures[liquidity.adv20].raw_numeric"
                        if adv is None
                        else adv.source_value_path
                    ),
                ),
                (
                    "trading_status",
                    None if trading_status is TradingStatus.UNKNOWN else trading_status.value,
                    fill_ref,
                    (
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.label_interval_end
                    ),
                    fill_available,
                    f"labels[{policy.fill_checkpoint.value}].market_conditions",
                ),
                (
                    "price_limit_state",
                    None if limit_state is PriceLimitState.UNKNOWN else limit_state.value,
                    fill_ref,
                    (
                        context.outcome.outcome_available_at
                        if fill_label is None
                        else fill_label.label_interval_end
                    ),
                    fill_available,
                    f"labels[{policy.fill_checkpoint.value}].market_conditions",
                ),
            )
            for (
                name,
                value,
                reference,
                effective_at,
                available_at,
                source_value_path,
            ) in observed_values:
                values.append(
                    _owner_value(
                        f"{symbol}.{name}",
                        value,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        reference,
                        effective_at,
                        available_at,
                        source_value_path,
                    )
                )
            values.append(
                _owner_value(
                    f"{symbol}.trade_session",
                    policy.trade_session.value,
                    ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                    policy_reference,
                    policy.created_at,
                    policy.created_at,
                    "policy.trade_session",
                )
            )
            reason_codes = set()
            if fill_label is None or mark_label is None:
                reason_codes.add("TARGET_OUTCOME_LABEL_MISSING")
            if adv is None or adv.raw_numeric is None:
                reason_codes.add("ADV20_OWNER_FACT_MISSING")
            market_observations.append(
                {
                    "symbol": symbol,
                    "reference_price": None if fill_label is None else str(fill_label.decision_reference_price),
                    "mark_price": None if mark_label is None or mark_label.checkpoint_price is None else str(mark_label.checkpoint_price),
                    "average_daily_amount": None if adv is None or adv.raw_numeric is None else str(adv.raw_numeric),
                    "trading_status": trading_status.value,
                    "price_limit_state": limit_state.value,
                    "trade_session": policy.trade_session.value,
                    "value_provenance": {
                        "average_daily_amount": "OBSERVED_FACT",
                        "mark_price": "OBSERVED_FACT",
                        "price_limit_state": "OBSERVED_FACT",
                        "reference_price": "OBSERVED_FACT",
                        "trade_session": "ENGINEERING_ASSUMPTION",
                        "trading_status": "OBSERVED_FACT",
                    },
                    "risk_weight": None,
                    "risk_weight_provenance": None,
                    "reason_codes": sorted(reason_codes),
                    "score": (
                        None
                        if symbol not in selected
                        or selected[symbol].candidate_discovery_score is None
                        else str(selected[symbol].candidate_discovery_score)
                    ),
                }
            )
        receipt = build_portfolio_observation_receipt(
            research_trading_date=research_trading_date,
            trading_date=trading_date,
            observed_at=observed_at,
            policy=policy,
            values=tuple(sorted(values, key=lambda item: item.name)),
            source_references=self._context_references(context),
            observation_payload={"market_observations": market_observations},
        )
        return self._observations.publish(policy=policy, receipt=receipt)

    def _context(
        self,
        *,
        research_trading_date: date,
        lineage: ShadowOwnerLineageRequest,
    ) -> ShadowOwnerContext:
        decision = self._shadow.get_decision(
            lineage.decision_reference.artifact_id
        )
        if decision.decision_hash != lineage.decision_reference.content_hash:
            raise ValueError("Automatic Shadow Decision owner hash mismatch")
        panel = self._panels.replay(lineage.panel_reference.artifact_id)
        if panel.panel_hash != lineage.panel_reference.content_hash:
            raise ValueError("Automatic Shadow Panel owner hash mismatch")
        panel_slices = tuple(
            item
            for item in panel.slices
            if _same_reference(item.shadow_decision, lineage.decision_reference)
            and _same_reference(item.targeted_outcome, lineage.outcome_reference)
        )
        if len(panel_slices) != 1:
            raise ValueError("Automatic Shadow exact Panel slice is missing or ambiguous")
        panel_slice = panel_slices[0]
        outcome = self._targets.replay(lineage.outcome_reference.artifact_id)
        if outcome.settlement_hash != lineage.outcome_reference.content_hash:
            raise ValueError("Automatic Shadow Outcome owner hash mismatch")
        protocol = self._targets.get_protocol(outcome.target_protocol_id)
        if ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            protocol.protocol_id,
            protocol.protocol_hash,
        ) != lineage.target_protocol_reference:
            raise ValueError("Automatic Shadow Target Protocol owner mismatch")
        if not _same_reference(
            outcome.shadow_decision, lineage.decision_reference
        ):
            raise ValueError("Automatic Shadow Outcome/Decision lineage mismatch")
        if decision.trading_date != research_trading_date:
            raise ValueError("Automatic Shadow Outcome research date mismatch")
        candidate_set = self._state.get_runtime_candidate(
            run_id=decision.run_id,
            tick_id=decision.tick_id,
        )
        candidate_reference = ValidationArtifactReference(
            "CANDIDATE_SET",
            candidate_set.envelope.artifact_id,
            candidate_set.envelope.content_hash,
        )
        if candidate_reference != lineage.candidate_reference:
            raise ValueError("Automatic Shadow Candidate owner mismatch")
        enrichment = self._enrichment(
            lineage.enrichment_reference,
            panel_reference=lineage.panel_reference,
        )
        available_at = self._owner_available_at(lineage)
        return ShadowOwnerContext(
            decision,
            panel,
            panel_slice,
            candidate_set,
            outcome,
            protocol,
            enrichment,
            available_at,
        )

    def _owner_available_at(
        self,
        lineage: ShadowOwnerLineageRequest,
    ) -> datetime:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT 'SHADOW_DECISION', created_at
                FROM shadow_research_decision
                WHERE decision_id = %s AND decision_hash = %s
                UNION ALL
                SELECT 'RESEARCH_PANEL_V2', created_at
                FROM research_evaluation_panel_v2
                WHERE panel_id = %s AND panel_hash = %s
                UNION ALL
                SELECT 'CANDIDATE_SET', created_at
                FROM state_runtime_candidate_artifact
                WHERE candidate_id = %s AND candidate_hash = %s
                UNION ALL
                SELECT 'OUTCOME_TARGET_PROTOCOL', created_at
                FROM outcome_target_protocol
                WHERE protocol_id = %s AND protocol_hash = %s
                UNION ALL
                SELECT 'TARGETED_SHADOW_OUTCOME',
                       greatest(created_at, outcome_available_at)
                FROM targeted_shadow_outcome
                WHERE settlement_id = %s AND settlement_hash = %s
                UNION ALL
                SELECT 'PANEL_ENRICHMENT', created_at
                FROM research_validation_artifact
                WHERE artifact_kind = 'PANEL_ENRICHMENT'
                  AND artifact_id = %s AND artifact_hash = %s
                """,
                tuple(
                    value
                    for reference in (
                        lineage.decision_reference,
                        lineage.panel_reference,
                        lineage.candidate_reference,
                        lineage.target_protocol_reference,
                        lineage.outcome_reference,
                        lineage.enrichment_reference,
                    )
                    for value in (
                        str(reference.artifact_id),
                        reference.content_hash,
                    )
                ),
            ).fetchall()
        expected = {item.artifact_kind for item in lineage.references}
        if len(rows) != len(expected) or {str(row[0]) for row in rows} != expected:
            raise ValueError("Automatic Shadow owner availability chain is incomplete")
        return max(row[1] for row in rows)

    def _enrichment(
        self,
        reference: ValidationArtifactReference,
        *,
        panel_reference: ValidationArtifactReference,
    ) -> ResearchPanelEnrichment:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT artifact_id, artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_kind = 'PANEL_ENRICHMENT'
                  AND artifact_id = %s
                """,
                (str(reference.artifact_id),),
            ).fetchone()
            if row is None or not isinstance(row[2], dict):
                raise ValueError("Automatic Shadow Panel Enrichment owner is missing")
            enrichment = ResearchPanelEnrichment.from_canonical_dict(
                {
                    "enrichment_id": str(row[0]),
                    "enrichment_hash": str(row[1]),
                    **row[2],
                }
            )
            if (
                enrichment.enrichment_hash != reference.content_hash
                or enrichment.panel_reference != panel_reference
            ):
                raise ValueError("Automatic Shadow Panel Enrichment owner mismatch")
            exposure_rows = connection.execute(
                """
                SELECT exposure_json FROM research_panel_factor_exposure
                WHERE enrichment_id = %s
                ORDER BY symbol, factor_family, factor_id, timeframe,
                         exposure_json->>'source_value_path'
                """,
                (str(enrichment.enrichment_id),),
            ).fetchall()
        actual_exposures = tuple(row[0] for row in exposure_rows)
        expected_exposures = tuple(
            item.to_canonical_dict() for item in enrichment.exposures
        )
        if len(actual_exposures) != len(expected_exposures) or {
            canonical_hash(item) for item in actual_exposures
        } != {canonical_hash(item) for item in expected_exposures}:
            raise ValueError("Panel Enrichment owner projection diverged")
        return enrichment

    @staticmethod
    def _optional_label(
        context: ShadowOwnerContext,
        *,
        symbol: str,
        checkpoint: Any,
    ) -> Any | None:
        target_ids = {
            target.target_id
            for target in context.protocol.targets
            if target.checkpoint is checkpoint
        }
        matches = tuple(
            item
            for item in context.outcome.labels
            if item.symbol == symbol and item.target.artifact_id in target_ids
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Target Outcome checkpoint label is ambiguous")
        return matches[0]

    @staticmethod
    def _context_references(
        context: ShadowOwnerContext,
    ) -> tuple[ValidationArtifactReference, ...]:
        runtime_references = (
            context.panel_slice.market_state,
            context.panel_slice.etf_state,
            context.panel_slice.theme_state,
            context.panel_slice.capital_state,
            context.panel_slice.dynamic_pool,
            context.panel_slice.candidate_set,
            context.panel_slice.signal,
            context.panel_slice.forecast,
        )
        references = {
            ValidationArtifactReference(
                "SHADOW_DECISION",
                context.decision.decision_id,
                context.decision.decision_hash,
            ),
            ValidationArtifactReference(
                "RESEARCH_PANEL_V2",
                context.panel.panel_id,
                context.panel.panel_hash,
            ),
            ValidationArtifactReference(
                "TARGETED_SHADOW_OUTCOME",
                context.outcome.settlement_id,
                context.outcome.settlement_hash,
            ),
            ValidationArtifactReference(
                "OUTCOME_TARGET_PROTOCOL",
                context.protocol.protocol_id,
                context.protocol.protocol_hash,
            ),
            ValidationArtifactReference(
                "CANDIDATE_SET",
                context.candidate_set.envelope.artifact_id,
                context.candidate_set.envelope.content_hash,
            ),
            ValidationArtifactReference(
                "PANEL_ENRICHMENT",
                context.enrichment.enrichment_id,
                context.enrichment.enrichment_hash,
            ),
            *(
                ValidationArtifactReference(
                    getattr(item, "artifact_kind", None)
                    or getattr(item, "reference_kind"),
                    item.artifact_id,
                    item.content_hash,
                )
                for item in runtime_references
                if item is not None
            ),
        }
        return tuple(
            sorted(
                references,
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )


def _owner_value(
    name: str,
    value: Any,
    provenance: ShadowParameterProvenance,
    reference: ValidationArtifactReference,
    effective_at: datetime,
    available_at: datetime,
    source_value_path: str,
) -> OwnerObservationValue:
    if isinstance(value, Decimal):
        canonical_value: str | int | bool | None = str(value)
    elif value is None or isinstance(value, (str, int, bool)):
        canonical_value = value
    else:
        canonical_value = str(value)
    return OwnerObservationValue(
        name=name,
        value=canonical_value,
        provenance=provenance,
        source_reference=reference,
        effective_at=effective_at,
        available_at=available_at,
        source_value_path=source_value_path,
    )


def _label_reference(label: Any) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "TARGET_OUTCOME_LABEL",
        label.label_id,
        label.label_hash,
    )


def _same_reference(left: Any, right: Any) -> bool:
    return (
        getattr(left, "artifact_kind", getattr(left, "reference_kind", None))
        == getattr(right, "artifact_kind", getattr(right, "reference_kind", None))
        and left.artifact_id == right.artifact_id
        and left.content_hash == right.content_hash
    )


def _fill_blocked(label: Any) -> bool:
    blocked = {
        OutcomeMarketCondition.SUSPENDED,
        OutcomeMarketCondition.LIMIT_UP,
        OutcomeMarketCondition.MISSING_QUOTE,
        OutcomeMarketCondition.NON_TRADING_DAY,
        OutcomeMarketCondition.UNAVAILABLE,
    }
    return (
        label.availability_status is not OutcomeAvailabilityStatus.COMPLETE
        or label.checkpoint_price is None
        or bool(blocked.intersection(label.market_conditions))
    )


def _trading_status(
    conditions: set[OutcomeMarketCondition],
) -> TradingStatus:
    if OutcomeMarketCondition.SUSPENDED in conditions:
        return TradingStatus.SUSPENDED
    if OutcomeMarketCondition.TRADING in conditions:
        return TradingStatus.TRADING
    return TradingStatus.UNKNOWN


def _price_limit_state(
    conditions: set[OutcomeMarketCondition],
) -> PriceLimitState:
    if OutcomeMarketCondition.LIMIT_UP in conditions:
        return PriceLimitState.LIMIT_UP
    if OutcomeMarketCondition.LIMIT_DOWN in conditions:
        return PriceLimitState.LIMIT_DOWN
    if OutcomeMarketCondition.TRADING in conditions:
        return PriceLimitState.NORMAL
    return PriceLimitState.UNKNOWN


__all__ = [
    "PostgresOwnerResolvedShadowObservationBuilder",
    "PostgresShadowObservationRepository",
    "ShadowOwnerContext",
]
