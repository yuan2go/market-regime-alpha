from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.daily_loop import (
    DailyLoopRunner,
    DailyRunCommand,
    DailyRunStatus,
    RunMode,
    SQLiteDailyRunRepository,
    StageReceipt,
)
from market_regime_alpha.application.daily_loop.errors import (
    OutcomeNotReadyError,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.daily_decision.entry import EntryAssessmentState
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    AcquiredSourcePayload,
    BaoStockHistoryClient,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeProviderResult,
    PublicCompositeLiveProfile,
    SourceReplayArchiveReader,
    TencentCurrentQuoteClient,
    publish_source_archive,
)
from market_regime_alpha.data.source_manifest import (
    SourceFieldFinality,
    SourceManifest,
)
from market_regime_alpha.universe.daily_exploratory import smoke_pool_policy_v1
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from tests.application.daily_loop.public_fixture import (
    DECISION,
    public_fixture,
    public_v2_fixture,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
CODE_REVISION = "772ecfb09410588b5a406ad900d793a5850e60d5"


def test_replay_run_publishes_one_verified_daily_decision(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(policy=policy)
    archive = publish_source_archive(
        root=tmp_path / "fixture-archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.REPLAY,
        provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
        replay_source_manifest_id=source_manifest.source_manifest_id,
    )
    runner = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    )

    result = runner.run(command, replay_archive_path=archive)

    assert result.record.status is DailyRunStatus.OUTCOME_PENDING
    assert result.record.daily_run_id is not None
    assert result.decision_artifact.bundle.prediction_runs
    assert len(result.decision_artifact.bundle.recommendations) == 10
    assert {
        item.entry_state
        for item in result.decision_artifact.bundle.entry_assessments
    } == {EntryAssessmentState.WAIT_CONFIRMATION}


def test_replay_performs_no_network_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, command, archive = _replay_runner(tmp_path)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("REPLAY_ATTEMPTED_NETWORK_ACCESS")

    monkeypatch.setattr(BaoStockHistoryClient, "acquire", unexpected_network)
    monkeypatch.setattr(
        TencentCurrentQuoteClient,
        "acquire",
        unexpected_network,
    )

    result = runner.run(command, replay_archive_path=archive)

    assert result.record.status is DailyRunStatus.OUTCOME_PENDING


def test_public_daily_history_preserves_b0_b1_ranking_equivalence(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, baseline_provider, baseline_manifest = public_fixture(policy=policy)
    _, daily_provider, daily_manifest = public_fixture(
        policy=policy,
        exploratory_daily_history=True,
    )
    baseline_archive = publish_source_archive(
        root=tmp_path / "baseline-archives",
        provider_result=baseline_provider,
        source_manifest=baseline_manifest,
    )
    daily_archive = publish_source_archive(
        root=tmp_path / "daily-archives",
        provider_result=daily_provider,
        source_manifest=daily_manifest,
    )

    def run_one(
        *,
        name: str,
        archive: Path,
        manifest: SourceManifest,
    ):
        command = DailyRunCommand(
            decision_date=DECISION.value.date(),
            decision_time=DECISION,
            run_mode=RunMode.REPLAY,
            provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
            universe_policy_id=str(policy.policy_id),
            model_set_id="daily-b0-b1-v1",
            configuration_identity=ArtifactId("daily-loop-test-config-v1"),
            output_root=tmp_path / name,
            replay_source_manifest_id=manifest.source_manifest_id,
        )
        return DailyLoopRunner(
            repository=SQLiteDailyRunRepository(tmp_path / f"{name}.sqlite3"),
            code_revision=CODE_REVISION,
            clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
        ).run(command, replay_archive_path=archive)

    baseline = run_one(
        name="baseline",
        archive=baseline_archive,
        manifest=baseline_manifest,
    )
    daily = run_one(
        name="daily",
        archive=daily_archive,
        manifest=daily_manifest,
    )

    def ranking_projection(result):
        return tuple(
            (
                str(run.model_id),
                run.population_size,
                run.ranking_coverage,
                tuple(
                    (
                        prediction.symbol,
                        prediction.model_score,
                        prediction.rank,
                        prediction.percentile,
                    )
                    for prediction in run.predictions
                ),
                tuple(
                    (
                        rejection.symbol,
                        rejection.reason_code,
                        str(rejection.feature_id),
                    )
                    for rejection in run.rejections
                ),
            )
            for run in result.decision_artifact.bundle.prediction_runs
        )

    assert ranking_projection(daily) == ranking_projection(baseline)
    assert tuple(
        (item.model_id, item.symbol, item.rank, item.score)
        for item in daily.decision_artifact.bundle.recommendations
    ) == tuple(
        (item.model_id, item.symbol, item.rank, item.score)
        for item in baseline.decision_artifact.bundle.recommendations
    )
    assert tuple(
        run.prediction_run_id
        for run in daily.decision_artifact.bundle.prediction_runs
    ) != tuple(
        run.prediction_run_id
        for run in baseline.decision_artifact.bundle.prediction_runs
    )


def test_artifact_records_public_history_semantic_limitations(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(
        policy=policy,
        exploratory_daily_history=True,
    )

    completed = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    assert completed.record.status is DailyRunStatus.OUTCOME_PENDING
    assert (
        "HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1"
        in completed.decision_artifact.bundle.source_manifest.limitations
    )
    assert completed.decision_artifact.bundle.source_manifest.data_eligibility is (
        DataEligibility.EXPLORATORY
    )


def test_repeated_command_reuses_frozen_source_and_artifacts(
    tmp_path: Path,
) -> None:
    runner, command, archive = _replay_runner(tmp_path)

    first = runner.run(command, replay_archive_path=archive)
    counts = _artifact_counts(command.output_root)
    second = runner.run(command)

    assert second.record == first.record
    assert second.decision_artifact.artifact_id == (
        first.decision_artifact.artifact_id
    )
    assert second.decision_artifact.checksums_hash == (
        first.decision_artifact.checksums_hash
    )
    assert _artifact_counts(command.output_root) == counts


def test_daily_run_id_binds_history_and_quote_hashes(tmp_path: Path) -> None:
    runner, command, archive = _replay_runner(tmp_path)
    source = SourceReplayArchiveReader().read(archive)

    completed = runner.run(command, replay_archive_path=archive)

    identity = completed.record.daily_run_identity
    assert identity is not None
    assert identity.source_manifest_id == source.source_manifest.source_manifest_id
    assert identity.source_manifest_content_hash == (
        source.source_manifest.content_hash
    )
    assert identity.source_content_hashes == tuple(
        sorted(
            {
                item.raw_hash
                for item in source.provider_result.raw_payloads
            }
        )
    )


def test_failure_after_source_freeze_resumes_without_provider_access(
    tmp_path: Path,
) -> None:
    _, command, archive = _replay_runner(tmp_path)
    repository = SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3")

    def fail_after_freeze(status: DailyRunStatus) -> None:
        if status is DailyRunStatus.SOURCE_FROZEN:
            raise RuntimeError("INJECTED_AFTER_SOURCE_FREEZE")

    interrupted = DailyLoopRunner(
        repository=repository,
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
        after_stage_hook=fail_after_freeze,
    )
    with pytest.raises(RuntimeError, match="INJECTED_AFTER_SOURCE_FREEZE"):
        interrupted.run(command, replay_archive_path=archive)
    failed = repository.get(command.run_request_id)
    assert failed.status is DailyRunStatus.FAILED
    assert failed.resume_status is DailyRunStatus.SOURCE_FROZEN
    assert failed.daily_run_id is not None

    resumed = DailyLoopRunner(
        repository=repository,
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 1, tzinfo=SHANGHAI),
    ).run(command)

    assert resumed.record.status is DailyRunStatus.OUTCOME_PENDING
    assert resumed.record.daily_run_id == failed.daily_run_id


def test_crash_between_source_binding_and_receipt_recovers_without_acquisition(
    tmp_path: Path,
) -> None:
    _, command, archive = _replay_runner(tmp_path)

    class ReceiptCrashRepository(SQLiteDailyRunRepository):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self.crashed = False

        def record_stage_receipt(self, receipt: StageReceipt) -> StageReceipt:
            if (
                receipt.stage is DailyRunStatus.SOURCE_FROZEN
                and not self.crashed
            ):
                self.crashed = True
                raise RuntimeError("CRASH_BEFORE_SOURCE_RECEIPT")
            return super().record_stage_receipt(receipt)

    journal = tmp_path / "runtime.sqlite3"
    interrupted_repository = ReceiptCrashRepository(journal)
    with pytest.raises(RuntimeError, match="CRASH_BEFORE_SOURCE_RECEIPT"):
        DailyLoopRunner(
            repository=interrupted_repository,
            code_revision=CODE_REVISION,
            clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
        ).run(command, replay_archive_path=archive)
    failed = interrupted_repository.get(command.run_request_id)
    assert failed.status is DailyRunStatus.FAILED
    assert failed.resume_status is DailyRunStatus.SOURCE_FROZEN

    resumed = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(journal),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 1, tzinfo=SHANGHAI),
    ).run(command)

    assert resumed.record.status is DailyRunStatus.OUTCOME_PENDING


