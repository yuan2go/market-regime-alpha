from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from market_regime_alpha.application.operational_research.supplemental_artifact import (
    publish_supplemental_research_evidence,
)
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from scripts.build_composite_operational_manifest import main
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _policy,
)
from tests.daily_decision.conftest import DailyDecisionFixture
from tests.postgres_path_repositories import postgres_cli_arguments


def test_build_composite_cli_persists_and_replays_decision_only_manifest(
    tmp_path: Path,
    capsys,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily",
        bundle=_daily_bundle(daily_decision_fixture),
    )
    supplemental = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental",
        bundle=_supplemental(daily_decision_fixture),
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(_policy().to_canonical_dict()), encoding="utf-8"
    )
    args = (
        "--daily-artifact",
        str(daily),
        "--supplemental-artifact",
        str(supplemental),
        "--composition-policy",
        str(policy_path),
        *postgres_cli_arguments(tmp_path / "h6.postgres-scope"),
        "--output-root",
        str(tmp_path / "composite"),
        "--created-at",
        (
            daily_decision_fixture.source_manifest.decision_time.value
            + timedelta(minutes=10)
        ).isoformat(),
        "--idempotency-key",
        "h6-cli-command",
    )

    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args) == 0
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["status"] == "VERIFIED"
    assert first["MANIFEST_ONLY"] is True
    assert first["NO_RESEARCH_MODEL_RUN"] is True
    assert first["NO_TRADE_ACTION_CREATED"] is True
    assert first["TRADING_AUTHORITY_NOT_GRANTED"] is True
    assert len(tuple((tmp_path / "composite").iterdir())) == 1
