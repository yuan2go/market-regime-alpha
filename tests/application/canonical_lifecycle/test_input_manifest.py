from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json

import pytest

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    CanonicalLifecycleInputManifestReader,
    LifecycleAuthorityCeiling,
    validate_lifecycle_locator_policy,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.contracts import DataEligibility


UTC = timezone.utc
AS_OF = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def _reference(
    object_type: LifecycleObjectType,
    object_id: str,
    content_hash: str,
    reader_kind: LifecycleReaderKind,
    locator: str | None,
) -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(object_id),
        content_hash=content_hash,
        reader_kind=reader_kind,
        locator=locator,
        available_at=AS_OF,
    )


def _inputs() -> tuple[LifecycleObjectReference, ...]:
    return (
        _reference(
            LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
            "composite-1",
            _hash("a"),
            LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
            "artifacts/composite-1",
        ),
        _reference(
            LifecycleObjectType.DAILY_DECISION_ARTIFACT,
            "daily-1",
            _hash("b"),
            LifecycleReaderKind.DAILY_DECISION_ARTIFACT_READER,
            "artifacts/daily-1",
        ),
        _reference(
            LifecycleObjectType.SOURCE_MANIFEST,
            "source-1",
            _hash("c"),
            LifecycleReaderKind.SOURCE_MANIFEST_READER,
            "artifacts/source-1.json",
        ),
        _reference(
            LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
            "supplemental-1",
            _hash("d"),
            LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER,
            "artifacts/supplemental-1",
        ),
    )


def _configuration() -> LifecycleConfigurationReference:
    return LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.GENERIC,
        configuration_id=ArtifactId("research-configuration-1"),
        configuration_version="1.0.0",
        content_hash=_hash("e"),
        locator="configurations/research-configuration-1.json",
    )


def _model() -> LifecycleModelVersionReference:
    return LifecycleModelVersionReference(
        model_id=ModelId("research-model-1"),
        model_version="1.0.0",
        content_hash=_hash("f"),
    )


def _manifest() -> CanonicalLifecycleInputManifest:
    return CanonicalLifecycleInputManifest.create(
        decision_date=date(2026, 8, 4),
        as_of_time=AS_OF,
        created_at=AS_OF + timedelta(seconds=1),
        input_references=_inputs(),
        configuration_references=(_configuration(),),
        model_references=(_model(),),
        authority_ceiling=LifecycleAuthorityCeiling(),
        limitations=("ENTRY_MODEL_NOT_EMPIRICALLY_VALIDATED",),
    )


def test_manifest_is_content_addressed_and_round_trippable() -> None:
    manifest = _manifest()
    restored = CanonicalLifecycleInputManifest.from_canonical_dict(
        manifest.to_canonical_dict()
    )
    assert restored == manifest
    assert str(manifest.manifest_id).startswith("canonical-lifecycle-input-")
    assert manifest.content_hash.startswith("sha256:")
    assert [item.object_type for item in manifest.input_references] == sorted(
        (item.object_type for item in manifest.input_references),
        key=lambda item: item.value,
    )


def test_manifest_binds_actual_operational_research_reader_inputs() -> None:
    by_type = {item.object_type: item for item in _manifest().input_references}
    assert by_type[LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST].reader_kind is (
        LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER
    )
    assert by_type[LifecycleObjectType.DAILY_DECISION_ARTIFACT].reader_kind is (
        LifecycleReaderKind.DAILY_DECISION_ARTIFACT_READER
    )
    assert by_type[LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE].reader_kind is (
        LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER
    )


def test_file_reader_requires_locator_but_repository_reference_forbids_one() -> None:
    file_reference = _inputs()[0]
    with pytest.raises(ValueError, match="requires a controlled locator"):
        validate_lifecycle_locator_policy(replace(file_reference, locator=None))

    repository_reference = _reference(
        LifecycleObjectType.POSITION_BOOK,
        "position-book-1",
        _hash("9"),
        LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
        None,
    )
    validate_lifecycle_locator_policy(repository_reference)
    with pytest.raises(ValueError, match="forbids locator"):
        validate_lifecycle_locator_policy(
            replace(repository_reference, locator="state.sqlite3")
        )


