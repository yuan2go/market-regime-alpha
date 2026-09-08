from datetime import timedelta
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.queries.daily_feature_inputs import PostgresDailyFeatureInputReadPort
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputState, session_open_close_move
from market_regime_alpha.research_qualification.domain.daily_protocol import daily_target_definition
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.market.domain import BarTimeframe, MarketBarRevision, NormalizationBatch, PriceBasis
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from tests.refoundation.research_qualification import test_research_postgres as research


def test_post_close_eligibility_does_not_require_unknown_future_session_status(stack):
    from market_regime_alpha.selection.domain import EligibilityRuleKind, UniverseScopeSpecification
    from market_regime_alpha.shared.time import DecisionTime
    from market_regime_alpha.infrastructure.postgres.repositories.selection import PostgresSelectionRepository

    with stack.pool.connection() as connection:
        row = connection.execute(
            "SELECT universe_id,scope_artifact_id,scope_content_sha256,scope_size_bytes FROM mra.universe_revision WHERE universe_revision_id=%s",
            (stack.universe_revision_id,),
        ).fetchone()
        old = PostgresSelectionRepository(connection).load_eligibility_policy(stack.eligibility_policy_id)
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    rule = replace(
        old.rules[0],
        eligibility_rule_id=uuid4(),
        rule_code="LAST_COMPLETE_SESSION_ACTIVE",
        rule_kind=EligibilityRuleKind.LAST_COMPLETED_SESSION_ACTIVE,
    )
    policy = replace(old, eligibility_policy_id=uuid4(), policy_code="daily_completed_session", rules=(rule,))
    stack.selection.register_eligibility_policy(policy, research._context("daily-policy", "REGISTER_ELIGIBILITY_POLICY"))
    scope = UniverseScopeSpecification(
        row[1], row[2], row[3], stack.product.provider_product_id, "INDEX", "RESEARCH_SCOPE", (stack.instrument_id,)
    )
    frozen = stack.selection.freeze_universe(
        universe_id=row[0], scope=scope, decision_time=DecisionTime(now), context=research._context("daily-universe", "FREEZE_UNIVERSE")
    )
    assessment = stack.selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=policy.eligibility_policy_id,
        decision_time=DecisionTime(now),
        context=research._context("daily-assess", "ASSESS_ELIGIBILITY"),
    )
    assert assessment.total_count == assessment.eligible_count == 1
    old_assessment = stack.selection.assess_eligibility(
        universe_revision_id=frozen.universe_revision_id,
        eligibility_policy_id=old.eligibility_policy_id,
        decision_time=DecisionTime(now),
        context=research._context("old-assess", "ASSESS_ELIGIBILITY"),
    )
    assert old_assessment.unknown_count == 1


@pytest.fixture
def stack(target_database_url, tmp_path, request):
    return research.dataset_stack.__wrapped__(target_database_url, tmp_path, request)


def test_daily_target_registration_is_canonical_and_idempotent(stack):
    artifact = stack.artifacts.publish(
        b"daily target fixture v1", media_type="text/plain", context=research._context("daily-code", "REGISTER_TARGET_CODE")
    )
    binding = ArtifactBinding(artifact.artifact_id, artifact.content_sha256, artifact.size_bytes)
    target = daily_target_definition(uuid4(), binding, binding)
    context = research._context("daily-target", "REGISTER_TARGET_DEFINITION")
    first = stack.research.register_target_definition(target, context)
    repeated = stack.research.register_target_definition(target, context)
    assert first.result_hash == repeated.result_hash
    with stack.pool.connection(read_only=True) as connection:
        assert connection.execute(
            "SELECT metric_kind FROM mra.target_metric_definition WHERE target_definition_id=%s", (target.target_definition_id,)
        ).fetchall() == [("OBSERVATION_RETURN",)]


