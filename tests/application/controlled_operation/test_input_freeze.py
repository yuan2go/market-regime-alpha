from __future__ import annotations

from pathlib import Path

import pytest

from market_regime_alpha.application.controlled_operation.runner import _install_input
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledDecisionTimeOperationRunner,
)
from market_regime_alpha.application.controlled_operation.journal import (
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    OperationArtifactReference,
)
from tests.postgres_path_repositories import (
    PostgresDecisionTimeOperationJournal,
    controlled_runner_dependencies,
)
from market_regime_alpha.core.identity import ArtifactId
from tests.application.controlled_operation.test_journal import HASH, HASH_2, NOW, _command


def test_frozen_input_rejects_different_source_on_resume(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    destination = tmp_path / "frozen" / "artifact"
    first.mkdir()
    second.mkdir()
    (first / "artifact.json").write_text('{"value":1}', encoding="utf-8")
    (second / "artifact.json").write_text('{"value":2}', encoding="utf-8")

    assert _install_input(source=first, destination=destination) == destination
    with pytest.raises(ValueError, match="frozen input identity conflict"):
        _install_input(source=second, destination=destination)


def test_frozen_input_accepts_identical_bytes_from_another_locator(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    same = tmp_path / "same"
    destination = tmp_path / "frozen" / "artifact"
    first.mkdir()
    same.mkdir()
    (first / "artifact.json").write_text('{"value":1}', encoding="utf-8")
    (same / "artifact.json").write_text('{"value":1}', encoding="utf-8")

    _install_input(source=first, destination=destination)

    assert _install_input(source=same, destination=destination) == destination


def test_completed_stage_rejects_recomputed_receipt_divergence(
    tmp_path: Path,
) -> None:
    journal = PostgresDecisionTimeOperationJournal(
        tmp_path / "journal.postgres-scope",
        clock=lambda: NOW,
    )
    command = _command()
    journal.create_or_get(command)
    runner = ControlledDecisionTimeOperationRunner(
        journal=journal,
        output_root=tmp_path / "operations",
        clock=lambda: NOW,
        **controlled_runner_dependencies(
            tmp_path / "journal.postgres-scope",
            clock=lambda: NOW,
        ),
    )
    inputs = (
        OperationArtifactReference("INPUT", ArtifactId("input"), HASH),
    )
    outputs = (
        OperationArtifactReference("OUTPUT", ArtifactId("output"), HASH),
    )
    runner._execute_stage(
        command=command,
        stage=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
        run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
        inputs=inputs,
        outputs=outputs,
        reasons=("VERIFIED",),
        latency_sink={},
    )

    with pytest.raises(ValueError, match="Receipt conflicts"):
        runner._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
            inputs=inputs,
            outputs=(
                OperationArtifactReference(
                    "OUTPUT",
                    ArtifactId("output"),
                    HASH_2,
                ),
            ),
            reasons=("VERIFIED",),
            latency_sink={},
        )
