from __future__ import annotations

import pytest

from scripts.prepare_golden_loop_v2_campaign import (
    _reference_from_text,
    _references,
)


def test_superseded_evidence_reference_preserves_exact_owner_identity() -> None:
    value = (
        "HISTORICAL_ALPHA_ABLATION_EVIDENCE|"
        "historical-evidence-old|"
        f"sha256:{'a' * 64}"
    )

    reference = _reference_from_text(value)

    assert reference.artifact_kind == "HISTORICAL_ALPHA_ABLATION_EVIDENCE"
    assert str(reference.artifact_id) == "historical-evidence-old"
    assert reference.content_hash == f"sha256:{'a' * 64}"
    assert _references((reference, reference)) == (reference,)


def test_superseded_evidence_reference_fails_closed_when_incomplete() -> None:
    with pytest.raises(ValueError, match=r"KIND\|ID\|SHA256"):
        _reference_from_text("missing-fields")
