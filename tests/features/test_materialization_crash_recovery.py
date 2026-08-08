from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tests.postgres_path_repositories import postgres_connection

import pytest

from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
)
from tests.postgres_path_repositories import (
    PostgresFeatureMaterializationRunRepository,
    feature_repository_factory,
)
from market_regime_alpha.features.materialization_v2 import (
    FeatureMaterializationHardCrash,
    FeatureMaterializationRunner,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.technical.catalog import (
    canonical_technical_feature_set,
)

from .test_materialization_runner_v2 import (
    CREATED_AT,
    DECISION_TIME,
    UTC,
    _verified_dataset,
)


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


@pytest.mark.parametrize(
    "crash_stage",
    (
        "AFTER_TASK_CLAIMED",
        "AFTER_ARTIFACT_PUBLISHED",
        "AFTER_TASK_COMPLETED",
        "BEFORE_BUNDLE_PUBLICATION",
        "AFTER_BUNDLE_PUBLISHED",
    ),
)
def test_hard_crash_boundaries_resume_to_one_receipt_and_explainable_history(
    tmp_path: Path,
    crash_stage: str,
) -> None:
    clock = MutableClock(datetime(2026, 8, 5, 6, 40, tzinfo=timezone.utc))
    dataset = _verified_dataset(tmp_path)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    runner = FeatureMaterializationRunner(
        max_workers=1,
        clock=clock,
        lease_duration=timedelta(seconds=30),
        repository_factory=feature_repository_factory(
            tmp_path / "run.postgres-scope",
            fallback_clock=clock,
        ),
    )
    fired = False

    def crash(stage: str) -> None:
        nonlocal fired
        if stage == crash_stage and not fired:
            fired = True
            raise FeatureMaterializationHardCrash(stage)

    with pytest.raises(FeatureMaterializationHardCrash, match=crash_stage):
        runner.run(
            verified_dataset=dataset,
            feature_set=feature_set,
            decision_time=DECISION_TIME,
            created_at=CREATED_AT,
            selected_symbols=("600000.SH",),
            code_revision="crash-recovery-v1",
            output_root=tmp_path / "features",
            idempotency_key="crash-recovery",
            execution_mode=FeatureMaterializationExecutionMode.START_NEW,
            failure_injector=crash,
        )

    clock.advance(timedelta(seconds=31))
    receipt = runner.run(
        verified_dataset=dataset,
        feature_set=feature_set,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        selected_symbols=("600000.SH",),
        code_revision="crash-recovery-v1",
        output_root=tmp_path / "features",
        idempotency_key="crash-recovery",
        execution_mode=FeatureMaterializationExecutionMode.RESUME_EXISTING,
    )
    bundle = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    assert len(bundle.artifacts) == 7
    assert len(tuple((tmp_path / "features" / "feature-artifacts").glob("feature-*"))) == 7

    repository = PostgresFeatureMaterializationRunRepository(
        tmp_path / "run.postgres-scope",
        clock=clock,
    )
    snapshot = repository.snapshot(1)
    event_types = tuple(item[1] for item in snapshot.events)
    assert "RUN_RESUMED" in event_types
    assert "RUN_COMPLETED" in event_types
    if crash_stage in {
        "AFTER_TASK_CLAIMED",
        "AFTER_ARTIFACT_PUBLISHED",
        "AFTER_TASK_COMPLETED",
    }:
        assert "LEASE_EXPIRED" in event_types
    if crash_stage == "AFTER_ARTIFACT_PUBLISHED":
        completed_payloads = tuple(
            payload
            for _, event_type, _, payload in snapshot.events
            if event_type == "TASK_COMPLETED"
        )
        assert any('"publication_reused":true' in item for item in completed_payloads)
    if crash_stage == "AFTER_BUNDLE_PUBLISHED":
        assert event_types.count("BUNDLE_PUBLISHED") == 2
    with postgres_connection(tmp_path / "run.postgres-scope") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM feature_materialization_receipt"
        ).fetchone() == (1,)
