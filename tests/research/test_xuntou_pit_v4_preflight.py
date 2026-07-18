from pathlib import Path

from market_regime_alpha.research.xuntou_pit_v4_preflight import (
    XuntouPITV4PreflightStatus,
    preflight_xuntou_pit_v4,
)


def test_missing_bundle_is_explicit_external_blocker() -> None:
    result = preflight_xuntou_pit_v4(None)
    assert result.status is XuntouPITV4PreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT
    assert result.tencent_fallback_used is False


def test_v3_bundle_cannot_masquerade_as_v4(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"schema_version":"xuntou-p0-native-bundle-v3"}', encoding="utf-8")
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    assert "V3_REHEARSAL_BUNDLE_CANNOT_BE_PROMOTED" in result.reasons


def test_test_only_fixture_is_not_formal_research_input(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"schema_version":"xuntou-pit-validation-bundle-v4",'
        '"evidence_classification":"TEST_ONLY_NOT_RESEARCH_EVIDENCE"}',
        encoding="utf-8",
    )
    result = preflight_xuntou_pit_v4(bundle)
    assert result.status is XuntouPITV4PreflightStatus.INVALID_PIT_EVIDENCE
    assert "TEST_FIXTURE_NOT_RESEARCH_EVIDENCE" in result.reasons


def test_source_byte_change_changes_preflight_identity(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"schema_version":"bad-v1"}', encoding="utf-8")
    first = preflight_xuntou_pit_v4(bundle)
    bundle.write_text('{"schema_version":"bad-v2"}', encoding="utf-8")
    second = preflight_xuntou_pit_v4(bundle)
    assert first.bundle_content_hash != second.bundle_content_hash
