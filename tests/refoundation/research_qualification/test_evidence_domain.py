from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.evidence import (
    EvidenceClass,
    EvidenceDependencyPlan,
    EvidenceDependencyRole,
    EvidenceDirection,
    EvidenceItemPlan,
    EvidenceOriginClass,
    EvidenceRole,
    EvidenceScope,
    ResearchProofClass,
)


_HASH = "a" * 64


def _dependency(ordinal: int = 1, *, parent_id=None) -> EvidenceDependencyPlan:
    return EvidenceDependencyPlan(
        evidence_dependency_id=uuid4(),
        parent_evidence_item_id=parent_id or uuid4(),
        ordinal=ordinal,
        dependency_role=EvidenceDependencyRole.DERIVED_FROM,
    )


def _item(**changes: object) -> EvidenceItemPlan:
    values: dict[str, object] = {
        "evidence_item_id": uuid4(),
        "evaluation_run_id": uuid4(),
        "evaluation_metric_id": None,
        "evidence_code": "evaluation-result",
        "scope": EvidenceScope.RUN,
        "evidence_class": EvidenceClass.RESEARCH_RESULT,
        "origin_class": EvidenceOriginClass.DERIVED_CANONICAL,
        "role": EvidenceRole.PRIMARY_RESULT,
        "direction": EvidenceDirection.SUPPORT,
        "proof_ceiling": ResearchProofClass.EXPLORATORY,
        "observed_at": datetime(2026, 8, 1, tzinfo=UTC),
        "evidence_artifact": ArtifactBinding(uuid4(), _HASH, 12),
        "code_artifact": ArtifactBinding(uuid4(), "b" * 64, 13),
        "config_artifact": ArtifactBinding(uuid4(), "c" * 64, 14),
        "provenance_sha256": "d" * 64,
        "dependencies": (),
    }
    values.update(changes)
    return EvidenceItemPlan(**values)  # type: ignore[arg-type]


def test_run_scope_forbids_metric_and_metric_scope_requires_one() -> None:
    with pytest.raises(ValueError, match="RUN-scoped"):
        _item(evaluation_metric_id=uuid4())
    with pytest.raises(ValueError, match="METRIC-scoped"):
        _item(scope=EvidenceScope.METRIC)
    item = _item(scope=EvidenceScope.METRIC, evaluation_metric_id=uuid4())
    assert item.scope is EvidenceScope.METRIC


def test_dependency_roster_is_ordered_unique_and_hashed() -> None:
    item = _item(dependencies=(_dependency(1), _dependency(2)))
    assert item.dependency_count == 2
    assert len(str(item.dependency_roster_sha256)) == 64
    with pytest.raises(ValueError, match="contiguous"):
        _item(dependencies=(_dependency(2),))
    parent = uuid4()
    with pytest.raises(ValueError, match="duplicate"):
        _item(dependencies=(_dependency(1, parent_id=parent), _dependency(2, parent_id=parent)))


def test_evidence_cannot_depend_on_itself() -> None:
    item_id = uuid4()
    with pytest.raises(ValueError, match="itself"):
        _item(
            evidence_item_id=item_id,
            dependencies=(_dependency(parent_id=item_id),),
        )


def test_evidence_identity_changes_with_direction_and_dependencies() -> None:
    item = _item()
    assert item.content_sha256 != replace(item, direction=EvidenceDirection.COUNTER).content_sha256
    assert item.content_sha256 != replace(item, dependencies=(_dependency(),)).content_sha256


def test_observed_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _item(observed_at=datetime(2026, 8, 1))