def test_experimental_use_sql_identity_matches_the_typed_artifact_contract(stack):
    from market_regime_alpha.research_qualification.domain.experimental_model_use import ExperimentalModelUsePlan

    with stack.pool.connection(read_only=True) as connection:
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        expression = connection.execute(
            "SELECT pg_get_expr(conbin,conrelid) FROM pg_constraint WHERE conname='experimental_use_hash_ck'"
        ).fetchone()[0]
        plan = ExperimentalModelUsePlan(
            uuid4(), uuid4(), uuid4(), "b" * 64, ArtifactBinding(uuid4(), "c" * 64, 123), now, now + timedelta(days=1), uuid4()
        )
        # Evaluate the actual database CHECK without bypassing any business FK.
        # The independently constructed typed request must have identical bytes.
        result = connection.execute(
            "SELECT "
            + expression
            + """ FROM (SELECT %s::uuid AS experimental_model_use_id,
            %s::uuid AS model_version_id,%s::uuid AS target_metric_definition_id,%s::text AS feature_roster_sha256,
            %s::uuid AS protocol_artifact_id,%s::text AS protocol_content_sha256,%s::bigint AS protocol_size_bytes,
            %s::timestamptz AS valid_from,%s::timestamptz AS expires_at,%s::text AS purpose,%s::text AS content_sha256,%s::uuid AS baseline_strategy_version_id) input""",
            (
                plan.experimental_model_use_id,
                plan.model_version_id,
                plan.target_metric_definition_id,
                plan.feature_roster_sha256,
                plan.protocol_artifact.artifact_id,
                str(plan.protocol_artifact.content_sha256),
                plan.protocol_artifact.size_bytes,
                plan.valid_from,
                plan.expires_at,
                plan.purpose,
                plan.content_sha256,
                plan.baseline_strategy_version_id,
            ),
        ).fetchone()
    assert result == (True,)


