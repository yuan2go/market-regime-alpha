from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_success_v2_runner import (
    PIT_REPLICATION_INPUT_PROJECTION_V2,
    _materialize_available_inputs,
    run_pit_replication_success_v2,
)
from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.xuntou_pit_v4_evidence import (
    PIT_V4_EVIDENCE_SECTIONS,
)
from market_regime_alpha.research.xuntou_pit_v4_preflight import (
    XuntouPITV4Preflight,
    XuntouPITV4PreflightStatus,
)
from market_regime_alpha.research.xuntou_pit_v4_qualification import (
    derive_pit_qualification,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def test_available_test_input_executes_success_path_without_placeholder(tmp_path: Path) -> None:
    final = run_pit_replication_success_v2(
        xuntou_bundle=None,
        output_root=tmp_path,
        success_inputs=build_test_success_inputs(),
    )
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert final.name.startswith("test-only-pit-replication-v2-")
    assert manifest["data_eligibility"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"
    assert manifest["authority"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"


def test_unknown_orderability_never_enters_population(tmp_path: Path) -> None:
    inputs = build_test_success_inputs()
    unknown = {**inputs.orderability_rows[0], "orderability_status": "UNKNOWN"}
    broken = replace(inputs, orderability_rows=(unknown, *inputs.orderability_rows[1:]))
    try:
        run_pit_replication_success_v2(
            xuntou_bundle=None, output_root=tmp_path, success_inputs=broken
        )
    except ValueError as exc:
        assert "RESEARCH_ORDERABLE" in str(exc)
    else:
        raise AssertionError("UNKNOWN orderability entered the Candidate population")


def test_missing_real_bundle_publishes_v4_bound_blocker(tmp_path: Path) -> None:
    final = run_pit_replication_success_v2(
        xuntou_bundle=None, output_root=tmp_path
    )
    blocker = json.loads((final / "blocker.json").read_text(encoding="utf-8"))
    assert blocker["required_bundle_schema"] == "xuntou-pit-validation-bundle-v4"
    assert blocker["tencent_fallback_used"] is False


def test_missing_bundle_is_semantically_verified_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def verify(path: Path):
        calls.append(path)
        return object()

    monkeypatch.setattr(
        "market_regime_alpha.research.pit_replication_success_v2_runner."
        "load_verified_pit_replication_artifact_v2",
        verify,
    )
    final = run_pit_replication_success_v2(xuntou_bundle=None, output_root=tmp_path)
    assert calls == [final]


def test_available_materialization_uses_preflight_derived_provider_identity(
    tmp_path: Path,
) -> None:
    start = date(2024, 1, 1)
    sessions = [start + timedelta(days=index) for index in range(250)]
    provider_id = "sha256:" + "a" * 64
    bundle = tmp_path / "v4.json"
    raw_source_hashes = {"raw.json": "sha256:" + "1" * 64}
    evidence_sections = {
        name: {"content_hash": "sha256:" + f"{index:x}" * 64}
        for index, name in enumerate(PIT_V4_EVIDENCE_SECTIONS, start=1)
    }
    projection = {
        "schema_version": PIT_REPLICATION_INPUT_PROJECTION_V2,
        "provider_artifact_id": provider_id,
        "source_content_hash": "sha256:" + "f" * 64,
        "raw_source_hashes": raw_source_hashes,
        "evidence_section_hashes": {
            name: section["content_hash"]
            for name, section in evidence_sections.items()
        },
        "included_sessions": [value.isoformat() for value in sessions],
        "excluded_sessions": [],
        "development_sessions": [],
        "calendar_identity": "sha256:" + "b" * 64,
        "universe_identity": "sha256:" + "c" * 64,
        "amount_unit_contract": {
            "currency": "CNY",
            "unit": "YUAN",
            "scale": 1.0,
            "aggregation": "SUM_NATIVE_PERIOD_AMOUNT",
            "adjustment_basis": "NONE",
            "provider_field": "amount",
            "evidence_source": "OFFICIAL_XTQUANT_CONTRACT",
        },
        "universe_rows": [],
        "eligibility_rows": [],
        "orderability_rows": [],
        "population_rows": [],
        "feature_rows": [],
        "evaluation_mark_rows": [],
        "path_rows": [],
    }
    projection["projection_content_hash"] = canonical_identity_hash(projection)
    bundle.write_text(
        json.dumps(
            {
                "raw_source_hashes": raw_source_hashes,
                "evidence_sections": evidence_sections,
                "replication_payload": projection,
            }
        ),
        encoding="utf-8",
    )
    qualification = derive_pit_qualification(
        historical_membership_complete=True,
        security_master_complete=True,
        st_history_complete=True,
        suspension_history_complete=True,
        orderability_complete=True,
        liquidity_unit_verified=True,
        bar_finality_verified=True,
        availability_verified=True,
        evaluation_path_complete=True,
    )
    preflight = XuntouPITV4Preflight(
        "xuntou-pit-validation-preflight-v4",
        XuntouPITV4PreflightStatus.AVAILABLE,
        "XUNTOU",
        "xuntou-pit-validation-bundle-v4",
        "sha256:" + "d" * 64,
        "sha256:" + "f" * 64,
        qualification,
        provider_id,
        (),
        False,
        False,
    )
    inputs = _materialize_available_inputs(
        bundle,
        preflight=preflight,
        output_root=tmp_path / "out",
        partition_id="FORMAL_PARTITION",
        partition_start=sessions[0],
        partition_end=sessions[-1],
    )
    assert inputs.provider_artifact_id == provider_id

    root = json.loads(bundle.read_text(encoding="utf-8"))
    root["replication_payload"]["provider_artifact_id"] = "sha256:" + "e" * 64
    bundle.write_text(json.dumps(root), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicts with preflight"):
        _materialize_available_inputs(
            bundle,
            preflight=preflight,
            output_root=tmp_path / "other-out",
            partition_id="OTHER_PARTITION",
            partition_start=sessions[0],
            partition_end=sessions[-1],
        )
