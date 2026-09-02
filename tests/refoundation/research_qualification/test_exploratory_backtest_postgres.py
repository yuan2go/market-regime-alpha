from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.exploratory_backtest_uow import (
    PostgresExploratoryBacktestUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.exploratory_backtests import (
    PostgresExploratoryBacktestVerificationPort,
)
from market_regime_alpha.infrastructure.postgres.archive_uow import (
    PostgresArchiveUnitOfWorkProvider,
)
from market_regime_alpha.market.application import (
    ArchiveCommands,
    ArchiveSlicePlan,
    RecordArchiveCaptureObservationRequest,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
    ArchiveSealDisposition,
    BarTimeframe,
    NormalizationBatch,
    PriceBasis,
    TradingSession,
)
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.application.exploratory_backtest import (
    ExploratoryBacktestCommands,
)
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestArmPlan,
    BacktestCostAssumption,
    BacktestCostKind,
    BacktestFoldPlan,
    BacktestFoldSessionPlan,
    BacktestSessionRole,
    ExploratoryBacktestRunPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.runtime.errors import IdempotencyKeyReusedError
from market_regime_alpha.shared.hashing import canonical_json_sha256

from tests.refoundation.formal_research import test_formal_campaign_postgres as _formal
from tests.refoundation.research_qualification import test_research_postgres as _research


UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def backtest_stack(target_database_url, tmp_path, request):
    return _formal.wp14_campaign_stack.__wrapped__(target_database_url, tmp_path, request)


def _context(key: str):
    return _research._context(f"wp17p-{key}", "WP17P_EXPLORATORY_BACKTEST")


def _archive_sessions(stack):
    archive_code_artifact = stack.artifacts.publish(
        b"wp17p exploratory archive code\n",
        media_type="text/plain",
        context=_context("archive-code"),
    )
    archive_config_artifact = stack.artifacts.publish(
        b'{"scope":"ENGINEERING_EXPLORATORY_PILOT_32"}\n',
        media_type="application/json",
        context=_context("archive-config"),
    )
    dates = (
        datetime(2026, 1, day, tzinfo=SHANGHAI).date()
        for day in (5, 6, 7, 8, 12, 13, 14, 15)
    )
    sessions = []
    for session_date in dates:
        def at(hour: int, minute: int):
            return datetime.combine(
                session_date,
                time(hour, minute),
                tzinfo=SHANGHAI,
            ).astimezone(UTC)

        sessions.append(
            TradingSession(
                session_id=uuid4(),
                exchange="XSHG",
                session_date=session_date,
                timezone_name="Asia/Shanghai",
                open_at=at(9, 30),
                break_start_at=at(11, 30),
                break_end_at=at(13, 0),
                close_at=at(15, 0),
                decision_reference_at=at(14, 55),
                source_capture_id=uuid4(),
            )
        )
    capture = stack.market.capture(
        CaptureRequest(
            provider_product_id=stack.product.provider_product_id,
            capture_key=f"wp17p-backtest-calendar-{uuid4()}",
            resource="fixture://wp17p/backtest-calendar",
            request_headers_hash="c" * 64,
        ),
        _research._BytesProvider(),
        _context("calendar-capture"),
    )
    normalized_sessions = tuple(
        replace(item, source_capture_id=capture.capture.capture_id)
        for item in sessions
    )
    stack.market.normalize(
        capture.capture.capture_id,
        _research._Normalizer(
            lambda observed: NormalizationBatch(
                source_capture_id=observed.capture_id,
                source_provider_product_id=observed.provider_product_id,
                trading_sessions=normalized_sessions,
            )
        ),
        _context("calendar-normalize"),
    )
    archive_commands = ArchiveCommands(
        PostgresArchiveUnitOfWorkProvider(stack.pool),
        id_factory=uuid4,
    )
    archive_id = uuid4()
    slice_id = uuid4()
    archive = archive_commands.start(
        StartMarketArchiveRequest(
            market_archive_id=archive_id,
            archive_code=f"backtest-{archive_id.hex[:12]}",
            lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
            provider_product_id=stack.product.provider_product_id,
            exchange_code="SSE",
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            instrument_scope="ENGINEERING_EXPLORATORY_PILOT_32",
            instrument_scope_sha256=canonical_json_sha256({"scope": "pilot-32"}),
            event_window_start=normalized_sessions[0].open_at,
            event_window_end=normalized_sessions[-1].close_at,
            reserved_free_bytes=1,
            maximum_archive_bytes=1_000_000,
            maximum_slice_bytes=1_000_000,
            code_artifact_id=archive_code_artifact.artifact_id,
            config_artifact_id=archive_config_artifact.artifact_id,
            provenance_sha256="d" * 64,
            slices=(
                ArchiveSlicePlan(
                    market_archive_slice_id=slice_id,
                    ordinal=1,
                    scope_key="xshg:2026-01-05:2026-01-15",
                    event_window_start=normalized_sessions[0].open_at,
                    event_window_end=normalized_sessions[-1].close_at,
                    request_sha256="e" * 64,
                    expected_fact_kind="TRADING_SESSION",
                ),
            ),
        ),
        _context("archive-start"),
    )
    archive_commands.record_capture_observation(
        RecordArchiveCaptureObservationRequest(
            market_archive_id=archive_id,
            market_archive_slice_id=slice_id,
            capture_id=capture.capture.capture_id,
            schedule_slot="RETROSPECTIVE_BATCH",
            requested_at=capture.capture.temporal.capture_started_at,
        ),
        _context("archive-observe"),
    )
    seal = archive_commands.seal_retrospective(
        market_archive_id=archive_id,
        disposition=ArchiveSealDisposition.COMPLETE,
        context=_context("archive-seal"),
    )
    return archive, seal, normalized_sessions


def _plan(stack) -> ExploratoryBacktestRunPlan:
    target, candidate, context, strategy, portfolio, risk = _formal._decision_baseline(stack)
    fit_protocol, validation_protocol, _ = _formal._evaluation_protocols(stack, target)
    archive, seal, sessions = _archive_sessions(stack)
    with stack.pool.connection(read_only=True) as connection:
        feature_rows = connection.execute(
            """
            SELECT feature.feature_definition_id, feature.content_sha256
            FROM mra.candidate_policy_component AS component
            JOIN mra.feature_definition AS feature
              ON feature.feature_definition_id = component.feature_definition_id
            WHERE component.candidate_policy_id = %s
            ORDER BY component.ordinal
            """,
            (candidate.candidate_policy_id,),
        ).fetchall()
    roles = (
        BacktestSessionRole.FIT_INPUT,
        BacktestSessionRole.PURGE,
        BacktestSessionRole.EVALUATION,
        BacktestSessionRole.EMBARGO,
    )

    def fold(ordinal, purpose, protocol, selected):
        return BacktestFoldPlan(
            exploratory_backtest_fold_id=uuid4(),
            ordinal=ordinal,
            purpose=purpose,
            exchange_code="XSHG",
            purge_sessions=1,
            embargo_sessions=1,
            evaluation_protocol_id=protocol.evaluation_protocol_id,
            evaluation_protocol_sha256=protocol.content_sha256,
            sessions=tuple(
                BacktestFoldSessionPlan(
                    exploratory_backtest_fold_session_id=uuid4(),
                    ordinal=index,
                    trading_session_id=session.session_id.value,
                    session_date=session.session_date,
                    role=role,
                )
                for index, (session, role) in enumerate(
                    zip(selected, roles, strict=True),
                    start=1,
                )
            ),
        )

    return ExploratoryBacktestRunPlan(
        exploratory_backtest_run_id=uuid4(),
        run_code=f"wp17p-{uuid4().hex[:10]}",
        generation=1,
        market_archive_id=archive.market_archive_id,
        market_archive_seal_id=seal.market_archive_seal_id,
        hypothesis="Transparent rank baseline versus deterministic ridge challenger.",
        target_definition_id=target.target_definition_id,
        target_version=target.version,
        target_definition_sha256=target.content_sha256,
        feature_definitions=tuple(
            (row[0], str(row[1])) for row in feature_rows
        ),
        candidate_policy_id=candidate.candidate_policy_id,
        candidate_policy_sha256=candidate.content_sha256,
        context_policy_id=context.context_policy_id,
        context_policy_sha256=context.content_sha256,
        strategy_version_id=strategy.strategy_version_id,
        strategy_version_sha256=strategy.content_sha256,
        portfolio_policy_id=portfolio.portfolio_policy_id,
        portfolio_policy_sha256=portfolio.content_sha256,
        risk_policy_id=risk.risk_policy_id,
        risk_policy_sha256=risk.content_sha256,
        arms=(
            BacktestArmPlan(uuid4(), 1, BacktestArmKind.RULE_BASELINE),
            BacktestArmPlan(uuid4(), 2, BacktestArmKind.MODEL_CHALLENGER),
        ),
        folds=(
            fold(1, PartitionPurpose.FIT, fit_protocol, sessions[:4]),
            fold(2, PartitionPurpose.VALIDATION, validation_protocol, sessions[4:]),
        ),
        cost_assumptions=(
            BacktestCostAssumption(uuid4(), 1, BacktestCostKind.COMMISSION_BPS, Decimal("3")),
            BacktestCostAssumption(uuid4(), 2, BacktestCostKind.SLIPPAGE_BPS, Decimal("5")),
        ),
        random_seed=1729,
        code_artifact=target.algorithm.code_artifact,
        config_artifact=target.algorithm.config_artifact,
        provenance_sha256="f" * 64,
    )


def test_backtest_predeclaration_is_atomic_replayable_and_relational(backtest_stack) -> None:
    plan = _plan(backtest_stack)
    commands = ExploratoryBacktestCommands(
        PostgresExploratoryBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    result = commands.register(plan, _context("register"))
    replay = commands.register(plan, _context("register"))

    assert result.replayed is False
    assert replay.replayed is True
    assert replay.result_hash == result.result_hash
    with psycopg.connect(backtest_stack.database_url) as connection:
        counts = connection.execute(
            """
            SELECT root.feature_count, root.arm_count, root.fold_count,
                   root.session_count, root.cost_count,
                   (SELECT count(*) FROM mra.exploratory_backtest_feature
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.exploratory_backtest_arm
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.exploratory_backtest_fold
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.exploratory_backtest_fold_session
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.exploratory_backtest_cost_assumption
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id)
            FROM mra.exploratory_backtest_run AS root
            WHERE root.exploratory_backtest_run_id = %s
            """,
            (plan.exploratory_backtest_run_id,),
        ).fetchone()
    assert counts == (len(plan.feature_definitions), 2, 2, 8, 2) * 2
    verification = PostgresExploratoryBacktestVerificationPort(
        backtest_stack.pool
    ).verify(plan.exploratory_backtest_run_id)
    assert verification.matched is True
    assert verification.mismatch_count == 0

    with pytest.raises(IdempotencyKeyReusedError):
        commands.register(
            replace(plan, random_seed=1730),
            _context("register"),
        )
