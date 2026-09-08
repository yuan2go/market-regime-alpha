from __future__ import annotations

import json

import pytest

from market_regime_alpha.legacy.inspect_runtime import main
from tests.research.state_system.test_pool import (
    config,
    context,
    lineage,
    member,
)
from market_regime_alpha.research.state_system.pool import evaluate_dynamic_pool


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

    assert main(["verify-pool", "--artifact", str(artifact)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["scope"] == "HISTORICAL_READ_ONLY"
    assert output["result"]["pool_id"] == str(pool.pool_id)
    assert output["current_execution_authority"] is False


def test_verify_pool_fails_closed_on_tampering(tmp_path, capsys) -> None:
    artifact = tmp_path / "pool.json"
    artifact.write_text('{"pool_id":"forged","pool_hash":"forged"}', encoding="utf-8")

    assert (
        main(["verify-pool", "--artifact", str(artifact)])
        == 2
    )

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "REJECTED"
    assert output["current_execution_authority"] is False


@pytest.mark.parametrize("operation", ("prepare", "schedule", "run-due", "settle"))
def test_historical_surface_rejects_execution_before_database_access(operation, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main([operation])
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
