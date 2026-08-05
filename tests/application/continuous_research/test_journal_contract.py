from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    RuntimeArtifactReference,
    RuntimeTickReceipt,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 6, 6, 42, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64


def _claim() -> ClaimedRuntimeTick:
    return ClaimedRuntimeTick(
        run_id=ArtifactId("continuous-run-fixture"),
        tick_id=ArtifactId("continuous-tick-fixture"),
        tick_sequence=1,
        claim_id="claim-fixture",
        fencing_token=2,
        tick_version=4,
        lease_acquired_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        heartbeat_at=NOW,
    )


def test_tick_receipt_is_content_addressed_and_bound_to_active_fence() -> None:
    receipt = RuntimeTickReceipt.create(
        claim=_claim(),
        input_references=(
            RuntimeArtifactReference(
                reference_kind="EVIDENCE_COMMIT",
                artifact_id=ArtifactId("evidence-fixture"),
                content_hash=HASH_1,
            ),
        ),
        output_references=(
            RuntimeArtifactReference(
                reference_kind="CHANGE_DECISION",
                artifact_id=ArtifactId("decision-fixture"),
                content_hash=HASH_2,
            ),
        ),
        reason_codes=("TICK_ENGINEERING_VERIFIED",),
        created_at=NOW,
    )

    assert str(receipt.receipt_id).startswith("continuous-tick-receipt-")
    assert receipt.fencing_token == 2
    assert RuntimeTickReceipt.from_canonical_dict(
        receipt.to_canonical_dict()
    ) == receipt
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(receipt, receipt_hash="sha256:" + "0" * 64)


def test_claim_rejects_invalid_lease_or_version() -> None:
    with pytest.raises(ValueError, match="lease"):
        replace(_claim(), lease_expires_at=NOW)
    with pytest.raises(ValueError, match="tick_version"):
        replace(_claim(), tick_version=0)