def test_manifest_rejects_wrong_reader_and_post_as_of_availability() -> None:
    manifest = _manifest()
    wrong_reader = replace(
        manifest.input_references[0],
        reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
    )
    with pytest.raises(ValueError, match="requires Reader kind"):
        CanonicalLifecycleInputManifest.create(
            decision_date=manifest.decision_date,
            as_of_time=manifest.as_of_time,
            created_at=manifest.created_at,
            input_references=(wrong_reader, *manifest.input_references[1:]),
            configuration_references=manifest.configuration_references,
            model_references=manifest.model_references,
            authority_ceiling=manifest.authority_ceiling,
            limitations=manifest.limitations,
        )
    future = replace(manifest.input_references[0], available_at=AS_OF + timedelta(seconds=1))
    with pytest.raises(ValueError, match="not available"):
        CanonicalLifecycleInputManifest.create(
            decision_date=manifest.decision_date,
            as_of_time=manifest.as_of_time,
            created_at=manifest.created_at,
            input_references=(future, *manifest.input_references[1:]),
            configuration_references=manifest.configuration_references,
            model_references=manifest.model_references,
            authority_ceiling=manifest.authority_ceiling,
            limitations=manifest.limitations,
        )


def test_manifest_rejects_different_ids_bound_to_same_hash() -> None:
    inputs = _inputs()
    ambiguous = replace(inputs[1], content_hash=inputs[0].content_hash)
    with pytest.raises(ValueError, match="different object IDs"):
        CanonicalLifecycleInputManifest.create(
            decision_date=date(2026, 8, 4),
            as_of_time=AS_OF,
            created_at=AS_OF + timedelta(seconds=1),
            input_references=(inputs[0], ambiguous, *inputs[2:]),
            configuration_references=(_configuration(),),
            model_references=(_model(),),
            authority_ceiling=LifecycleAuthorityCeiling(),
            limitations=(),
        )


def test_authority_ceiling_cannot_be_inflated() -> None:
    with pytest.raises(ValueError, match="EXPLORATORY"):
        LifecycleAuthorityCeiling(data_eligibility=DataEligibility.FORMAL_RESEARCH)
    with pytest.raises(ValueError, match="automatic_order_execution"):
        LifecycleAuthorityCeiling(automatic_order_execution=True)
    with pytest.raises(ValueError, match="production_ready"):
        LifecycleAuthorityCeiling(production_ready=True)

    unqualified = LifecycleAuthorityCeiling(
        data_eligibility=DataEligibility.UNQUALIFIED
    )
    assert LifecycleAuthorityCeiling.from_canonical_dict(
        unqualified.to_canonical_dict()
    ).data_eligibility is DataEligibility.UNQUALIFIED


def test_strict_reader_verifies_expected_identity_hash_and_json_shape(tmp_path) -> None:
    manifest = _manifest()
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps(manifest.to_canonical_dict(), sort_keys=True), encoding="utf-8"
    )
    reader = CanonicalLifecycleInputManifestReader()
    assert reader.read(
        path,
        expected_manifest_id=manifest.manifest_id,
        expected_content_hash=manifest.content_hash,
    ) == manifest
    with pytest.raises(ValueError, match="expected identity"):
        reader.read(path, expected_manifest_id=ArtifactId("wrong"))
    with pytest.raises(ValueError, match="expected hash"):
        reader.read(path, expected_content_hash=_hash("0"))

    tampered = manifest.to_canonical_dict()
    tampered["content_hash"] = _hash("0")
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        reader.read(path)


def test_strict_reader_rejects_duplicate_keys_and_noncanonical_time(tmp_path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="strict JSON"):
        CanonicalLifecycleInputManifestReader().read(path)

    payload = _manifest().to_canonical_dict()
    payload["as_of_time"] = "2026-08-04T06:55:00+00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Z suffix"):
        CanonicalLifecycleInputManifestReader().read(path)