def test_provider_invariant_failure_is_failed_not_data_blocked(
    tmp_path: Path,
) -> None:
    class InvalidClient:
        def acquire(self, request):
            raise ValueError("PROVIDER_CONTRACT_VIOLATION")

    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )
    repository = SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3")
    runner = DailyLoopRunner(
        repository=repository,
        code_revision=CODE_REVISION,
        live_profile=PublicCompositeLiveProfile(
            history_client=InvalidClient(),
            current_client=InvalidClient(),
        ),
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    )

    with pytest.raises(ValueError, match="PROVIDER_CONTRACT_VIOLATION"):
        runner.run(command)

    assert repository.get(command.run_request_id).status is DailyRunStatus.FAILED


def test_missing_price_is_a_verified_data_blocked_terminal(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(
        policy=policy,
        missing_price_symbol=policy.symbols[0],
    )
    archive = publish_source_archive(
        root=tmp_path / "fixture-archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = _command(
        tmp_path=tmp_path,
        source_manifest_id=source_manifest.source_manifest_id,
    )
    result = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    ).run(command, replay_archive_path=archive)

    assert result.record.status is DailyRunStatus.DATA_BLOCKED
    assert result.decision_artifact.bundle.prediction_runs == ()
    assert result.decision_artifact.bundle.recommendations == ()
    assert result.decision_artifact.bundle.entry_assessments == ()
    assert any(
        "PRICE_UNAVAILABLE" in reason
        for reason in result.decision_artifact.bundle.data_quality_report.blocked_reason_codes
    )


