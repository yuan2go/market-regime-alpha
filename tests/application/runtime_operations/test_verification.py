from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_regime_alpha.application.runtime_operations.verification import (
    CIStatus,
    EngineeringReadiness,
    EngineeringVerificationRecord,
    REQUIRED_LOCAL_GATES,
    VerificationGateResult,
    VerificationStatus,
    load_engineering_verification,
    publish_engineering_verification,
)


def test_engineering_verification_is_sha_bound_and_content_addressed(
    tmp_path: Path,
) -> None:
    record = _record()

    path = publish_engineering_verification(root=tmp_path, record=record)

    assert load_engineering_verification(path) == record
    assert record.readiness is EngineeringReadiness.ENGINEERING_READY
    assert record.ci_status is CIStatus.EXTERNAL_BLOCKED
    assert record.commit_sha == "a" * 40


def test_engineering_ready_cannot_hide_failed_or_dirty_gate() -> None:
    gates = list(_gates())
    gates[2] = VerificationGateResult(
        gate="PYTEST",
        command=("uv", "run", "pytest"),
        status=VerificationStatus.FAIL,
        exit_code=1,
        duration_seconds=1.0,
        output_sha256="b" * 64,
        summary="1 failed",
    )

    with pytest.raises(ValueError, match="readiness"):
        EngineeringVerificationRecord.create(
            **_record_values(
                gates=tuple(gates),
                readiness=EngineeringReadiness.ENGINEERING_READY,
            )
        )


def _record() -> EngineeringVerificationRecord:
    return EngineeringVerificationRecord.create(**_record_values())


def _record_values(**overrides):
    values = {
        "commit_sha": "a" * 40,
        "python_version": "3.12.2",
        "uv_version": "uv 0.8.15",
        "postgres_version": "16.14",
        "migration_head": 37,
        "application_schema": "market_regime_alpha",
        "environment": "test",
        "dirty_worktree": False,
        "gates": _gates(),
        "ci_status": CIStatus.EXTERNAL_BLOCKED,
        "readiness": EngineeringReadiness.ENGINEERING_READY,
        "verified_at": datetime(2026, 8, 9, 8, 0, tzinfo=UTC),
        "limitations": (
            "ENGINEERING_EVIDENCE_ONLY",
            "NOT_ALPHA_EVIDENCE",
            "NOT_LIVE_EVIDENCE",
            "NOT_PRODUCTION_AUTHORIZATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
    }
    values.update(overrides)
    return values


def _gates() -> tuple[VerificationGateResult, ...]:
    return tuple(
        VerificationGateResult(
            gate=gate,
            command=("verify", gate.lower()),
            status=VerificationStatus.PASS,
            exit_code=0,
            duration_seconds=1.123456,
            output_sha256="b" * 64,
            summary="passed",
        )
        for gate in REQUIRED_LOCAL_GATES
    )
