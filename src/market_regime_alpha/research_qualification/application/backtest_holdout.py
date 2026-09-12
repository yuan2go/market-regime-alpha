"""Freeze one exploratory selection before the original Backtest can execute it."""

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
from typing import Any, Callable, cast
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.application._command_support import replay_concurrent_success, retry_transient_transaction, terminal_failure_boundary
from market_regime_alpha.research_qualification.application._results import ensure_replay_succeeded
from market_regime_alpha.research_qualification.application.backtest_execution import BacktestExecutionPlanner
from market_regime_alpha.research_qualification.application.historical_comparison import HistoricalComparisonApplication, HistoricalSpecificationReader
from market_regime_alpha.research_qualification.domain.backtest import BacktestSessionRole, BacktestSpecification, freeze_backtest_specification
from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestActionKind
from market_regime_alpha.research_qualification.domain.backtest_holdout import BacktestHoldoutOpening, BacktestHoldoutReservation
from market_regime_alpha.research_qualification.domain.historical_study import BASELINE_CANDIDATES
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan
from market_regime_alpha.research_qualification.domain.historical_rolling import HistoricalRollingPlan, ROBUSTNESS_CONTROLS
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.ports.backtest_holdout import BacktestHoldoutReadPort
from market_regime_alpha.research_qualification.ports.backtest_reports import BacktestReportArtifactPublisher
from market_regime_alpha.research_qualification.ports.backtest_uow import BacktestUnitOfWorkProvider
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.application import CommandContext, RuntimeCommandFailureRecorder
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError
from market_regime_alpha.runtime.ports import CommandFailureUnitOfWorkProvider
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class BacktestHoldoutMutation:
    reservation_id: UUID
    receipt_id: UUID
    result_hash: str
    replayed: bool
    fact: dict[str, Any]


