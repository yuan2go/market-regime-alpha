"""Real PostgreSQL holdout owner/Runtime contracts over explicit synthetic data.

Only the build attestation is stubbed; separate installed-wheel evidence tests
the real package. No synthetic result is historical model-value evidence.
"""

from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

import psycopg
import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.interfaces import historical_study as study
from market_regime_alpha.interfaces.historical_study_build import HistoricalBuild
from market_regime_alpha.research_qualification.application.backtest_execution import BacktestExecutionPlanner
from market_regime_alpha.research_qualification.domain.backtest import freeze_backtest_specification
from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestActionKind, BacktestNextOperation, BacktestExecutionBudget
from market_regime_alpha.research_qualification.domain.backtest_holdout import BacktestHoldoutOpening, BacktestHoldoutReservation
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan, HistoricalTimeSplit, HistoricalRidgeCandidate
from market_regime_alpha.research_qualification.domain.historical_study import BASELINE_CANDIDATES, HistoricalStudyPlan
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeStateConflictError
from tests.contracts.research_qualification.archive_campaign_fixture import _context
from tests.contracts.research_qualification.daily_campaign_fixture import daily_baseline


@pytest.mark.parametrize("all_session_facts",[False,True])
def test_holdout_reservation_opening_recovery_and_cross_identity_label_guards(target_database_url, tmp_path, monkeypatch, all_session_facts):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    content = b"explicit synthetic engineering build; never historical research evidence"
    build = HistoricalBuild(content, sha256(content).hexdigest(), "1"*64, "2"*64, "3"*64, "0.1.0", "0.8.15")
    monkeypatch.setattr(study, "verify_historical_build", lambda **_: build)
    with bootstrap_application(settings) as app:
        def resume(specification):
            from market_regime_alpha.research_qualification.errors import BacktestExecutionIntegrityError
            frozen=freeze_backtest_specification(specification)
            try:
                return app.backtest_execution.resume(frozen)
            except BacktestExecutionIntegrityError:
                observed=app.backtest_execution.inspect(frozen)
                print("HOLDOUT_TEST_FIRST_OWNER_MISMATCH",[(a.kind.value,str(a.action_id),str(a.arm_id),str(a.fold_id))
                    for a in observed.expected_actions if a.action_id in observed.integrity_mismatch_action_ids])
                print("HOLDOUT_TEST_REPLAY",app.backtest_replay.verify(specification.exploratory_backtest_run_id))
                raise
        template, catalog = daily_baseline(app, archive_exchange="XSHG", mixed_daily_bars=True, all_session_facts=all_session_facts)
        app.backtests.predeclare(template, _context("holdout-template"))
        def prepare(code, split, reuse=None):
            plan = HistoricalStudyPlan(code, template.exploratory_backtest_run_id, str(template.definition_sha256),
                template.market_archive.authority_id, str(template.market_archive.content_sha256),
                template.market_archive_seal.authority_id, str(template.market_archive_seal.content_sha256),
                split.fit_dates, split.purge_dates, split.embargo_dates, split.validation_dates,
                tuple(sorted((i.value for i in catalog["instruments"]), key=str)))
            matrix = HistoricalMatrixPlan(plan, (), (HistoricalRidgeCandidate("ridge_intraday", ("intraday",), Decimal(1)),))
            output = tmp_path / code
            output.mkdir()
            result = study.prepare_study(app, plan, matrix=matrix, wheel=Path("fixture.whl"), lockfile=Path("fixture.lock"),
                source_checkout=tmp_path, code_sha="a"*40, output=output, actor_id="fixture", reuse_contracts_from=reuse)
            return app.backtest_specifications.load_specification(UUID(str(result["run_id"]))), matrix

        development_split = HistoricalTimeSplit((date(2026,1,5),), (date(2026,1,6),), (date(2026,1,7),), (date(2026,1,8),))
        heldout_split = HistoricalTimeSplit((date(2026,1,9),), (date(2026,1,12),), (date(2026,1,13),), (date(2026,1,14),))
        development, matrix = prepare("holdout_development", development_split)
        plan = json.loads(json.dumps(asdict(matrix), default=str))
        plan.update(schema="mra-historical-matrix-v1")
        plan["baseline"]["schema"] = "mra-historical-study-v1"
        protocol = {"schema":"mra-historical-campaign-boundary-v1", "development_plan":plan,
            "holdout_time_split":json.loads(json.dumps(asdict(heldout_split),default=str)),
            "future_holdout_study_code":"holdout_selected",
            "selection":{"eligible_candidates":["ridge_intraday"],"metric":"ALL_ARM_COMMON_VALIDATION_MAE",
                "tie_break":"PREDECLARED_ARM_ORDINAL","holdout_reselection_allowed":False,
                "holdout_controls":list(BASELINE_CANDIDATES),"holdout_candidate_count":8}}
        artifact = app.artifacts.publish(study._json(protocol), media_type="application/json", context=_context("holdout-protocol"))
        future_id = uuid5(uuid5(NAMESPACE_URL,"mra:historical-study:holdout_selected"),"backtest")
        request = BacktestHoldoutReservation(uuid4(), development.exploratory_backtest_run_id, str(development.content_sha256),
            future_id, "holdout_selected", heldout_split, ("ridge_intraday",),
            ArtifactBinding(artifact.artifact_id,artifact.content_sha256,artifact.size_bytes))
        with pytest.raises(ValueError,match="expanded Ridge candidates"):
            app.backtest_holdouts.reserve(replace(request,selection_arm_codes=("zero",)),_context("reject-control-selection"))
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT count(*) FROM mra.backtest_holdout_reservation").fetchone()==(0,)
        first = app.backtest_holdouts.reserve(request, _context("reserve-holdout"))
        assert app.backtest_holdouts.reserve(request, _context("reserve-holdout")).replayed
        assert first.fact["body"] == request.payload()
        heldout, _ = prepare("holdout_selected", heldout_split, development.exploratory_backtest_run_id)
        blocked = app.backtest_execution.run(freeze_backtest_specification(heldout))
        assert blocked.execution_blockers and not blocked.ready_actions and blocked.expected_actions
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT count(*) FROM mra.backtest_runtime_binding WHERE exploratory_backtest_run_id=%s",(future_id,)).fetchone()==(0,)

        # A new Run and Target cannot obtain the same economic label window.
        clone, _ = prepare("holdout_clone", heldout_split)
        cloned = freeze_backtest_specification(clone)
        expected = BacktestExecutionPlanner().compile(cloned).expected_actions
        rule = clone.arms[0].exploratory_backtest_arm_id
        validation = clone.folds[1].exploratory_backtest_fold_id
        actions = tuple(a for a in expected if a.arm_id==rule and a.fold_id==validation)
        for action in actions:
            if action.kind in {BacktestActionKind.MATERIALIZE_DATASET, BacktestActionKind.GENERATE_DECISION_SUPPORT}:
                app.backtest_execution._actions.execute(cloned, action, BacktestNextOperation.EXECUTE)
        outcome = next(a for a in actions if a.kind is BacktestActionKind.SETTLE_OUTCOME)
        from market_regime_alpha.infrastructure.postgres.queries import outcome_inputs
        def forbidden_label_read(*args, **kwargs):
            raise AssertionError("reserved label sources were read")
        with monkeypatch.context() as patch:
            patch.setattr(outcome_inputs, "_load_sources", forbidden_label_read)
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="EXPLORATORY_HOLDOUT_ACCESS_BLOCKED"):
                app.backtest_execution._actions.execute(cloned, outcome, BacktestNextOperation.EXECUTE)
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT count(*) FROM mra.market_target_outcome outcome JOIN mra.decision_run decision USING(decision_run_id) "
                "JOIN mra.exploratory_backtest_dataset dataset ON dataset.dataset_id=decision.dataset_id "
                "WHERE dataset.exploratory_backtest_run_id=%s",(clone.exploratory_backtest_run_id,)).fetchone()==(0,)

        started = app.backtest_execution.run(freeze_backtest_specification(development), budget=BacktestExecutionBudget(2,300))
        assert started.execution_state.value=="RUNNING"
        assert resume(development).execution_state.value=="COMPLETED"
        if not all_session_facts:
            with app._pool.connection(read_only=True) as c:
                assert c.execute("""SELECT sum(decision.commitment_count) FROM mra.exploratory_retrospective_decision_run backtest
                    JOIN mra.decision_run decision USING(decision_run_id)
                    JOIN mra.exploratory_backtest_fold fold USING(exploratory_backtest_fold_id)
                    WHERE backtest.exploratory_backtest_run_id=%s AND fold.purpose='VALIDATION'""",
                    (development.exploratory_backtest_run_id,)).fetchone()==(0,)
                empty_group=c.execute("""SELECT forecast.forecast_group_id FROM mra.forecast_run forecast
                    JOIN mra.command_receipt receipt ON receipt.receipt_id=forecast.command_receipt_id
                    WHERE forecast.forecast_count=0 AND receipt.command_kind='PRODUCE_MODEL_SIGNAL_AND_FORECAST'
                    LIMIT 1""").fetchone()[0]
            from market_regime_alpha.infrastructure.postgres.queries.model_forecast_inputs import PostgresModelForecastQueryProvider
            from market_regime_alpha.infrastructure.postgres.repositories.model_forecasts import PostgresModelForecastRepository
            from market_regime_alpha.decision_support.errors import InferenceAuthorityIntegrityError
            summary=PostgresModelForecastQueryProvider(app._pool).summary(empty_group)
            assert summary is not None and summary.binding_count==0
            with app._pool.connection(read_only=True) as c:
                repository=PostgresModelForecastRepository(c)
                assert repository.reconcile(empty_group,summary.model_version_id,lock=False).matched
                with pytest.raises(InferenceAuthorityIntegrityError,match="absent or differs"):
                    repository.reconcile(empty_group,uuid4(),lock=False)
                with pytest.raises(InferenceAuthorityIntegrityError,match="absent or differs"):
                    repository.reconcile(uuid4(),summary.model_version_id,lock=False)
            assert app.backtest_replay.verify(development.exploratory_backtest_run_id).matched
            with pytest.raises(RuntimeStateConflictError,match="HOLDOUT_SELECTION_NOT_ESTIMABLE"):
                app.backtest_holdouts.select(request.reservation_id)
            assert app.backtest_holdouts.queries.inspect(request.reservation_id)["state"]=="RESERVED_BLOCKED"
            return
        assert app.backtest_holdouts.select(request.reservation_id)["selected_arm_code"]=="ridge_intraday"
        changed_recipe = replace(heldout.model_training_requirements[-1].recipe,
            hyperparameters=(replace(heldout.model_training_requirements[-1].recipe.hyperparameters[0],decimal_value=Decimal(10)),))
        changed = replace(heldout, model_training_requirements=(*heldout.model_training_requirements[:-1],
            replace(heldout.model_training_requirements[-1],recipe=changed_recipe)))
        with pytest.raises(RuntimeStateConflictError, match="parameters"):
            app.backtest_holdouts._validate_heldout(request, development, changed, "ridge_intraday")
        opened = app.backtest_holdouts.open(request.reservation_id, future_id, _context("open-holdout"))
        assert app.backtest_holdouts.open(request.reservation_id, future_id, _context("open-holdout")).replayed
        assert opened.fact["body"]["selected_arm_code"]=="ridge_intraday"
        fact=BacktestHoldoutOpening.from_payload(opened.fact["body"])
        from market_regime_alpha.infrastructure.postgres.repositories.backtest_holdout import PostgresBacktestHoldoutRepository
        replaced=tuple(sorted(((uuid4(),*fact.evaluation_scopes[0][1:]),*fact.evaluation_scopes[1:]),key=lambda row:str(row[0])))
        poisoned=replace(fact,allowed_evaluation_ids=tuple(row[0] for row in replaced),evaluation_scopes=replaced)
        with app._pool.connection() as c, pytest.raises(ArtifactIntegrityError,match="identities differ"):
            PostgresBacktestHoldoutRepository(c).open(poisoned)
        from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
        path=LocalArtifactStore(settings.artifact_root).object_path(str(fact.selection_artifact.content_sha256))
        original=path.read_bytes()
        try:
            path.write_bytes(b"corrupt selection")
            with pytest.raises(ArtifactIntegrityError,match="ARTIFACT_INTEGRITY_BLOCKED"):
                app.backtest_execution.resume(freeze_backtest_specification(heldout))
            # The direct Evaluation owner must reject physical corruption too,
            # before acquiring any label inputs (even without the CLI executor).
            with pytest.raises(ArtifactIntegrityError,match="ARTIFACT_INTEGRITY_BLOCKED"):
                app.research_evaluations.acquire_outcome_inputs(
                    fact.allowed_evaluation_ids[0], _context("corrupt-direct-evaluation"))
        finally:
            path.write_bytes(original)
        assert resume(heldout).execution_state.value=="COMPLETED"
        assert app.backtest_replay.verify(future_id).matched
        inspection = app.backtest_holdouts.queries.inspect(request.reservation_id)
        assert inspection["state"]=="ACCESSED" and len(inspection["evaluation_accesses"])==16
        evaluation_id = inspection["evaluation_accesses"][0][0]
        with app._pool.connection(read_only=True) as c:
            commitment, due = c.execute("SELECT member.commitment_id,member.outcome_due_at FROM mra.evaluation_run evaluation "
                "JOIN mra.research_partition_member member USING(research_partition_id) WHERE evaluation.evaluation_run_id=%s LIMIT 1",
                (evaluation_id,)).fetchone()
        with app._pool.connection(read_only=True) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="HOLDOUT_ACCESS_BLOCKED"):
            c.execute("SELECT mra.require_backtest_holdout_access(%s,%s,%s)", (commitment,due,uuid4()))
        with app._pool.connection(read_only=True) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="HOLDOUT_ACCESS_BLOCKED"):
            c.execute("SELECT mra.require_backtest_holdout_training_access(%s)", (evaluation_id,))
        with app._pool.connection(read_only=True) as c:
            assert c.execute("""SELECT mra.backtest_holdout_partition_matches(opening,array_position(opening.allowed_evaluation_ids,evaluation.evaluation_run_id),partition,evaluation)
                FROM mra.backtest_holdout_opening opening,mra.evaluation_run evaluation
                JOIN mra.research_partition partition USING(research_partition_id)
                WHERE opening.reservation_id=%s AND evaluation.evaluation_run_id=%s""",(request.reservation_id,evaluation_id)).fetchone()==(True,)
            for change in ({"population_scope":"SELECTED_COMMITMENTS"},{"purge_after_sessions":99},{"source_context_state":"RISK_OFF"},
                    {"decision_start_session_id":str(template.folds[0].sessions[0].trading_session_id)}):
                assert c.execute("""SELECT mra.backtest_holdout_partition_matches(opening,array_position(opening.allowed_evaluation_ids,evaluation.evaluation_run_id),
                    jsonb_populate_record(NULL::mra.research_partition,to_jsonb(partition)||%s::jsonb),evaluation)
                    FROM mra.backtest_holdout_opening opening,mra.evaluation_run evaluation
                    JOIN mra.research_partition partition USING(research_partition_id)
                    WHERE opening.reservation_id=%s AND evaluation.evaluation_run_id=%s""",
                    (json.dumps(change),request.reservation_id,evaluation_id)).fetchone()==(False,)
