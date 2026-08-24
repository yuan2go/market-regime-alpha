from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.forecasting import PathForecast, PathForecastArtifact
from market_regime_alpha.forecasting.artifact import publish_path_forecast
from market_regime_alpha.portfolio import RiskRouteApplicationService
from market_regime_alpha.research.platform_v2.artifact import (
    ResearchLayerArtifact,
    ResearchLayerStatus,
    publish_research_layer_artifact,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.signals.artifact import publish_signal_run
from market_regime_alpha.signals.engine import SIGNAL_RUN_SCHEMA, SignalRunArtifact
from scripts.build_thesis_health import main
import scripts.build_thesis_health as build_thesis_health

from tests.forecasting.test_path_forecast import _config as _path_config
from tests.position.thesis_health_fixtures import ASSESSED_AT, make_h5_fixture
from tests.position.thesis_health_fixtures import (
    H5Fixture,
    _opportunity,
    _thesis,
    health_rule_set,
)
from tests.postgres_path_repositories import (
    postgres_cli_arguments,
    postgres_connection,
)
from tests.research.platform_v2.conftest import research_input_bundle
from tests.signals.test_engine import _config as _signal_config


def _write_document(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_request(
    path: Path,
    *,
    idempotency_key: str,
    fixture: H5Fixture | None = None,
    package_paths: tuple[Path, Path, Path] | None = None,
) -> None:
    fixture = fixture or make_h5_fixture()
    _write_document(path.parent / "thesis.json", fixture.thesis.to_canonical_dict())
    _write_document(path.parent / "opportunity.json", fixture.opportunity.to_canonical_dict())
    _write_document(path.parent / "price.json", fixture.price.to_canonical_dict())
    _write_document(
        path.parent / "configuration.json",
        fixture.configuration.to_canonical_dict(),
    )
    _write_document(path.parent / "rules.json", fixture.rule_set.to_canonical_dict())
    payload = {
        "thesis_path": "thesis.json",
        "opportunity_path": "opportunity.json",
        "research_package_path": str(package_paths[0] if package_paths is not None else "research-package"),
        "signal_package_path": str(package_paths[1] if package_paths is not None else "signal-package"),
        "path_forecast_package_path": str(package_paths[2] if package_paths is not None else "path-package"),
        "price_snapshot_path": "price.json",
        "configuration_path": "configuration.json",
        "rule_set_path": "rules.json",
        "manual_evidence_paths": [],
        "prior_observation_id": None,
        "prior_observation_hash": None,
        "assessed_at": fixture.price.decision_time.isoformat(),
        "actor": "reviewer-a",
        "reason": "strict verified package CLI test",
        "idempotency_key": idempotency_key,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _publish_verified_packages(
    root: Path,
) -> tuple[H5Fixture, tuple[Path, Path, Path]]:
    fixture = make_h5_fixture()
    inputs = research_input_bundle.__wrapped__()
    research_config = default_research_pipeline_config()
    component_ids = tuple(
        item.envelope.artifact_id
        for item in (
            fixture.market,
            fixture.theme,
            fixture.capital,
            fixture.candidate,
        )
    )
    component_hashes = tuple(
        item.envelope.content_hash
        for item in (
            fixture.market,
            fixture.theme,
            fixture.capital,
            fixture.candidate,
        )
    )
    research_semantic = ResearchLayerArtifact.semantic_payload_for(
        market_regime=fixture.market,
        theme_rotation=fixture.theme,
        capital_evolution=fixture.capital,
        candidate_set=fixture.candidate,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        input_bundle_id=inputs.input_bundle_id,
        configuration_ids=(
            research_config.market_regime.configuration_id,
            research_config.theme_rotation.configuration_id,
            research_config.capital_evolution.configuration_id,
            research_config.candidate_discovery.configuration_id,
            research_config.configuration_id,
        ),
        model_ids=(
            research_config.market_regime.model_id,
            research_config.theme_rotation.model_id,
            research_config.capital_evolution.model_id,
            research_config.candidate_discovery.model_id,
        ),
        research_status=ResearchLayerStatus.RESEARCH_READY,
        reason_codes=("H5_CLI_VERIFIED_PACKAGE_TEST",),
        limitations=("SYNTHETIC_TEST_EVIDENCE",),
    )
    research_envelope = ArtifactEnvelope.create(
        artifact_type="RESEARCH_LAYER_ARTIFACT",
        artifact_payload=research_semantic,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision="h5-cli-package-test",
        configuration_id=research_config.configuration_id,
        configuration_hash=research_config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=(inputs.input_bundle_id, *component_ids),
        input_content_hashes=(inputs.content_hash, *component_hashes),
        model_id=None,
        model_version=None,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=ResearchLayerStatus.RESEARCH_READY.value,
        reason_codes=("H5_CLI_VERIFIED_PACKAGE_TEST",),
        limitations=("SYNTHETIC_TEST_EVIDENCE",),
    )
    research = ResearchLayerArtifact(
        envelope=research_envelope,
        inputs=inputs,
        configuration=research_config,
        market_regime=fixture.market,
        theme_rotation=fixture.theme,
        capital_evolution=fixture.capital,
        candidate_set=fixture.candidate,
        research_status=ResearchLayerStatus.RESEARCH_READY,
        reason_codes=("H5_CLI_VERIFIED_PACKAGE_TEST",),
        limitations=("SYNTHETIC_TEST_EVIDENCE",),
    )
    research_path = publish_research_layer_artifact(root=root / "research", artifact=research)

    signal_config = _signal_config()
    signal_payload = {
        "schema_version": SIGNAL_RUN_SCHEMA,
        "candidate_set": {
            "artifact_id": str(fixture.candidate.envelope.artifact_id),
            "content_hash": fixture.candidate.envelope.content_hash,
        },
        "configuration": signal_config.to_canonical_dict(),
        "observations": [],
        "snapshots": [fixture.signal.to_canonical_dict()],
    }
    signal_envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_RUN",
        artifact_payload=signal_payload,
        decision_date=fixture.signal.envelope.decision_date,
        decision_time=fixture.signal.envelope.decision_time,
        created_at=fixture.signal.envelope.created_at,
        code_revision="h5-cli-package-test",
        configuration_id=signal_config.configuration_id,
        configuration_hash=signal_config.configuration_hash,
        source_manifest_id=fixture.signal.envelope.source_manifest_id,
        source_manifest_hash=fixture.signal.envelope.source_manifest_hash,
        input_artifact_ids=(fixture.candidate.envelope.artifact_id,),
        input_content_hashes=(fixture.candidate.envelope.content_hash,),
        model_id=signal_config.model_id,
        model_version=signal_config.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("H5_CLI_VERIFIED_PACKAGE_TEST",),
        limitations=("SYNTHETIC_TEST_EVIDENCE",),
    )
    signal_run = SignalRunArtifact(
        envelope=signal_envelope,
        candidate_set=fixture.candidate,
        configuration=signal_config,
        observations=(),
        snapshots=(fixture.signal,),
    )
    signal_path = publish_signal_run(root=root / "signal", artifact=signal_run)

    path_config = _path_config()
    path_payload = fixture.path.to_canonical_dict()
    path_payload.pop("envelope")
    old_path_envelope = fixture.path.envelope
    path_envelope = ArtifactEnvelope.create(
        artifact_type=old_path_envelope.artifact_type,
        artifact_payload=path_payload,
        decision_date=old_path_envelope.decision_date,
        decision_time=old_path_envelope.decision_time,
        created_at=old_path_envelope.created_at,
        code_revision="h5-cli-package-test",
        configuration_id=path_config.configuration_id,
        configuration_hash=path_config.configuration_hash,
        source_manifest_id=old_path_envelope.source_manifest_id,
        source_manifest_hash=old_path_envelope.source_manifest_hash,
        input_artifact_ids=(fixture.signal.envelope.artifact_id,),
        input_content_hashes=(fixture.signal.envelope.content_hash,),
        model_id=path_config.model_id,
        model_version=path_config.model_version,
        data_eligibility=old_path_envelope.data_eligibility,
        evidence_authority=old_path_envelope.evidence_authority,
        status=old_path_envelope.status,
        reason_codes=old_path_envelope.reason_codes,
        limitations=old_path_envelope.limitations,
    )
    path_forecast = PathForecast.from_canonical_dict({"envelope": path_envelope.to_canonical_dict(), **path_payload})
    path_artifact = PathForecastArtifact(
        forecast=path_forecast,
        signal_snapshot=fixture.signal,
        configuration=path_config,
        samples=(),
    )
    path_path = publish_path_forecast(root=root / "path", artifact=path_artifact)
    opportunity = _opportunity(fixture.candidate, fixture.signal, path_forecast)
    thesis = _thesis(opportunity)
    return (
        replace(
            fixture,
            path=path_forecast,
            opportunity=opportunity,
            thesis=thesis,
            rule_set=health_rule_set(thesis),
        ),
        (research_path, signal_path, path_path),
    )


def _install_verified_package_readers(monkeypatch) -> None:
    fixture = make_h5_fixture()
    research = SimpleNamespace(
        market_regime=fixture.market,
        theme_rotation=fixture.theme,
        capital_evolution=fixture.capital,
        candidate_set=fixture.candidate,
    )
    signal = SimpleNamespace(
        candidate_set=fixture.candidate,
        snapshots=(fixture.signal,),
    )
    path = SimpleNamespace(
        signal_snapshot=fixture.signal,
        forecast=fixture.path,
    )
    monkeypatch.setattr(
        build_thesis_health,
        "load_verified_research_layer_artifact",
        lambda _path: SimpleNamespace(artifact=research),
    )
    monkeypatch.setattr(
        build_thesis_health,
        "load_verified_signal_run",
        lambda _path: SimpleNamespace(artifact=signal),
    )
    monkeypatch.setattr(
        build_thesis_health,
        "load_verified_path_forecast",
        lambda _path: SimpleNamespace(artifact=path),
    )


def _invoke(database: Path, request: Path, capsys) -> dict[str, object]:
    assert main([*postgres_cli_arguments(database), "--request", str(request)]) == 0
    return json.loads(capsys.readouterr().out)


def test_cli_persists_and_replays_v2_observation_without_trade_authority(tmp_path, capsys, monkeypatch) -> None:
    database = tmp_path / "health.postgres-scope"
    request = tmp_path / "health.json"
    _write_request(request, idempotency_key="cli-health-replay")
    _install_verified_package_readers(monkeypatch)
    monkeypatch.setattr(
        RiskRouteApplicationService,
        "assess_reducing",
        lambda *_args, **_kwargs: pytest.fail("H5 CLI must not create an H4 decision"),
    )

    first = _invoke(database, request, capsys)
    replay = _invoke(database, request, capsys)

    assert replay["observation_id"] == first["observation_id"]
    assert first["schema_version"] == "thesis-health-observation-v2"
    assert first["observed_health_state"] == "HEALTHY"
    assert first["effective_health_state"] == "HEALTHY"
    assert first["mode"] == "OBSERVATION_ONLY"
    assert first["execution_boundary"] == "NO_TRADE_ACTION_CREATED"
    assert first["trading_authority"] == "TRADING_AUTHORITY_NOT_GRANTED"
    assert first["component_states"]["signal"] == "SUPPORTED"
    assert first["source_artifacts"]["candidate_set"]["artifact_id"]

    with postgres_connection(database) as connection:
        health_count = connection.execute("SELECT count(*) FROM thesis_health_observations").fetchone()[0]
        downstream_counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "risk_reducing_decisions",
                "manual_trade_records",
                "manual_fills",
            )
        )
    assert health_count == 1
    assert downstream_counts == (0, 0, 0)


