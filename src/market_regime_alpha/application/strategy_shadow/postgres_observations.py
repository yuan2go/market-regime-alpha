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
    ShadowObservationPolicy,
    ShadowObservationReceipt,
    build_observation_receipt,
    build_portfolio_observation_receipt,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
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
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PostgresShadowObservationRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
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


@dataclass(frozen=True, slots=True)
class _OwnerContext:
    decision: Any
    panel: Any
    panel_slice: Any
    candidate_set: Any
    outcome: Any
    protocol: Any
    enrichment: ResearchPanelEnrichment


class PostgresOwnerResolvedShadowObservationBuilder:
    """Reload current fact owners and publish replayable automatic inputs."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
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

    def build_strategy(
        self,
        *,
        research_trading_date: date,
        observed_at: datetime,
        policy: ShadowObservationPolicy,
        symbol: str | None = None,
    ) -> ShadowObservationReceipt:
        context = self._context(research_trading_date)
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
            "TARGETED_OUTCOME",
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
                        context.decision.decision_time
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
                        context.decision.decision_time
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
                        context.decision.decision_time
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
                        context.decision.decision_time
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
                        context.decision.decision_time
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
        required_symbols: tuple[str, ...] = (),
    ) -> ShadowObservationReceipt:
        context = self._context(research_trading_date)
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
                "TARGETED_OUTCOME",
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
            effective = context.decision.decision_time
            fill_available = (
                context.decision.decision_time
                if fill_label is None
                else fill_label.outcome_available_at
            )
            mark_available = (
                context.decision.decision_time
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
                    fill_available,
                ),
                (
                    "mark_price",
                    None if mark_label is None else mark_label.checkpoint_price,
                    mark_ref,
                    mark_available,
                ),
                (
                    "average_daily_amount",
                    None if adv is None else adv.raw_numeric,
                    adv_ref,
                    context.decision.decision_time if adv is None or adv.available_at is None else adv.available_at,
                ),
                (
                    "trading_status",
                    None if trading_status is TradingStatus.UNKNOWN else trading_status.value,
                    fill_ref,
                    fill_available,
                ),
                (
                    "price_limit_state",
                    None if limit_state is PriceLimitState.UNKNOWN else limit_state.value,
                    fill_ref,
                    fill_available,
                ),
            )
            for name, value, reference, available_at in observed_values:
                values.append(
                    _owner_value(
                        f"{symbol}.{name}",
                        value,
                        ShadowParameterProvenance.OBSERVED_FACT,
                        reference,
                        effective,
                        available_at,
                        name,
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

    def _context(self, trading_date: date) -> _OwnerContext:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT decision.decision_id, panel.panel_id,
                       slice.targeted_outcome_id
                FROM shadow_research_decision AS decision
                JOIN shadow_research_session AS shadow
                  ON shadow.session_id = decision.session_id
                JOIN research_evaluation_panel_slice_v2 AS slice
                  ON slice.shadow_decision_id = decision.decision_id
                JOIN research_evaluation_panel_v2 AS panel
                  ON panel.panel_id = slice.panel_id
                WHERE shadow.trading_date = %s
                  AND shadow.status = 'SETTLED'
                ORDER BY panel.created_at DESC, panel.panel_id DESC
                """,
                (trading_date,),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError(
                "Automatic Shadow observation requires exactly one settled Panel"
            )
        decision = self._shadow.get_decision(ArtifactId(str(rows[0][0])))
        panel = self._panels.replay(ArtifactId(str(rows[0][1])))
        panel_slices = tuple(
            item for item in panel.slices if item.shadow_decision.artifact_id == decision.decision_id
        )
        if len(panel_slices) != 1:
            raise ValueError("Automatic Shadow observation Panel slice is ambiguous")
        panel_slice = panel_slices[0]
        outcome = self._targets.replay(ArtifactId(str(rows[0][2])))
        protocol = self._targets.get_protocol(outcome.target_protocol_id)
        candidate_set = self._state.get_runtime_candidate(
            run_id=decision.run_id,
            tick_id=decision.tick_id,
        )
        enrichment = self._enrichment(panel.panel_id, panel.panel_hash)
        return _OwnerContext(
            decision,
            panel,
            panel_slice,
            candidate_set,
            outcome,
            protocol,
            enrichment,
        )

    def _enrichment(
        self,
        panel_id: ArtifactId,
        panel_hash: str,
    ) -> ResearchPanelEnrichment:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_kind = 'PANEL_ENRICHMENT'
                  AND payload_json->'panel_reference'->>'artifact_id' = %s
                  AND payload_json->'panel_reference'->>'content_hash' = %s
                ORDER BY created_at DESC, artifact_id DESC
                """,
                (str(panel_id), panel_hash),
            ).fetchall()
            if len(rows) != 1 or not isinstance(rows[0][2], dict):
                raise ValueError(
                    "Automatic Shadow observation requires one Panel Enrichment owner"
                )
            enrichment = ResearchPanelEnrichment.from_canonical_dict(
                {
                    "enrichment_id": str(rows[0][0]),
                    "enrichment_hash": str(rows[0][1]),
                    **rows[0][2],
                }
            )
            exposure_rows = connection.execute(
                """
                SELECT exposure_json FROM research_panel_factor_exposure
                WHERE enrichment_id = %s
                ORDER BY symbol, factor_family, factor_id, timeframe,
                         exposure_json->>'source_value_path'
                """,
                (str(enrichment.enrichment_id),),
            ).fetchall()
        if [row[0] for row in exposure_rows] != [
            item.to_canonical_dict() for item in enrichment.exposures
        ]:
            raise ValueError("Panel Enrichment owner projection diverged")
        return enrichment

    @staticmethod
    def _optional_label(
        context: _OwnerContext,
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
        context: _OwnerContext,
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
                "TARGETED_OUTCOME",
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
                    item.artifact_kind,
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
]
