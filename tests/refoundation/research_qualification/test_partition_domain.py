from __future__ import annotations

from dataclasses import fields, replace
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
)


_HASH = "a" * 64


def _plan(**changes: object) -> ResearchPartitionPlan:
    values: dict[str, object] = {
        "research_partition_id": uuid4(),
        "partition_code": "mr1-validation",
        "target_definition_id": uuid4(),
        "target_version": 1,
        "target_definition_sha256": _HASH,
        "purpose": PartitionPurpose.VALIDATION,
        "population_scope": PartitionPopulationScope.ALL_COMMITMENTS,
        "overlap_policy": PartitionOverlapPolicy.PURGED_WALK_FORWARD,
        "decision_start_session_id": uuid4(),
        "decision_end_session_id": uuid4(),
        "purge_before_sessions": 1,
        "purge_after_sessions": 2,
        "embargo_sessions": 1,
        "series_code": "mr1-walk-forward",
        "fold_ordinal": 2,
        "code_artifact": ArtifactBinding(uuid4(), _HASH, 10),
        "config_artifact": ArtifactBinding(uuid4(), "b" * 64, 20),
        "provenance_sha256": "c" * 64,
    }
    values.update(changes)
    return ResearchPartitionPlan(**values)  # type: ignore[arg-type]


def test_partition_plan_has_no_caller_roster_field() -> None:
    names = {item.name for item in fields(ResearchPartitionPlan)}
    assert not names & {"members", "member_ids", "commitment_ids", "roster"}


@pytest.mark.parametrize(
    ("purpose", "policy"),
    [
        (PartitionPurpose.DISCOVERY, PartitionOverlapPolicy.DIAGNOSTIC_REUSE),
        (PartitionPurpose.FIT, PartitionOverlapPolicy.PURGED_WALK_FORWARD),
        (PartitionPurpose.VALIDATION, PartitionOverlapPolicy.DIAGNOSTIC_REUSE),
        (PartitionPurpose.LOCKED_OOS, PartitionOverlapPolicy.ISOLATED_PROTECTED),
        (PartitionPurpose.PROSPECTIVE, PartitionOverlapPolicy.ISOLATED_PROTECTED),
    ],
)
def test_partition_purpose_accepts_compatible_overlap_policy(
    purpose: PartitionPurpose,
    policy: PartitionOverlapPolicy,
) -> None:
    assert _plan(purpose=purpose, overlap_policy=policy).purpose is purpose


@pytest.mark.parametrize(
    ("purpose", "policy"),
    [
        (PartitionPurpose.DISCOVERY, PartitionOverlapPolicy.PURGED_WALK_FORWARD),
        (PartitionPurpose.FIT, PartitionOverlapPolicy.ISOLATED_PROTECTED),
        (PartitionPurpose.LOCKED_OOS, PartitionOverlapPolicy.DIAGNOSTIC_REUSE),
        (PartitionPurpose.PROSPECTIVE, PartitionOverlapPolicy.PURGED_WALK_FORWARD),
    ],
)
def test_partition_purpose_rejects_incompatible_overlap_policy(
    purpose: PartitionPurpose,
    policy: PartitionOverlapPolicy,
) -> None:
    with pytest.raises(ValueError, match="overlap"):
        _plan(purpose=purpose, overlap_policy=policy)


def test_partition_plan_rejects_invalid_session_protection() -> None:
    with pytest.raises(ValueError, match="purge_before_sessions"):
        _plan(purge_before_sessions=-1)
    with pytest.raises(ValueError, match="fold_ordinal"):
        _plan(fold_ordinal=0)


def test_partition_hash_is_stable_and_semantic() -> None:
    first = _plan()
    same = replace(first)
    changed = replace(first, population_scope=PartitionPopulationScope.SELECTED)
    assert first.content_sha256 == same.content_sha256
    assert changed.content_sha256 != first.content_sha256