def test_global_provider_failure_blocks_run(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )

    result = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    ).run(command)

    assert result.record.status is DailyRunStatus.DATA_BLOCKED
    assert result.decision_artifact.bundle.source_manifest.limitations == (
        "LIVE_ACQUISITION_FAILED",
        "PUBLIC_DATA_EXPLORATORY_ONLY",
        "NO_LOCAL_ARCHIVE_FALLBACK",
        "PROTOCOL_AND_POLICY_EVIDENCE_ARCHIVED",
        "ELIGIBILITY_POLICY_EVIDENCE_ARCHIVED",
    )
    assert result.decision_artifact.bundle.prediction_runs == ()


def test_live_never_uses_local_archive_fallback(tmp_path: Path) -> None:
    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )
    local_archive = tmp_path / "old-local-cache"
    local_archive.mkdir()
    (local_archive / "fixture.json").write_text("{}", encoding="utf-8")

    result = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    ).run(command)
    acquired = SourceReplayArchiveReader().read(result.source_archive_path)

    assert result.record.status is DailyRunStatus.DATA_BLOCKED
    assert "NO_LOCAL_ARCHIVE_FALLBACK" in acquired.provider_result.limitations
    assert all(
        item.locator != str(local_archive)
        and not item.locator.startswith("archive://fixture")
        for item in acquired.provider_result.raw_payloads
    )


def test_live_current_failure_archives_successful_history_payload(
    tmp_path: Path,
) -> None:
    history_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-history-success",
        locator="baostock://fixture/history-success",
        raw_payload=b"successful-history-before-current-failure",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    history = PublicCompositeBatch(
        raw_payloads=(history_payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("BAOSTOCK_HISTORY_ONLY",),
    )

    class HistoryClient:
        def acquire(self, request):
            return history

    class CurrentFailureClient:
        def acquire(self, request):
            raise AShareDataError("TENCENT_FIXTURE_UNAVAILABLE")

    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )
    result = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        live_profile=PublicCompositeLiveProfile(
            history_client=HistoryClient(),
            current_client=CurrentFailureClient(),
        ),
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    ).run(command)

    acquired = SourceReplayArchiveReader().read(result.source_archive_path)
    assert result.record.status is DailyRunStatus.DATA_BLOCKED
    assert tuple(
        item.provider_id for item in acquired.provider_result.raw_payloads
    ) == (
        ProviderId("provider-baostock-public"),
        ProviderId("provider-public-composite-live-runtime"),
        ProviderId("provider-daily-run-protocol"),
        ProviderId("authority-daily-universe-policy"),
        ProviderId("authority-daily-eligibility-policy"),
    )
    assert acquired.provider_result.raw_payloads[0] == history_payload
    assert "NO_LOCAL_ARCHIVE_FALLBACK" in (
        acquired.provider_result.limitations
    )