def test_actual_daily_input_rejects_future_revision_and_never_uses_five_minute_bar(stack):
    with stack.pool.connection(read_only=True) as connection:
        opening, closing = connection.execute(
            "SELECT open_at,close_at FROM mra.trading_session WHERE session_id=%s", (stack.market_session_id,)
        ).fetchone()
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    reader = PostgresDailyFeatureInputReadPort(stack.pool, stack.store)
    kwargs = dict(
        provider_product_id=stack.product.provider_product_id,
        session_id=stack.market_session_id,
        instrument_ids=(stack.instrument_id.value,),
    )
    assert reader.visible(**kwargs, input_cutoff=before)[0].state is DailyInputState.MISSING
    with pytest.raises(research.RuntimeStateConflictError, match="future"):
        reader.visible(**kwargs, input_cutoff=before + timedelta(days=1))
    captured = stack.market.capture(
        research.CaptureRequest(stack.product.provider_product_id, "daily-test-bar", "fixture://daily-bar", "d" * 64),
        research._BytesProvider(),
        research._context("daily-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    bar_id = uuid4()

    def batch(capture):
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=bar_id,
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=stack.instrument_id,
                    session_id=stack.market_session_id,
                    timeframe=BarTimeframe.DAILY,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=opening,
                    event_end=closing,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Money(Decimal("100"), "CNY"),
                    high=Money(Decimal("105"), "CNY"),
                    low=Money(Decimal("100"), "CNY"),
                    close=Money(Decimal("105"), "CNY"),
                    volume=Quantity(Decimal("100"), QuantityUnit.SHARES),
                    turnover=None,
                ),
            ),
        )

    normalized = stack.market.normalize(
        captured.capture.capture_id, research._Normalizer(batch), research._context("daily-normalize", "NORMALIZE_MARKET_PIT")
    )
    assert reader.visible(**kwargs, input_cutoff=before)[0].state is DailyInputState.MISSING
    member = reader.visible(**kwargs, input_cutoff=normalized.decision_visible_at.value + timedelta(microseconds=1))[0]
    assert member.bar_revision_id == bar_id
    assert session_open_close_move(member.open_value, member.close_value) == Decimal("0.050000000000")
    with psycopg.connect(stack.database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.market_bar_revision WHERE bar_revision_id=%s", (bar_id,)).fetchone() == (1,)


def test_actual_daily_runtime_freezes_complete_population_and_shared_feature(
    stack, monkeypatch
):
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
    from market_regime_alpha.market.domain import TradingSession
    from market_regime_alpha.selection.domain import EligibilityRuleKind
    from market_regime_alpha.infrastructure.postgres.repositories.selection import PostgresSelectionRepository
    from market_regime_alpha.research_qualification.domain.daily_protocol import daily_feature_definition
    from tests.refoundation.research_qualification.test_daily_prediction import plan as example_plan

    with stack.pool.connection() as connection:
        opening, closing = connection.execute(
            "SELECT open_at,close_at FROM mra.trading_session WHERE session_id=%s", (stack.market_session_id,)
        ).fetchone()
        universe, scope_id, scope_hash, scope_size = connection.execute(
            "SELECT universe_id,scope_artifact_id,scope_content_sha256,scope_size_bytes FROM mra.universe_revision WHERE universe_revision_id=%s",
            (stack.universe_revision_id,),
        ).fetchone()
        old = PostgresSelectionRepository(connection).load_eligibility_policy(stack.eligibility_policy_id)
    capture = stack.market.capture(
        research.CaptureRequest(stack.product.provider_product_id, "daily-runtime-input", "fixture://daily-runtime", "e" * 64),
        research._BytesProvider(),
        research._context("daily-runtime-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    future_date = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)

    def future(hour, minute):
        return datetime.combine(future_date, time(hour, minute), ZoneInfo("Asia/Shanghai")).astimezone(research.UTC)

    target_session = uuid4()

    def batch(captured):
        return NormalizationBatch(
            source_capture_id=captured.capture_id,
            source_provider_product_id=captured.provider_product_id,
            trading_sessions=(
                TradingSession(
                    target_session,
                    "XSHG",
                    future_date,
                    "Asia/Shanghai",
                    future(9, 30),
                    future(11, 30),
                    future(13, 0),
                    future(15, 0),
                    future(14, 55),
                    captured.capture_id,
                ),
            ),
            bars=(
                MarketBarRevision(
                    uuid4(),
                    captured.provider_product_id,
                    captured.capture_id,
                    stack.instrument_id,
                    stack.market_session_id,
                    BarTimeframe.DAILY,
                    PriceBasis.RAW_UNADJUSTED,
                    opening,
                    closing,
                    1,
                    None,
                    Money(Decimal("100"), "CNY"),
                    Money(Decimal("105"), "CNY"),
                    Money(Decimal("100"), "CNY"),
                    Money(Decimal("105"), "CNY"),
                    Quantity(Decimal("100"), QuantityUnit.SHARES),
                    None,
                ),
            ),
        )

    stack.market.normalize(
        capture.capture.capture_id, research._Normalizer(batch), research._context("daily-runtime-normalize", "NORMALIZE_MARKET_PIT")
    )
    code = stack.artifacts.publish(
        b"daily runtime fixture", media_type="text/plain", context=research._context("daily-runtime-code", "REGISTER_ARTIFACT")
    )
    binding = ArtifactBinding(code.artifact_id, code.content_sha256, code.size_bytes)
    feature = daily_feature_definition(uuid4(), binding, binding)
    stack.research.register_feature_definition(feature, research._context("daily-runtime-feature", "REGISTER_FEATURE_DEFINITION"))
    target = daily_target_definition(uuid4(), binding, binding)
    stack.research.register_target_definition(target, research._context("daily-runtime-target", "REGISTER_TARGET_DEFINITION"))
    policy = replace(
        old,
        eligibility_policy_id=uuid4(),
        policy_code="daily_runtime_completed_session",
        rules=(
            replace(
                old.rules[0],
                eligibility_rule_id=uuid4(),
                rule_code="LAST_COMPLETE_SESSION_ACTIVE",
                rule_kind=EligibilityRuleKind.LAST_COMPLETED_SESSION_ACTIVE,
            ),
        ),
    )
    stack.selection.register_eligibility_policy(policy, research._context("daily-runtime-policy", "REGISTER_ELIGIBILITY_POLICY"))
    from tests.refoundation.research_qualification import _historical_backtest_catalog as C
    from market_regime_alpha.runtime.application import CommandContext, ActorType
    import time as elapsed_time

    with bootstrap_application(TargetSettings(stack.database_url, stack.store.root)) as app:
        # This input/lease test intentionally uses the compact example plan instead
        # of building a trained ModelVersion.  Keep the independent admission gate
        # out of scope here; the PostgreSQL vertical tests exercise it with a real
        # ExperimentalModelUse, including revocation during a partial Run.
        monkeypatch.setattr(
            app.daily_prediction_reads,
            "model_use_available",
            lambda _plan: True,
        )
        candidate = C._candidate(feature, binding, binding)
        app.candidates.register_candidate_policy(candidate, research._context("daily-runtime-candidate", "REGISTER_CANDIDATE_POLICY"))
        now = app.daily_prediction_reads.now()
        plan = replace(
            example_plan(),
            prediction_id=uuid4(),
            provider_product_id=stack.product.provider_product_id,
            universe_id=universe,
            universe_scope=ArtifactBinding(scope_id, scope_hash, scope_size),
            classification_scheme="INDEX",
            classification_code="RESEARCH_SCOPE",
            instrument_ids=(stack.instrument_id.value,),
            eligibility_policy_id=policy.eligibility_policy_id,
            feature_definition_id=feature.feature_definition_id,
            candidate_policy_id=candidate.candidate_policy_id,
            input_session_id=stack.market_session_id,
            target_session_id=target_session,
            input_cutoff=now,
            decision_time=now,
            target_definition_id=target.target_definition_id,
            code_artifact=binding,
            config_artifact=binding,
        )
        plan = replace(plan, input_content_sha256=app.daily_prediction_reads.observe(plan).content_sha256)
        trace = app.daily_research.execute(plan, worker_id="daily-fixture", maximum_steps=3)
        assert tuple(step.state for step in trace.steps[:3]) == ("SUCCEEDED",) * 3
        population = app.daily_prediction_reads.population(plan)
        assert len(population) == 1 and population[0].eligible
        with stack.pool.connection(read_only=True) as connection:
            assert connection.execute(
                "SELECT row_count,available_cell_count FROM mra.dataset WHERE dataset_id=%s", (plan.dataset_id,)
            ).fetchone() == (1, 1)
            assert connection.execute(
                "SELECT count(*) FROM mra.exploratory_backtest_dataset WHERE dataset_id=%s", (plan.dataset_id,)
            ).fetchone() == (0,)
        claim = app.runtime.claim_next(
            run_id=plan.runtime_run_id,
            step_id=trace.steps[3].step_id,
            worker_id="crashed-daily",
            lease_duration=timedelta(seconds=1),
            context=CommandContext("crashed-claim", ActorType.WORKER, "crashed-daily", "TEST_CRASH"),
        )
        assert claim is not None
        app.runtime.start_attempt(claim, CommandContext("crashed-start", ActorType.WORKER, "crashed-daily", "TEST_CRASH"))
        elapsed_time.sleep(1.1)  # Disposable DB lease, never a real market window wait.
        resumed = app.daily_research.execute(plan, worker_id="daily-fixture", maximum_steps=1)
        assert resumed.steps[3].state == "SUCCEEDED" and resumed.steps[3].current_fence == 2
        with stack.pool.connection(read_only=True) as connection:
            assert connection.execute("SELECT count(*) FROM mra.candidate_set WHERE dataset_id=%s", (plan.dataset_id,)).fetchone() == (1,)
        from market_regime_alpha.runtime.errors import StaleFenceError

        with stack.pool.connection(read_only=True) as connection:
            before = connection.execute(
                "SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)"
            ).fetchone()
        with pytest.raises(StaleFenceError):
            app.candidates.build_candidate_set(
                plan.candidate_policy_id,
                plan.dataset_id,
                CommandContext("stale-daily-result", ActorType.WORKER, "crashed-daily", "TEST_CRASH"),
                runtime_claim=claim,
            )

        with stack.pool.connection(read_only=True) as connection:
            assert (
                connection.execute("SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)").fetchone()
                == before
            )
