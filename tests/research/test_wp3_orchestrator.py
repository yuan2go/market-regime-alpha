from __future__ import annotations

import json
from pathlib import Path

from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data import DataEligibility
from market_regime_alpha.research.provider_routing import (
    CandidateDataSource,
    CandidateRunSourceMode,
    ProviderAvailabilityStatus,
    ProviderCapabilityReport,
)
from market_regime_alpha.research.wp3_orchestrator import (
    NormalizedXuntouWP3Backend,
    WP3BackendResult,
    WP3RunRequest,
    XuntouWP3Preflight,
    execute_wp3_candidate_run,
)


def _report(
    source: CandidateDataSource,
    status: ProviderAvailabilityStatus,
) -> ProviderCapabilityReport:
    maximum = (
        DataEligibility.REHEARSAL
        if source is CandidateDataSource.XUNTOU
        else DataEligibility.EXPLORATORY
    )
    return ProviderCapabilityReport(
        source=source,
        availability_status=status,
        maximum_data_eligibility=maximum,
        supported_evidence=("R5_B0_B1_INPUT",),
        unsupported_evidence=("FORMAL_PIT",),
        limitations=(f"{source.value}_TEST_LIMITATION",),
        input_identity=f"test:{source.value}:{status.value}",
    )


def _result(
    source: CandidateDataSource,
    *,
    empty: bool = False,
) -> WP3BackendResult:
    eligibility = (
        DataEligibility.REHEARSAL
        if source is CandidateDataSource.XUNTOU
        else DataEligibility.EXPLORATORY
    )
    return WP3BackendResult(
        source=source,
        data_eligibility=eligibility,
        dataset_id=DatasetId(f"dataset-{source.value.lower()}"),
        provider_references=[{"provider": source.value}],
        source_artifacts=[{"content_hash": f"sha256:{source.value.lower()}"}],
        quality={"status": "ACCEPTED"},
        candidate_panel_summary={
            "outcome": (
                "NO_CANDIDATES_AFTER_ELIGIBILITY" if empty else "EVALUATED"
            )
        },
        b0_b1_evaluation=(
            {
                "status": "NOT_PRODUCED",
                "reason": "NO_CANDIDATES_AFTER_ELIGIBILITY",
                "targets": [],
            }
            if empty
            else {"status": "PRODUCED", "targets": []}
        ),
        limitations=(f"{source.value}_TEST_LIMITATION",),
        manifest_details={"decision_time_convention": "14:55 Asia/Shanghai"},
    )


class FakeXuntouBackend:
    def __init__(
        self,
        status: ProviderAvailabilityStatus,
        *,
        empty: bool = False,
    ) -> None:
        self.status = status
        self.empty = empty
        self.execute_count = 0

    def preflight(self, bundle: Path | None) -> XuntouWP3Preflight:
        prepared = object() if self.status is ProviderAvailabilityStatus.AVAILABLE else None
        return XuntouWP3Preflight(
            report=_report(CandidateDataSource.XUNTOU, self.status),
            prepared=prepared,
        )

    def execute(
        self,
        request: WP3RunRequest,
        preflight: XuntouWP3Preflight,
    ) -> WP3BackendResult:
        self.execute_count += 1
        return _result(CandidateDataSource.XUNTOU, empty=self.empty)


class FakeTencentBackend:
    def __init__(self, status: ProviderAvailabilityStatus) -> None:
        self.status = status
        self.execute_count = 0

    def capability_report(self) -> ProviderCapabilityReport:
        return _report(CandidateDataSource.TENCENT_COMPOSITE, self.status)

    def execute(self, request: WP3RunRequest) -> WP3BackendResult:
        self.execute_count += 1
        return _result(CandidateDataSource.TENCENT_COMPOSITE)


def _request(
    tmp_path: Path,
    *,
    mode: CandidateRunSourceMode = CandidateRunSourceMode.AUTO,
    minimum: DataEligibility = DataEligibility.EXPLORATORY,
    run_id: str = "run-001",
) -> WP3RunRequest:
    return WP3RunRequest(
        run_id=run_id,
        source_mode=mode,
        minimum_eligibility=minimum,
        output_root=tmp_path,
        xuntou_bundle=None,
        decision_count=2,
        code_revision="abc123",
        config_hash="sha256:config",
        minimum_liquidity_value=None,
    )