def test_history_freeze_is_reused_after_quote_failure(
    tmp_path: Path,
) -> None:
    history_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-history-stage",
        locator="baostock://fixture/history-stage",
        raw_payload=b"history-stage",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 3, 14, 50, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    current_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-current-stage",
        locator="https://qt.gtimg.cn/q=fixture-stage",
        raw_payload=b"current-stage",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    history_batch = PublicCompositeBatch(
        raw_payloads=(history_payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("BAOSTOCK_HISTORY_ONLY",),
    )
    current_batch = PublicCompositeBatch(
        raw_payloads=(current_payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("TENCENT_CURRENT_QUOTE_ONLY",),
    )

    class CountingHistoryClient:
        calls = 0

        def acquire(self, request):
            self.calls += 1
            return history_batch

    class InterruptThenSucceedCurrentClient:
        calls = 0

        def acquire(self, request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("CRASH_AFTER_HISTORY_FREEZE")
            return current_batch

    history_client = CountingHistoryClient()
    current_client = InterruptThenSucceedCurrentClient()
    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )
    runner = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        live_profile=PublicCompositeLiveProfile(
            history_client=history_client,
            current_client=current_client,
        ),
        clock=lambda: datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI),
    )

    with pytest.raises(RuntimeError, match="CRASH_AFTER_HISTORY_FREEZE"):
        runner.run(command)
    resumed = runner.run(command)

    assert history_client.calls == 1
    assert current_client.calls == 2
    assert resumed.record.status is DailyRunStatus.DATA_BLOCKED


def test_receipt_write_before_crash_recovers_orphan_without_reacquisition(
    tmp_path: Path,
) -> None:
    history_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-orphan-history-stage",
        locator="baostock://fixture/orphan-history-stage",
        raw_payload=b"orphan-history-stage",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 3, 14, 50, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    current_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-orphan-current-stage",
        locator="https://qt.gtimg.cn/q=fixture-orphan",
        raw_payload=b"orphan-current-stage",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    history_batch = PublicCompositeBatch(
        raw_payloads=(history_payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("BAOSTOCK_HISTORY_ONLY",),
    )
    current_batch = PublicCompositeBatch(
        raw_payloads=(current_payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("TENCENT_CURRENT_QUOTE_ONLY",),
    )

    class CountingClient:
        def __init__(self, batch: PublicCompositeBatch) -> None:
            self.batch = batch
            self.calls = 0

        def acquire(self, request):
            self.calls += 1
            return self.batch

    class FailFirstReceiptRepository(SQLiteDailyRunRepository):
        fail_first_receipt = True

        def record_acquisition_receipt(self, receipt):
            if self.fail_first_receipt:
                self.fail_first_receipt = False
                raise RuntimeError("CRASH_BEFORE_ACQUISITION_RECEIPT")
            return super().record_acquisition_receipt(receipt)

    history_client = CountingClient(history_batch)
    current_client = CountingClient(current_batch)
    policy = smoke_pool_policy_v1()
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.LIVE,
        provider_profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
    )
    runner = DailyLoopRunner(
        repository=FailFirstReceiptRepository(
            tmp_path / "runtime.sqlite3"
        ),
        code_revision=CODE_REVISION,
        live_profile=PublicCompositeLiveProfile(
            history_client=history_client,
            current_client=current_client,
        ),
        clock=lambda: datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI),
    )

    with pytest.raises(
        RuntimeError,
        match="CRASH_BEFORE_ACQUISITION_RECEIPT",
    ):
        runner.run(command)
    resumed = runner.run(command)

    assert history_client.calls == 1
    assert current_client.calls == 1
    assert resumed.record.status is DailyRunStatus.DATA_BLOCKED


