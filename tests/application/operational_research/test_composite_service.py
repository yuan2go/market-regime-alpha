from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from market_regime_alpha.application.operational_research.composite_service import (
    CompositeOperationalEvidenceApplicationService,
)
from tests.postgres_path_repositories import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    publish_supplemental_research_evidence,
)
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _policy,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _paths(tmp_path: Path, fixture: DailyDecisionFixture) -> tuple[Path, Path]:
    return (
        publish_phase_d_daily_decision_artifact(
            root=tmp_path / "daily", bundle=_daily_bundle(fixture)
        ),
        publish_supplemental_research_evidence(
            root=tmp_path / "supplemental", bundle=_supplemental(fixture)
        ),
    )


def test_service_runs_file_first_and_replays_same_command(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path = _paths(tmp_path, daily_decision_fixture)
    repository = PostgresCompositeOperationalRepository(tmp_path / "h6.postgres-scope")
    service = CompositeOperationalEvidenceApplicationService(repository)
    created_at = daily_decision_fixture.source_manifest.decision_time.value + (
        timedelta(minutes=10)
    )

    first = service.build_and_publish(
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        composition_policy=_policy(),
        package_root=tmp_path / "composite",
        created_at=created_at,
        idempotency_key="h6-service-1",
    )
    second = service.build_and_publish(
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        composition_policy=_policy(),
        package_root=tmp_path / "composite",
        created_at=created_at,
        idempotency_key="h6-service-1",
    )

    assert first == second
    assert first.root.is_dir()
    assert repository.get_manifest(first.manifest.manifest_id) == first


def test_service_rejects_same_key_for_another_semantic_command(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path = _paths(tmp_path, daily_decision_fixture)
    repository = PostgresCompositeOperationalRepository(tmp_path / "h6.postgres-scope")
    service = CompositeOperationalEvidenceApplicationService(repository)
    created_at = daily_decision_fixture.source_manifest.decision_time.value + (
        timedelta(minutes=10)
    )
    service.build_and_publish(
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        composition_policy=_policy(),
        package_root=tmp_path / "composite",
        created_at=created_at,
        idempotency_key="h6-service-conflict",
    )

    with pytest.raises(ValueError, match="idempotency key"):
        service.build_and_publish(
            daily_package_path=daily_path,
            supplemental_package_path=supplemental_path,
            composition_policy=_policy(),
            package_root=tmp_path / "composite",
            created_at=created_at + timedelta(seconds=1),
            idempotency_key="h6-service-conflict",
        )


def test_crash_after_package_publish_is_repaired_by_idempotent_replay(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path = _paths(tmp_path, daily_decision_fixture)
    repository = PostgresCompositeOperationalRepository(tmp_path / "h6.postgres-scope")
    service = CompositeOperationalEvidenceApplicationService(repository)
    created_at = daily_decision_fixture.source_manifest.decision_time.value + (
        timedelta(minutes=10)
    )

    with pytest.raises(RuntimeError, match="after publish"):
        service.build_and_publish(
            daily_package_path=daily_path,
            supplemental_package_path=supplemental_path,
            composition_policy=_policy(),
            package_root=tmp_path / "composite",
            created_at=created_at,
            idempotency_key="h6-service-repair",
            after_package_publish=lambda _: (_ for _ in ()).throw(
                RuntimeError("injected after publish")
            ),
        )
    assert len(tuple((tmp_path / "composite").iterdir())) == 1

    repaired = service.build_and_publish(
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        composition_policy=_policy(),
        package_root=tmp_path / "composite",
        created_at=created_at,
        idempotency_key="h6-service-repair",
    )
    assert repository.get_manifest(repaired.manifest.manifest_id) == repaired
