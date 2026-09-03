"""Resumable operator operations for the WP-17P exploratory pilot.

Every mutation is delegated to the canonical owning Application command.  This
module only coordinates typed identities and materializes immutable bytes
outside business transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.bootstrap import TargetApplication
from market_regime_alpha.interfaces.wp17p_authorities import Wp17pAuthorityCatalog
from market_regime_alpha.interfaces.wp17p_research import (
    Wp17pDatasetMember,
    Wp17pFeatureLineageKind,
    materialize_wp17p_dataset,
)
from market_regime_alpha.research_qualification.domain import (
    ArtifactBinding,
    FeatureCellStatus,
    TargetCheckpointRole,
    TargetTimingRule,
)
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    ExploratoryBacktestDatasetScope,
)
from market_regime_alpha.research_qualification.ports import (
    ExploratoryIntradayFeatureGap,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.selection.domain import (
    ExploratoryRetrospectiveSelectionScope,
    UniverseMembershipStatus,
    UniverseScopeSpecification,
)
from market_regime_alpha.selection.domain.vocabulary import EligibilityStatus
from market_regime_alpha.shared.identity import InstrumentId


@dataclass(frozen=True, slots=True)
class Wp17pDatasetAuthority:
    dataset_id: UUID
    universe_revision_id: UUID
    eligible_count: int
    available_feature_count: int
    unavailable_feature_count: int
    retrospective_scope: ExploratoryRetrospectiveDatasetScope
    backtest_scope: ExploratoryBacktestDatasetScope


class Wp17pResearchOperations:
    """Controlled interface; not a new business Authority or UoW."""

    def __init__(self, application: TargetApplication) -> None:
        self._application = application

    def register_catalog(self, catalog: Wp17pAuthorityCatalog) -> None:
        app = self._application
        app.research_definitions.register_target_definition(
            catalog.target,
            _context("register-target"),
        )
        app.research_definitions.register_feature_definition(
            catalog.feature,
            _context("register-feature"),
        )
        app.selection.register_universe(
            catalog.universe,
            _context("register-universe"),
        )
        app.selection.register_eligibility_policy(
            catalog.eligibility_policy,
            _context("register-eligibility"),
        )
        app.candidates.register_candidate_policy(
            catalog.candidate_policy,
            _context("register-candidate-policy"),
        )
        app.decision_contexts.register_policy(
            catalog.context_policy,
            _context("register-context-policy"),
        )
        app.decision_strategies.register(
            catalog.strategy,
            _context("register-strategy"),
        )
        app.decision_portfolios.register_policy(
            catalog.portfolio_policy,
            _context("register-portfolio-policy"),
        )
        app.decision_risk.register_policy(
            catalog.risk_policy,
            _context("register-risk-policy"),
        )
        app.research_evaluations.register_protocol(
            catalog.fit_evaluation_protocol,
            _context("register-fit-evaluation"),
        )
        app.research_evaluations.register_protocol(
            catalog.validation_evaluation_protocol,
            _context("register-validation-evaluation"),
        )
        app.exploratory_backtests.register(
            catalog.backtest,
            _context("register-backtest"),
        )

    def materialize_dataset(
        self,
        *,
        catalog: Wp17pAuthorityCatalog,
        pilot_instrument_ids: tuple[InstrumentId, ...],
        exploratory_backtest_arm_id: UUID,
        exploratory_backtest_fold_id: UUID,
        exploratory_backtest_fold_session_id: UUID,
    ) -> Wp17pDatasetAuthority:
        app = self._application
        if exploratory_backtest_arm_id not in {
            item.exploratory_backtest_arm_id for item in catalog.backtest.arms
        }:
            raise ValueError("Dataset arm is not declared by the backtest")
        fold_sessions = tuple(
            item
            for fold in catalog.backtest.folds
            for item in fold.sessions
            if item.exploratory_backtest_fold_session_id
            == exploratory_backtest_fold_session_id
            and fold.exploratory_backtest_fold_id == exploratory_backtest_fold_id
        )
        if len(fold_sessions) != 1:
            raise ValueError("Dataset fold session is not uniquely declared by the backtest")
        fold_session = fold_sessions[0]
        archive = app.archive_inspection.inspect(catalog.backtest.market_archive_id)
        if (
            archive.seal_id != catalog.backtest.market_archive_seal_id
            or archive.sealed_at is None
            or archive.lane != "RETROSPECTIVE_BACKFILL"
            or archive.evidence_class != "EXPLORATORY_RETROSPECTIVE"
        ):
            raise ValueError("backtest Archive is not the exact sealed retrospective Authority")
        simulated = next(
            item
            for item in app.archive_trading_sessions.sessions(
                exchange="XSHG",
                start_date=fold_session.session_date,
                end_date=fold_session.session_date,
            )
            if item.session_id.value == fold_session.trading_session_id
        )
        references = tuple(
            checkpoint
            for checkpoint in catalog.target.checkpoints
            if checkpoint.role is TargetCheckpointRole.DECISION_REFERENCE
        )
        if len(references) != 1:
            raise ValueError("WP-17P Target requires one Decision reference")
        reference = references[0]
        if reference.timing_rule is not TargetTimingRule.SESSION_LOCAL_BAR_END:
            raise ValueError("WP-17P Target requires a session-local Decision reference")
        simulated_cutoff = datetime.combine(
            simulated.session_date,
            reference.local_time,
            ZoneInfo(reference.timezone_name),
        )
        selection_scope = ExploratoryRetrospectiveSelectionScope(
            catalog.backtest.market_archive_id,
            catalog.backtest.market_archive_seal_id,
            archive.sealed_at,
            simulated_cutoff,
        )
        dataset_scope = ExploratoryRetrospectiveDatasetScope(
            catalog.backtest.market_archive_id,
            catalog.backtest.market_archive_seal_id,
            archive.sealed_at,
            simulated_cutoff,
        )
        instruments = tuple(sorted(set(pilot_instrument_ids), key=str))
        if len(instruments) != 32:
            raise ValueError("Dataset must use the exact deterministic 32-instrument scope")
        scope_content = json.dumps(
            {
                "classification_code": "CSI300",
                "classification_scheme": "INDEX_MEMBERSHIP",
                "instrument_ids": [str(item) for item in instruments],
                "market_provider_product_id": str(
                    catalog.eligibility_policy.market_provider_product_id
                ),
                "schema": "selection-universe-scope-v1",
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        scope_artifact = app.artifacts.publish(
            scope_content,
            media_type="application/json",
            context=_context(f"scope-{fold_session.session_date:%Y%m%d}"),
        )
        universe_scope = UniverseScopeSpecification(
            scope_artifact.artifact_id,
            scope_artifact.content_sha256,
            scope_artifact.size_bytes,
            catalog.eligibility_policy.market_provider_product_id,
            "INDEX_MEMBERSHIP",
            "CSI300",
            instruments,
        )
        frozen = app.selection.freeze_exploratory_retrospective_universe(
            universe_id=catalog.universe.universe_id,
            scope=universe_scope,
            retrospective_scope=selection_scope,
            context=_context(
                f"freeze-{fold_session.session_date:%Y%m%d}"
            ),
        )
        assessed = app.selection.assess_exploratory_retrospective_eligibility(
            universe_revision_id=frozen.universe_revision_id,
            eligibility_policy_id=catalog.eligibility_policy.eligibility_policy_id,
            retrospective_scope=selection_scope,
            context=_context(
                f"eligibility-{fold_session.session_date:%Y%m%d}"
            ),
        )
        member_by_id = {
            item.universe_member_id: item
            for item in frozen.members
            if item.membership_status is UniverseMembershipStatus.INCLUDED
        }
        population = tuple(
            item
            for item in assessed.assessments
            if item.result is EligibilityStatus.ELIGIBLE
            and item.universe_member_id in member_by_id
        )
        if not population:
            raise ValueError("retrospective Selection produced no eligible population")
        dataset_members: list[Wp17pDatasetMember] = []
        for item in population:
            feature = app.exploratory_feature_inputs.exact_intraday_move(
                scope=dataset_scope,
                instrument_id=item.instrument_id,
                session_id=simulated.session_id,
                feature_event_end=simulated.close_at - timedelta(minutes=5),
            )
            if isinstance(feature, ExploratoryIntradayFeatureGap):
                status = {
                    "MISSING": FeatureCellStatus.MISSING,
                    "PLACEHOLDER": FeatureCellStatus.MISSING,
                    "PROVIDER_FAILURE": FeatureCellStatus.UNKNOWN,
                    "CONFLICT": FeatureCellStatus.CONFLICT,
                    "INVALID_OHLC": FeatureCellStatus.CONFLICT,
                }[feature.gap_kind]
                dataset_members.append(
                    Wp17pDatasetMember(
                        item.instrument_id.value,
                        item.universe_member_id,
                        item.eligibility_assessment_id,
                        status,
                        f"ARCHIVE_{feature.reason_code}",
                        Wp17pFeatureLineageKind.SOURCE_GAP,
                        feature.gap_id,
                        None,
                    )
                )
            else:
                dataset_members.append(
                    Wp17pDatasetMember(
                        item.instrument_id.value,
                        item.universe_member_id,
                        item.eligibility_assessment_id,
                        FeatureCellStatus.AVAILABLE,
                        "EXACT_ARCHIVED_BAR",
                        Wp17pFeatureLineageKind.BAR_REVISION,
                        feature.bar_revision_id,
                        feature.intraday_move,
                    )
                )
        dataset_id = uuid5(
            catalog.backtest.exploratory_backtest_run_id,
            (
                f"dataset:{exploratory_backtest_arm_id}:"
                f"{exploratory_backtest_fold_session_id}"
            ),
        )
        materialized = materialize_wp17p_dataset(
            dataset_id=dataset_id,
            dataset_code=(
                f"wp17p_{str(exploratory_backtest_arm_id)[:8]}_"
                f"{fold_session.session_date:%Y%m%d}"
            ),
            simulated_decision_time=simulated_cutoff,
            universe_revision_id=frozen.universe_revision_id,
            eligibility_policy_id=catalog.eligibility_policy.eligibility_policy_id,
            feature_definition_id=catalog.feature.feature_definition_id,
            code_artifact=catalog.backtest.code_artifact,
            config_artifact=catalog.backtest.config_artifact,
            members=tuple(dataset_members),
        )
        manifest = app.artifacts.publish(
            materialized.manifest_content,
            media_type="application/json",
            context=_context(f"dataset-manifest-{dataset_id}"),
        )
        backtest_scope = ExploratoryBacktestDatasetScope(
            dataset_scope,
            catalog.backtest.exploratory_backtest_run_id,
            exploratory_backtest_arm_id,
            exploratory_backtest_fold_id,
            exploratory_backtest_fold_session_id,
        )
        app.research_definitions.register_exploratory_backtest_dataset(
            materialized.definition(_artifact(manifest)),
            backtest_scope,
            _context(f"register-dataset-{dataset_id}"),
        )
        return Wp17pDatasetAuthority(
            dataset_id,
            frozen.universe_revision_id,
            len(population),
            materialized.available_count,
            materialized.unavailable_count,
            dataset_scope,
            backtest_scope,
        )


def _artifact(record: ArtifactRecord) -> ArtifactBinding:
    return ArtifactBinding(
        record.artifact_id,
        record.content_sha256,
        record.size_bytes,
    )


def _id(suffix: str) -> UUID:
    return uuid5(UUID("e17baaca-c189-5c07-a54c-9c6754c5d622"), suffix)


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        idempotency_key=f"wp17p:{suffix}",
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-pilot-operator",
        reason_code="WP17P_EXPLORATORY_PILOT",
    )


__all__ = ["Wp17pDatasetAuthority", "Wp17pResearchOperations"]