def test_settlement_appends_review_without_mutating_daily_decision(
    tmp_path: Path,
) -> None:
    runner, command, archive = _replay_runner(tmp_path)
    daily = runner.run(command, replay_archive_path=archive)
    before = _tree_hashes(daily.decision_artifact.root)
    settlement_archive = _settlement_archive(
        tmp_path,
        symbols=tuple(
            item.symbol
            for item in daily.decision_artifact.bundle.prediction_runs[0].predictions
        ),
    )
    assert daily.record.daily_run_id is not None

    settled = runner.settle_daily_run(
        daily.record.daily_run_id,
        settlement_archive_path=settlement_archive,
    )

    assert settled.record.status is DailyRunStatus.REVIEW_PUBLISHED
    assert settled.review_artifact.settlement.review.outcome_coverage == 1.0
    assert settled.review_artifact.settlement.review.unresolved_outcome_count == 0
    assert _tree_hashes(daily.decision_artifact.root) == before
    replayed = runner.settle_daily_run(
        daily.record.daily_run_id,
        settlement_archive_path=settlement_archive,
    )
    assert replayed.review_artifact.checksums_hash == (
        settled.review_artifact.checksums_hash
    )


def test_ten_session_replay_is_unique_replayable_and_settleable(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    repository = SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3")
    runner = DailyLoopRunner(
        repository=repository,
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 14, 16, 0, tzinfo=SHANGHAI),
    )
    session_dates = (
        date(2025, 2, 3),
        date(2025, 2, 4),
        date(2025, 2, 5),
        date(2025, 2, 6),
        date(2025, 2, 7),
        date(2025, 2, 10),
        date(2025, 2, 11),
        date(2025, 2, 12),
        date(2025, 2, 13),
        date(2025, 2, 14),
    )
    run_ids = []
    artifact_ids = []
    replay_hashes = []
    for session_date in session_dates:
        decision_time = DecisionTime(
            datetime(
                session_date.year,
                session_date.month,
                session_date.day,
                14,
                55,
                tzinfo=SHANGHAI,
            )
        )
        _, provider_result, source_manifest = public_fixture(
            policy=policy,
            decision_time=decision_time,
        )
        archive = publish_source_archive(
            root=tmp_path / "fixture-archives",
            provider_result=provider_result,
            source_manifest=source_manifest,
        )
        command = DailyRunCommand(
            decision_date=session_date,
            decision_time=decision_time,
            run_mode=RunMode.REPLAY,
            provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
            universe_policy_id=str(policy.policy_id),
            model_set_id="daily-b0-b1-v1",
            configuration_identity=ArtifactId("ten-session-config-v1"),
            output_root=tmp_path / "runtime",
            replay_source_manifest_id=source_manifest.source_manifest_id,
        )
        daily = runner.run(command, replay_archive_path=archive)
        assert daily.record.daily_run_id is not None
        run_ids.append(daily.record.daily_run_id)
        artifact_ids.append(daily.decision_artifact.artifact_id)
        replay_hashes.append(daily.decision_artifact.checksums_hash)
        replayed = runner.run(command)
        assert replayed.decision_artifact.checksums_hash == replay_hashes[-1]
        next_session = _next_weekday(session_date)
        settlement_archive = _settlement_archive(
            tmp_path,
            symbols=tuple(
                item.symbol
                for item in daily.decision_artifact.bundle.prediction_runs[
                    0
                ].predictions
            ),
            next_session=next_session,
        )
        settled = runner.settle_daily_run(
            daily.record.daily_run_id,
            settlement_archive_path=settlement_archive,
        )
        assert settled.record.status is DailyRunStatus.REVIEW_PUBLISHED
        assert settled.review_artifact.settlement.review.outcome_coverage == 1.0

    assert len(set(run_ids)) == 10
    assert len(set(artifact_ids)) == 10
    assert len(set(replay_hashes)) == 10