def test_cli_reads_real_verified_research_signal_and_path_packages(
    tmp_path,
    capsys,
) -> None:
    fixture, package_paths = _publish_verified_packages(tmp_path / "packages")
    request = tmp_path / "verified-packages.json"
    _write_request(
        request,
        idempotency_key="cli-real-package-readers",
        fixture=fixture,
        package_paths=package_paths,
    )

    result = _invoke(tmp_path / "verified-packages.postgres-scope", request, capsys)
    assert result["observed_health_state"] == "HEALTHY"
    assert result["source_artifacts"]["candidate_set"]["artifact_id"] == str(fixture.candidate.envelope.artifact_id)


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "signal_support",
        "theme_support",
        "capital_support",
        "triggered_condition_ids",
        "health_state",
    ),
)
def test_cli_rejects_v1_support_or_caller_authored_health(tmp_path, forbidden_field: str) -> None:
    request = tmp_path / f"forbidden-{forbidden_field}.json"
    _write_request(request, idempotency_key="strict-v2-input")
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload[forbidden_field] = True
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="request fields mismatch"):
        main(
            [
                *postgres_cli_arguments(tmp_path / "forbidden.postgres-scope"),
                "--request",
                str(request),
            ]
        )


def test_cli_rejects_v1_health_observation_as_operational_input(tmp_path) -> None:
    request = tmp_path / "v1.json"
    request.write_text(
        json.dumps(
            {
                "signal_support": True,
                "theme_support": True,
                "capital_support": True,
                "idempotency_key": "no-v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        main(
            [
                *postgres_cli_arguments(tmp_path / "v1.postgres-scope"),
                "--request",
                str(request),
            ]
        )


@pytest.mark.parametrize(
    ("assessed_at", "expected_state"),
    (
        (None, "DATA_INSUFFICIENT"),
        ("TIME_INVALIDATION", "INVALIDATED"),
    ),
)
def test_cli_reports_derived_insufficient_and_invalidated_states(
    tmp_path,
    capsys,
    monkeypatch,
    assessed_at: str | None,
    expected_state: str,
) -> None:
    request = tmp_path / f"{expected_state.lower()}.json"
    _write_request(request, idempotency_key=f"cli-{expected_state.lower()}")
    fixture = make_h5_fixture()
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["assessed_at"] = (
        fixture.thesis.time_invalidation.isoformat()
        if assessed_at == "TIME_INVALIDATION"
        else (fixture.price.decision_time.value.isoformat())
    )
    if expected_state == "DATA_INSUFFICIENT":
        from datetime import timedelta

        payload["assessed_at"] = (ASSESSED_AT + timedelta(minutes=2)).isoformat()
    request.write_text(json.dumps(payload), encoding="utf-8")
    _install_verified_package_readers(monkeypatch)

    result = _invoke(tmp_path / f"{expected_state}.postgres-scope", request, capsys)
    assert result["observed_health_state"] == expected_state
    if expected_state == "DATA_INSUFFICIENT":
        assert result["effective_health_state"] == "NOT_ESTABLISHED"
        assert result["missing_reason_codes"]
    else:
        assert result["triggered_condition_ids"] == ["time-stop"]