class BacktestHoldoutApplication:
    def __init__(self, uow_provider: BacktestUnitOfWorkProvider, queries: BacktestHoldoutReadPort,
                 specifications: HistoricalSpecificationReader, comparison: HistoricalComparisonApplication,
                 artifacts: BacktestReportArtifactPublisher, byte_store: ResearchArtifactByteStore, *, id_factory: Callable[[], UUID]) -> None:
        self._uow_provider, self.queries, self._specifications = uow_provider, queries, specifications
        self._comparison, self._artifacts, self._id_factory = comparison, artifacts, id_factory
        self._byte_store = byte_store
        self._failure_recorder = RuntimeCommandFailureRecorder(cast(CommandFailureUnitOfWorkProvider, uow_provider), id_factory=id_factory)

    def reserve(self, request: BacktestHoldoutReservation, context: CommandContext) -> BacktestHoldoutMutation:
        self._verify_protocol(request)
        return self._mutate(request, context)

    def _read_artifact(self, artifact: ArtifactBinding) -> Any:
        verification = self._byte_store.verify(str(artifact.content_sha256), expected_size=artifact.size_bytes)
        if verification.result != "VERIFIED":
            raise ArtifactIntegrityError("holdout protocol Artifact bytes are not exact")
        return json.loads(self._byte_store.read_bytes(str(artifact.content_sha256), expected_size=artifact.size_bytes))

    def frozen_protocol(self, reservation_id: UUID) -> dict[str, Any]:
        reservation = self.queries.reservation(reservation_id)
        self._verify_protocol(reservation)
        return self._read_artifact(reservation.protocol_artifact)

    def _verify_protocol(self, reservation: BacktestHoldoutReservation) -> None:
        protocol = self._read_artifact(reservation.protocol_artifact)
        development = self._specifications.load_specification(reservation.development_run_id)
        config = self._read_artifact(development.config_artifact)
        if not isinstance(protocol, dict) or protocol.get("schema") not in {"mra-historical-campaign-boundary-v1", "mra-robustness-campaign-boundary-v2"}:
            raise ValueError("holdout requires the frozen finite historical campaign boundary")
        rolling = protocol["schema"] == "mra-robustness-campaign-boundary-v2"
        matrix = (HistoricalRollingPlan.from_bytes(json.dumps(protocol["development_plan"]).encode()) if rolling else
            HistoricalMatrixPlan.from_bytes(json.dumps(protocol["development_plan"]).encode()))
        controls = ROBUSTNESS_CONTROLS if rolling else BASELINE_CANDIDATES
        if rolling and (protocol.get("primary_point_metric") != "COMMON_VALIDATION_MAE" or protocol.get("primary_ordering_diagnostic") != "DAILY_RANK_IC"
                or protocol.get("historical_access_class") != "EXPLORATORY_TIME_ISOLATION_NOT_BLIND_PIT"
                or config.get("schema") != "mra-historical-rolling-freeze-v2"):
            raise ValueError("rolling holdout requires independently frozen point/rank objectives and exploratory access limits")
        expanded = tuple(candidate.name for candidate in matrix.ridge_candidates)
        if tuple(code for code in expanded if code in reservation.selection_arm_codes) != reservation.selection_arm_codes:
            raise ValueError("holdout selection must use the ordered frozen expanded Ridge candidates")
        expected_plan = json.loads(json.dumps(asdict(matrix), default=str))
        if (str(development.content_sha256) != reservation.development_specification_sha256
                or config["plan"] != expected_plan
                or protocol["holdout_time_split"] != reservation.payload()["time_split"]
                or protocol["future_holdout_study_code"] != reservation.future_study_code
                or tuple(protocol["selection"]["eligible_candidates"]) != reservation.selection_arm_codes
                or protocol["selection"]["metric"] != "ALL_ARM_COMMON_VALIDATION_MAE"
                or protocol["selection"]["tie_break"] != "PREDECLARED_ARM_ORDINAL"
                or protocol["selection"]["holdout_reselection_allowed"] is not False
                or tuple(protocol["selection"]["holdout_controls"]) != controls
                or protocol["selection"]["holdout_candidate_count"] != len(controls) + 1):
            raise RuntimeStateConflictError("holdout reservation differs from its physical frozen protocol and development plan")

    def select(self, reservation_id: UUID) -> dict[str, Any]:
        reservation = self.queries.reservation(reservation_id)
        self._verify_protocol(reservation)
        spec = self._specifications.load_specification(reservation.development_run_id)
        if str(spec.content_sha256) != reservation.development_specification_sha256:
            raise ArtifactIntegrityError("holdout development specification changed")
        projection = self._comparison.project(reservation.development_run_id)
        scores = {row["arm_code"]: row["common_population"]["pooled"]["model"]["mae"]["value"]
            for row in projection["statistics"]["arms"]}
        eligible = tuple(arm for arm in spec.arms if arm.arm_code in reservation.selection_arm_codes)
        if tuple(arm.arm_code for arm in eligible) != reservation.selection_arm_codes:
            raise ArtifactIntegrityError("holdout candidate roster differs from frozen selection protocol")
        if any(not isinstance(scores.get(arm.arm_code), Decimal) or not scores[arm.arm_code].is_finite() for arm in eligible):
            raise RuntimeStateConflictError("HOLDOUT_SELECTION_NOT_ESTIMABLE: at least one candidate lacks common-sample MAE")
        selected = min(eligible, key=lambda arm: (scores[arm.arm_code], arm.ordinal))
        return {"schema": "mra-backtest-holdout-selection-v1", "reservation_sha256": reservation.content_sha256,
            "selected_arm_id": selected.exploratory_backtest_arm_id, "selected_arm_code": selected.arm_code,
            "selected_mae": scores[selected.arm_code], "development_projection": projection,
            "development_evaluation_roster": self.queries.development_evaluation_roster(reservation.development_run_id),
            "authority": "FINITE_EXPLORATORY_SELECTION_NOT_MODEL_GOVERNANCE_QUALIFICATION"}

    def open(self, reservation_id: UUID, heldout_run_id: UUID, context: CommandContext) -> BacktestHoldoutMutation:
        reservation = self.queries.reservation(reservation_id)
        selection = self.select(reservation_id)
        development = self._specifications.load_specification(reservation.development_run_id)
        heldout = self._specifications.load_specification(heldout_run_id)
        self._validate_heldout(reservation, development, heldout, selection["selected_arm_code"])
        # All reporting, physical Artifact I/O and selection computation precede
        # the short owner transaction. Failure leaves an orphan Artifact only.
        content = (json.dumps(selection, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False) + "\n").encode()
        artifact = self._artifacts.publish(content, media_type="application/json", context=context)
        scopes = tuple(sorted(((uuid5(action.action_id, "evaluation-run"),uuid5(action.action_id,"research-partition"),
            uuid5(action.action_id,"experiment-run"),action.evaluation_requirement_id)
            for action in BacktestExecutionPlanner().compile(freeze_backtest_specification(heldout)).expected_actions
            if action.kind is BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION or
            (action.kind is BacktestActionKind.COMPLETE_FOLD_EVALUATION and any(
                fold.exploratory_backtest_fold_id == action.fold_id and fold.purpose.value == "VALIDATION" for fold in heldout.folds))), key=lambda row:str(row[0])))
        assert all(row[3] is not None for row in scopes)
        exact_scopes = cast(tuple[tuple[UUID,UUID,UUID,UUID],...],scopes)
        allowed = tuple(row[0] for row in exact_scopes)
        request = BacktestHoldoutOpening(reservation_id, reservation.content_sha256, heldout_run_id, str(heldout.content_sha256),
            selection["selected_arm_id"], selection["selected_arm_code"],
            selection["development_projection"]["projection_sha256"],
            ArtifactBinding(artifact.artifact_id, artifact.content_sha256, artifact.size_bytes), allowed, selection["development_evaluation_roster"], exact_scopes)
        return self._mutate(request, context)

    def _validate_heldout(self, reservation: BacktestHoldoutReservation, development: BacktestSpecification,
                         heldout: BacktestSpecification, selected_code: str) -> None:
        protocol = self.frozen_protocol(reservation.reservation_id)
        controls = ROBUSTNESS_CONTROLS if protocol["schema"] == "mra-robustness-campaign-boundary-v2" else BASELINE_CANDIDATES
        if (heldout.exploratory_backtest_run_id != reservation.future_run_id or heldout.run_code != reservation.future_study_code
                or heldout.market_archive != development.market_archive or heldout.market_archive_seal != development.market_archive_seal
                or heldout.target != development.target or heldout.feature_definitions != development.feature_definitions
                or heldout.random_seed != development.random_seed
                or tuple(m.instrument_id for m in heldout.sample_members) != tuple(m.instrument_id for m in development.sample_members)
                or tuple(arm.arm_code for arm in heldout.arms) != (*controls, selected_code)
                or heldout.defaults != development.defaults
                or heldout.eligibility_policy != development.eligibility_policy):
            raise RuntimeStateConflictError("holdout changed the reserved population, Target, Features, policies or selected candidate")
        if len(heldout.folds) != 2 or tuple(fold.purpose.value for fold in heldout.folds) != ("FIT", "VALIDATION"):
            raise RuntimeStateConflictError("holdout requires exactly its original FIT and validation folds")
        split = reservation.time_split
        for role, days in ((BacktestSessionRole.FIT_INPUT, split.fit_dates), (BacktestSessionRole.PURGE, split.purge_dates),
                           (BacktestSessionRole.EMBARGO, split.embargo_dates), (BacktestSessionRole.EVALUATION, split.validation_dates)):
            if tuple(s.session_date for fold in heldout.folds for s in fold.sessions if s.role is role) != days:
                raise RuntimeStateConflictError("holdout altered its frozen Calendar window")
        originals = {arm.arm_code: arm for arm in development.arms}
        for arm in heldout.arms:
            previous = originals[arm.arm_code]
            policy_fields = ("execution_kind", "comparison_role", "context_mode", "candidate", "context", "strategy", "portfolio", "risk",
                "candidate_binding_source", "context_binding_source", "strategy_binding_source", "portfolio_binding_source", "risk_binding_source", "cost_binding_source")
            if any(getattr(arm, field) != getattr(previous, field) for field in policy_fields):
                raise RuntimeStateConflictError("holdout changed an effective arm execution policy")
            def costs(spec: BacktestSpecification, arm_id: UUID) -> tuple[tuple[Any, ...], ...]:
                return tuple((c.cost_kind,c.charge_side,c.amount_bps,c.arm_id is not None) for c in spec.cost_assumptions
                    if c.arm_id is None or c.arm_id == arm_id)
            if costs(heldout,arm.exploratory_backtest_arm_id) != costs(development,previous.exploratory_backtest_arm_id):
                raise RuntimeStateConflictError("holdout changed effective arm costs")
            for requirement in heldout.evaluation_requirements:
                if requirement.arm_id != arm.exploratory_backtest_arm_id:
                    continue
                purpose = None if requirement.fold_id is None else next(f.purpose for f in heldout.folds if f.exploratory_backtest_fold_id==requirement.fold_id)
                original_requirements = tuple(r for r in development.evaluation_requirements if r.arm_id==previous.exploratory_backtest_arm_id
                    and r.scope_kind==requirement.scope_kind and (purpose is None or any(f.exploratory_backtest_fold_id==r.fold_id and f.purpose==purpose for f in development.folds)))
                if not original_requirements or any((r.evaluation_protocol,r.primary,r.slice_key)!=(requirement.evaluation_protocol,requirement.primary,requirement.slice_key) for r in original_requirements):
                    raise RuntimeStateConflictError("holdout changed the exact Evaluation protocol or scope semantics")
            if arm.model is None or previous.model is None:
                if arm.model != previous.model:
                    raise RuntimeStateConflictError("holdout changed rule/Model execution kind")
                continue
            if self.queries.model_features(arm.model.authority_id) != self.queries.model_features(previous.model.authority_id):
                raise RuntimeStateConflictError("holdout changed the selected Model feature order or identity")
            old_recipes = tuple(r.recipe for r in development.model_training_requirements if r.model_arm_id == previous.exploratory_backtest_arm_id)
            new_recipes = tuple(r.recipe for r in heldout.model_training_requirements if r.model_arm_id == arm.exploratory_backtest_arm_id)
            if not old_recipes or len(new_recipes) != 1:
                raise RuntimeStateConflictError("holdout requires exactly one fresh training recipe per Model")
            if any(r.training_metric != development.model_training_requirements[0].training_metric for r in heldout.model_training_requirements):
                raise RuntimeStateConflictError("holdout changed its FIT training metric")
            for recipe in (*old_recipes, *new_recipes):
                original = old_recipes[0]
                if recipe is None or original is None or (
                    recipe.algorithm_code, recipe.algorithm_version, recipe.implementation_sha256, recipe.hyperparameters, recipe.environment.uv_lock_sha256
                ) != (original.algorithm_code, original.algorithm_version, original.implementation_sha256, original.hyperparameters, original.environment.uv_lock_sha256):
                    raise RuntimeStateConflictError("holdout changed the selected algorithm, parameters or locked dependencies")

    @retry_transient_transaction
    @replay_concurrent_success
    def _mutate(self, request: BacktestHoldoutReservation | BacktestHoldoutOpening, context: CommandContext) -> BacktestHoldoutMutation:
        opening = isinstance(request, BacktestHoldoutOpening)
        operation = "OPEN_BACKTEST_HOLDOUT" if opening else "RESERVE_BACKTEST_HOLDOUT"
        with terminal_failure_boundary(self._failure_recorder, operation=operation, scope_id=str(request.reservation_id),
                request_hash=request.content_sha256, error_class="COMMAND", error_code=operation + "_REJECTED", context=context, runtime_claim=None):
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(receipt_id=self._id_factory(), command_kind=operation,
                    scope_id=str(request.reservation_id), idempotency_key=context.idempotency_key, request_hash=request.content_sha256)
                if not receipt.is_new:
                    ensure_replay_succeeded(receipt)
                    if (receipt.result_aggregate_kind != ("BACKTEST_HOLDOUT_OPENING" if opening else "BACKTEST_HOLDOUT_RESERVATION")
                            or receipt.result_aggregate_id != str(request.reservation_id)
                            or receipt.result_aggregate_version != 1):
                        raise ArtifactIntegrityError("holdout Receipt aggregate identity differs")
                    fact = uow.holdouts.record(request.reservation_id, opening=opening)
                    if canonical_json_sha256(fact) != receipt.result_hash:
                        raise ArtifactIntegrityError("holdout Receipt and owner fact differ")
                    return BacktestHoldoutMutation(request.reservation_id, receipt.receipt_id, str(receipt.result_hash), True, fact)
                uow.artifacts.require_exact(request.selection_artifact if isinstance(request, BacktestHoldoutOpening) else request.protocol_artifact, lock=True)
                fact = uow.holdouts.open(request) if isinstance(request, BacktestHoldoutOpening) else uow.holdouts.reserve(request)
                result_hash = canonical_json_sha256(fact)
                uow.receipts.succeed(receipt_id=receipt.receipt_id, aggregate_kind="BACKTEST_HOLDOUT_OPENING" if opening else "BACKTEST_HOLDOUT_RESERVATION",
                    aggregate_id=str(request.reservation_id), aggregate_version=1, result_hash=result_hash)
                uow.audit.append(audit_event_id=self._id_factory(), receipt_id=receipt.receipt_id,
                    actor_type=context.actor_type.value, actor_id=context.actor_id, aggregate_kind="BACKTEST_HOLDOUT",
                    aggregate_id=str(request.reservation_id), action=operation, reason_code=context.reason_code, before_version=None, after_version=1)
                uow.commit()
                return BacktestHoldoutMutation(request.reservation_id, receipt.receipt_id, result_hash, False, fact)