def test_quote_stale_blocks_before_universe_projection(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(
        policy=policy,
        quote_age_minutes=6,
    )

    blocked = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    assert blocked.record.status is DailyRunStatus.DATA_BLOCKED
    assert blocked.decision_artifact.bundle.universe_snapshot is None
    assert any(
        "QUOTE_STALE" in reason
        for reason in blocked.decision_artifact.bundle.data_quality_report.blocked_reason_codes
    )


def test_insufficient_candidate_pool_blocks_with_full_accounting(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(
        policy=policy,
        suspended_symbols=policy.symbols[:16],
    )

    blocked = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    assert blocked.record.status is DailyRunStatus.DATA_BLOCKED
    assert blocked.decision_artifact.bundle.data_quality_report.blocked_reason_codes[
        -1
    ] == "CANDIDATE_POPULATION_INSUFFICIENT"


def test_partial_symbol_failure_preserves_remaining_population(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    excluded = policy.symbols[0]
    _, result, manifest = public_v2_fixture(
        policy=policy,
        unknown_trading_symbol=excluded,
    )

    completed = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    assert completed.record.status is DailyRunStatus.OUTCOME_PENDING
    assert all(
        run.population_size == 19
        and len(run.predictions) == 19
        and excluded not in {item.symbol for item in run.predictions}
        for run in completed.decision_artifact.bundle.prediction_runs
    )


def test_successful_public_replay_reaches_outcome_pending(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_v2_fixture(policy=policy)

    completed = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    bundle = completed.decision_artifact.bundle
    assert completed.record.status is DailyRunStatus.OUTCOME_PENDING
    assert all(run.population_size == 20 for run in bundle.prediction_runs)
    assert len(bundle.recommendations) == 10
    assert len(bundle.entry_assessments) == 10


def test_feature_window_missing_blocks_without_partial_predictions(
    tmp_path: Path,
) -> None:
    policy = smoke_pool_policy_v1()
    _, complete_result, manifest = public_fixture(policy=policy)
    missing_symbol = policy.symbols[0]
    result = replace(
        complete_result,
        bars=tuple(
            item
            for item in complete_result.bars
            if not (
                item.symbol == missing_symbol
                and item.event_time
                == max(
                    bar.event_time
                    for bar in complete_result.bars
                    if bar.symbol == missing_symbol
                )
            )
        ),
    )

    blocked = _run_fixture(
        tmp_path=tmp_path,
        provider_result=result,
        source_manifest=manifest,
    )

    assert blocked.record.status is DailyRunStatus.DATA_BLOCKED
    assert blocked.decision_artifact.bundle.prediction_runs == ()
    assert any(
        reason.startswith(f"FEATURE_MISSING:{missing_symbol}:")
        for reason in blocked.decision_artifact.bundle.data_quality_report.blocked_reason_codes
    )


def test_outcome_not_arrived_keeps_run_pending(
    tmp_path: Path,
) -> None:
    runner, command, archive = _replay_runner(tmp_path)
    daily = runner.run(command, replay_archive_path=archive)
    assert daily.record.daily_run_id is not None
    settlement_archive = _empty_settlement_archive(tmp_path)

    with pytest.raises(OutcomeNotReadyError, match="no exact"):
        runner.settle_daily_run(
            daily.record.daily_run_id,
            settlement_archive_path=settlement_archive,
        )

    assert runner.run(command).record.status is DailyRunStatus.OUTCOME_PENDING


def test_operational_loop_never_inflates_research_or_trading_authority(
    tmp_path: Path,
) -> None:
    runner, command, archive = _replay_runner(tmp_path)

    result = runner.run(command, replay_archive_path=archive)

    bundle = result.decision_artifact.bundle
    assert bundle.source_manifest.data_eligibility is DataEligibility.EXPLORATORY
    assert all(
        item.data_eligibility is DataEligibility.EXPLORATORY
        for item in bundle.prediction_runs
    )
    assert all(
        item.data_eligibility is DataEligibility.EXPLORATORY
        for item in bundle.recommendations
    )
    assert all(
        item.data_eligibility is DataEligibility.EXPLORATORY
        for item in bundle.entry_assessments
    )
    assert result.decision_artifact.manifest["formal_oos_authority"] == (
        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    )
    assert result.decision_artifact.manifest["trading_authority"] == (
        "TRADING_AUTHORITY_NOT_GRANTED"
    )


def _replay_runner(
    tmp_path: Path,
) -> tuple[DailyLoopRunner, DailyRunCommand, Path]:
    policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(policy=policy)
    archive = publish_source_archive(
        root=tmp_path / "fixture-archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = _command(
        tmp_path=tmp_path,
        source_manifest_id=source_manifest.source_manifest_id,
    )
    runner = DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    )
    return runner, command, archive


def _run_fixture(
    *,
    tmp_path: Path,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
):
    archive = publish_source_archive(
        root=tmp_path / "fixture-archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = _command(
        tmp_path=tmp_path,
        source_manifest_id=source_manifest.source_manifest_id,
    )
    return DailyLoopRunner(
        repository=SQLiteDailyRunRepository(tmp_path / "runtime.sqlite3"),
        code_revision=CODE_REVISION,
        clock=lambda: datetime(2025, 2, 3, 15, 0, tzinfo=SHANGHAI),
    ).run(command, replay_archive_path=archive)


def _command(
    *,
    tmp_path: Path,
    source_manifest_id: ArtifactId,
) -> DailyRunCommand:
    policy = smoke_pool_policy_v1()
    return DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.REPLAY,
        provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-test-config-v1"),
        output_root=tmp_path / "runtime",
        replay_source_manifest_id=source_manifest_id,
    )


def _artifact_counts(root: Path) -> tuple[int, int, int]:
    return tuple(
        len(tuple((root / name).iterdir()))
        for name in ("source_archives", "prediction_runs", "daily_decisions")
    )


def _settlement_archive(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    next_session: date = date(2025, 2, 4),
) -> Path:
    retrieved = RetrievedAt(
        datetime(
            next_session.year,
            next_session.month,
            next_session.day,
            10,
            31,
            tzinfo=SHANGHAI,
        )
    )
    source = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-next-session-1030",
        locator="archive://fixture/next-session-1030",
        raw_payload=f"runner-next-session-1030:{next_session}".encode(),
        retrieved_time=retrieved,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=DecisionTime(
            datetime(
                next_session.year,
                next_session.month,
                next_session.day,
                14,
                55,
                tzinfo=SHANGHAI,
            )
        ),
        raw_payloads=(source,),
        bars=tuple(
            PublicBar(
                symbol=symbol,
                event_time=datetime(
                    next_session.year,
                    next_session.month,
                    next_session.day,
                    10,
                    30,
                    tzinfo=SHANGHAI,
                ),
                available_time=AvailabilityTime(
                    datetime(
                        next_session.year,
                        next_session.month,
                        next_session.day,
                        10,
                        31,
                        tzinfo=SHANGHAI,
                    )
                ),
                source_artifact_id=source.source_artifact_id,
                open=10.5,
                high=10.8,
                low=10.4,
                close=10.605,
                volume=1_000_000.0,
                amount=20_000_000.0,
                unit="CNY",
                adjustment_basis="NONE",
                finality=SourceFieldFinality.PRELIMINARY,
            )
            for symbol in symbols
        ),
        quotes=(),
        source_conflicts=(),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    manifest = SourceManifest(
        provider_profile_id=result.profile_id,
        decision_time=result.decision_time,
        source_artifacts=result.source_artifact_references,
        fields=(),
        source_conflicts=(),
        limitations=("SETTLEMENT_ARCHIVE_ONLY",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return publish_source_archive(
        root=tmp_path / "settlement-archives",
        provider_result=result,
        source_manifest=manifest,
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        item.name: f"sha256:{sha256(item.read_bytes()).hexdigest()}"
        for item in root.iterdir()
    }


def _empty_settlement_archive(tmp_path: Path) -> Path:
    source = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-next-session-pending",
        locator="archive://fixture/next-session-pending",
        raw_payload=b"runner-next-session-pending",
        retrieved_time=RetrievedAt(
            datetime(2025, 2, 4, 9, 30, tzinfo=SHANGHAI)
        ),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=DecisionTime(
            datetime(2025, 2, 4, 9, 30, tzinfo=SHANGHAI)
        ),
        raw_payloads=(source,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("OUTCOME_NOT_ARRIVED",),
    )
    manifest = SourceManifest(
        provider_profile_id=result.profile_id,
        decision_time=result.decision_time,
        source_artifacts=result.source_artifact_references,
        fields=(),
        source_conflicts=(),
        limitations=("SETTLEMENT_ARCHIVE_ONLY",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return publish_source_archive(
        root=tmp_path / "settlement-archives",
        provider_result=result,
        source_manifest=manifest,
    )


def _next_weekday(value: date) -> date:
    candidate = value
    while True:
        candidate = candidate.fromordinal(candidate.toordinal() + 1)
        if candidate.weekday() < 5:
            return candidate
