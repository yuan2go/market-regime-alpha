from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from market_regime_alpha.application.runtime_operations.preflight import (
    PreflightCheck,
    PreflightReport,
    PreflightStatus,
)
from market_regime_alpha.application.runtime_operations.query import (
    CanonicalDagNode,
    CanonicalDagNodeStatus,
    CanonicalDagNodeType,
)


NOW = datetime(2026, 8, 9, 6, 54, tzinfo=UTC)


def test_preflight_report_uses_worst_check_and_machine_reason_codes() -> None:
    report = PreflightReport.create(
        checked_at=NOW,
        trading_date=date(2026, 8, 10),
        checks=(
            PreflightCheck.ready("POSTGRESQL", details={"server": "16"}),
            PreflightCheck.degraded(
                "LEASE",
                reason_codes=("STALE_LEASE_RECOVERABLE",),
            ),
            PreflightCheck.blocked(
                "MODEL_GOVERNANCE",
                reason_codes=("CHAMPION_AUTHORITY_MISSING",),
            ),
        ),
    )

    assert report.status is PreflightStatus.BLOCKED
    assert report.reason_codes == (
        "CHAMPION_AUTHORITY_MISSING",
        "STALE_LEASE_RECOVERABLE",
    )
    assert report.grants_trading_authority is False
    assert report.to_canonical_dict()["status"] == "BLOCKED"


def test_preflight_contract_rejects_unordered_or_duplicate_reasons() -> None:
    with pytest.raises(ValueError, match="sorted"):
        PreflightCheck(
            check_name="MODEL_GOVERNANCE",
            status=PreflightStatus.BLOCKED,
            reason_codes=("Z", "A"),
            details={},
        )


def test_canonical_dag_node_is_a_read_only_identity_projection(tmp_path: Path) -> None:
    node = CanonicalDagNode.create(
        node_type=CanonicalDagNodeType.SUMMARY,
        owner="DECISION_SYSTEM",
        artifact_id="research-daily-summary-abc",
        content_hash="sha256:" + "a" * 64,
        status=CanonicalDagNodeStatus.AVAILABLE,
        observed_at=NOW,
        parent_node_ids=("node-a",),
        reason_codes=("RESEARCH_CANDIDATE",),
        details={"path": str(tmp_path)},
    )

    assert node.node_id.startswith("runtime-dag-node-")
    assert node.to_canonical_dict()["owner"] == "DECISION_SYSTEM"
    assert node.read_only is True
