from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from market_regime_alpha.features.technical.moving_average import (
    SimpleMovingAverageComputer,
)
from market_regime_alpha.migration.comparison.artifact import (
    MODEL_COMPARISON_REPORT_FILES,
    load_verified_model_comparison_report,
    publish_model_comparison_report,
    replay_model_comparison_report,
)
from market_regime_alpha.migration.comparison.contracts import ComparisonPolicy
from market_regime_alpha.migration.comparison.harness import DifferentialTestHarness
from market_regime_alpha.migration.legacy.adapters.moving_average import (
    LegacyMovingAverageAdapter,
)

from .test_legacy_moving_average_adapter import dataset


CREATED_AT = datetime(2026, 8, 4, 7, 1, tzinfo=timezone.utc)


def inputs() -> tuple[object, ...]:
    return (
        dataset(),
        LegacyMovingAverageAdapter(),
        SimpleMovingAverageComputer(),
        ComparisonPolicy.create(policy_version="1.0.0"),
    )


def report() -> object:
    data, legacy, canonical, policy = inputs()
    return DifferentialTestHarness().compare(
        dataset=data,
        legacy_adapter=legacy,
        canonical_model=canonical,
        policy=policy,
        created_at=CREATED_AT,
    )


def test_report_publisher_reader_and_replay_are_strict_and_idempotent(
    tmp_path: Path,
) -> None:
    original = report()
    path = publish_model_comparison_report(root=tmp_path, report=original)

    assert {item.name for item in path.iterdir()} == set(MODEL_COMPARISON_REPORT_FILES)
    assert publish_model_comparison_report(root=tmp_path, report=original) == path
    verified = load_verified_model_comparison_report(path)
    assert verified.report.to_canonical_dict() == original.to_canonical_dict()

    data, legacy, canonical, policy = inputs()
    replayed = replay_model_comparison_report(
        path,
        dataset=data,
        legacy_adapter=legacy,
        canonical_model=canonical,
        policy=policy,
    )
    assert replayed.report.report_hash == original.report_hash


def test_republish_same_semantics_preserves_first_audit_timestamp(
    tmp_path: Path,
) -> None:
    original = report()
    first_path = publish_model_comparison_report(root=tmp_path, report=original)
    later = replace(
        original,
        created_at=datetime(2026, 8, 4, 8, 1, tzinfo=timezone.utc),
    )

    second_path = publish_model_comparison_report(root=tmp_path, report=later)

    assert second_path == first_path
    verified = load_verified_model_comparison_report(second_path)
    assert verified.report.created_at == original.created_at
    assert verified.report.report_hash == later.report_hash


def test_report_reader_rejects_checksum_and_unexpected_file(tmp_path: Path) -> None:
    path = publish_model_comparison_report(root=tmp_path, report=report())
    (path / "report.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_model_comparison_report(path)

    second_root = tmp_path / "second"
    second = publish_model_comparison_report(root=second_root, report=report())
    (second / "extra.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact file set"):
        load_verified_model_comparison_report(second)


def test_report_reader_rejects_semantic_tamper_with_rewritten_checksum(
    tmp_path: Path,
) -> None:
    path = publish_model_comparison_report(root=tmp_path, report=report())
    report_path = path / "report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["unexpected_difference"] = True
    report_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    checksum_path = path / "SHA256SUMS.json"
    checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
    checksums["report.json"] = (
        "sha256:" + hashlib.sha256(report_path.read_bytes()).hexdigest()
    )
    checksum_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="report hash mismatch"):
        load_verified_model_comparison_report(path)


def test_report_publisher_rejects_unbound_or_conflicting_content(
    tmp_path: Path,
) -> None:
    original = report()
    invalid = replace(original, unexpected_difference=True)
    with pytest.raises(ValueError, match="report hash mismatch"):
        publish_model_comparison_report(root=tmp_path, report=invalid)

    path = publish_model_comparison_report(root=tmp_path, report=original)
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_model_comparison_report(root=tmp_path, report=original)


def test_replay_rejects_wrong_dataset_model_or_policy(tmp_path: Path) -> None:
    original = report()
    path = publish_model_comparison_report(root=tmp_path, report=original)
    data, legacy, canonical, _ = inputs()
    wrong_policy = ComparisonPolicy.create(
        policy_version="2.0.0",
        expected_not_comparable_reason_codes=("SOMETHING_ELSE",),
    )

    with pytest.raises(ValueError, match="replay differs"):
        replay_model_comparison_report(
            path,
            dataset=data,
            legacy_adapter=legacy,
            canonical_model=canonical,
            policy=wrong_policy,
        )