def test_valid_xuntou_is_selected_without_executing_tencent(tmp_path) -> None:
    xuntou = FakeXuntouBackend(ProviderAvailabilityStatus.AVAILABLE)
    tencent = FakeTencentBackend(ProviderAvailabilityStatus.AVAILABLE)

    output = execute_wp3_candidate_run(
        _request(tmp_path),
        xuntou_backend=xuntou,
        tencent_backend=tencent,
    )

    selection = json.loads((output / "provider_selection.json").read_text())
    assert selection["selected_source"] == "XUNTOU"
    assert xuntou.execute_count == 1
    assert tencent.execute_count == 0


def test_absent_xuntou_selects_tencent_for_exploratory_request(tmp_path) -> None:
    xuntou = FakeXuntouBackend(ProviderAvailabilityStatus.UNAVAILABLE)
    tencent = FakeTencentBackend(ProviderAvailabilityStatus.AVAILABLE)

    output = execute_wp3_candidate_run(
        _request(tmp_path),
        xuntou_backend=xuntou,
        tencent_backend=tencent,
    )

    manifest = json.loads((output / "manifest.json").read_text())
    limitations = json.loads((output / "limitations.json").read_text())
    assert manifest["data_eligibility"] == "EXPLORATORY"
    assert manifest["selected_source"] == "TENCENT_COMPOSITE"
    assert "TENCENT_COMPOSITE_TEST_LIMITATION" in limitations["items"]
    assert xuntou.execute_count == 0
    assert tencent.execute_count == 1


def test_invalid_xuntou_fails_closed_without_executing_tencent(tmp_path) -> None:
    xuntou = FakeXuntouBackend(ProviderAvailabilityStatus.INVALID)
    tencent = FakeTencentBackend(ProviderAvailabilityStatus.AVAILABLE)

    output = execute_wp3_candidate_run(
        _request(tmp_path),
        xuntou_backend=xuntou,
        tencent_backend=tencent,
    )

    failure = json.loads((output / "failure.json").read_text())
    assert failure["code"] == "WP3_XUNTOU_PREFLIGHT_FAILED"
    assert not (output / "b0_b1_evaluation.json").exists()
    assert xuntou.execute_count == 0
    assert tencent.execute_count == 0


def test_rehearsal_request_rejects_tencent(tmp_path) -> None:
    output = execute_wp3_candidate_run(
        _request(tmp_path, minimum=DataEligibility.REHEARSAL),
        xuntou_backend=FakeXuntouBackend(ProviderAvailabilityStatus.UNAVAILABLE),
        tencent_backend=FakeTencentBackend(ProviderAvailabilityStatus.AVAILABLE),
    )

    failure = json.loads((output / "failure.json").read_text())
    assert failure["route_error_code"] == "PROVIDER_ROUTE_AUTHORITY_UNSUPPORTED"


def test_xuntou_empty_population_is_success_not_fallback(tmp_path) -> None:
    xuntou = FakeXuntouBackend(
        ProviderAvailabilityStatus.AVAILABLE,
        empty=True,
    )
    tencent = FakeTencentBackend(ProviderAvailabilityStatus.AVAILABLE)

    output = execute_wp3_candidate_run(
        _request(tmp_path),
        xuntou_backend=xuntou,
        tencent_backend=tencent,
    )

    evaluation = json.loads((output / "b0_b1_evaluation.json").read_text())
    assert evaluation["reason"] == "NO_CANDIDATES_AFTER_ELIGIBILITY"
    assert tencent.execute_count == 0


def test_default_xuntou_preflight_classifies_corrupt_bundle_as_invalid(
    tmp_path,
) -> None:
    bundle = tmp_path / "bad.json"
    bundle.write_text("not-json", encoding="utf-8")

    preflight = NormalizedXuntouWP3Backend().preflight(bundle)

    assert preflight.report.availability_status is ProviderAvailabilityStatus.INVALID
    assert preflight.prepared is None
