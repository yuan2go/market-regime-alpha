from __future__ import annotations

import json

from market_regime_alpha.cli.state_system import (
    ARGUMENT_OR_INTEGRITY_ERROR,
    SUCCESS,
    main,
)
from tests.research.state_system.test_pool import (
    config,
    context,
    lineage,
    member,
)
from market_regime_alpha.research.state_system.pool import evaluate_dynamic_pool


def test_describe_exposes_order_and_fail_closed_authority(capsys) -> None:
    assert main(["describe"]) == SUCCESS

    output = json.loads(capsys.readouterr().out)

    assert output["runtime_owner"] == "CONTINUOUS_RESEARCH"
    assert output["stage_order"] == [
        "OBSERVATION",
        "MARKET_REGIME",
        "ETF_ROTATION",
        "THEME_ROTATION",
        "CAPITAL_STATE",
        "DYNAMIC_POOL",
        "CANDIDATE",
        "SIGNAL",
        "FORECAST",
    ]
    assert output["entry_authority_granted"] is False
    assert output["broker_authority_granted"] is False
    assert output["daily_decision_window_summary_delivered"] is False


def test_verify_pool_reads_content_validating_artifact(tmp_path, capsys) -> None:
    pool = evaluate_dynamic_pool(
        state_context=context(),
        eligibility=(member("600000.SH"), member("600001.SH", eligible=False)),
        previous=None,
        configuration=config(),
        lineage=lineage(),
    ).pool
    artifact = tmp_path / "pool.json"
    artifact.write_text(json.dumps(pool.to_canonical_dict()), encoding="utf-8")

    assert main(["verify-pool", "--artifact", str(artifact)]) == SUCCESS

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "VERIFIED"
    assert output["pool_id"] == str(pool.pool_id)
    assert output["entry_authority_granted"] is False


def test_verify_pool_fails_closed_on_tampering(tmp_path, capsys) -> None:
    artifact = tmp_path / "pool.json"
    artifact.write_text('{"pool_id":"forged","pool_hash":"forged"}', encoding="utf-8")

    assert (
        main(["verify-pool", "--artifact", str(artifact)])
        == ARGUMENT_OR_INTEGRITY_ERROR
    )

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAILED"
    assert output["broker_authority_granted"] is False
