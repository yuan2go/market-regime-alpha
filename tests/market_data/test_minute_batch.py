from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Lock
import time

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.market_data.minute_batch import (
    CandidateMinuteAcquisitionCommand,
    CandidateMinuteBatchAcquirer,
    MinuteCoverageState,
    MinuteSymbolState,
    load_minute_acquisition_coverage,
)
from market_regime_alpha.market_data.minute_source import (
    MinuteSourceRequest,
    MinuteSourceResponse,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState


DECISION = datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc)
START = DECISION - timedelta(minutes=1)
HARD_CUTOFF = DECISION + timedelta(minutes=1)
HASH = "sha256:" + "1" * 64


def _candidate_set(count: int) -> CandidateSet:
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, count + 1))
    records = tuple(
        CandidateRecord(
            symbol=symbol,
            primary_theme_id=None,
            supporting_theme_ids=(),
            market_regime_status=MarketState.RISK_ON,
            theme_rotation_state=RotationState.STRENGTHENING,
            capital_evolution_state=CapitalEvolutionState.IGNITION,
            market_regime_score=0.5,
            theme_score=0.4,
            capital_evolution_score=0.3,
            candidate_discovery_score=0.8 - rank / 100,
            rank=rank,
            selection_status=CandidateSelectionStatus.SELECTED,
            reason_codes=("FIXTURE_SELECTED",),
            source_feature_ids=(),
            input_artifact_ids=(),
        )
        for rank, symbol in enumerate(symbols, 1)
    )
    payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": 1,
        "reason_codes": ["IMMUTABLE_RECORDED_FIXTURE"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=DECISION.date(),
        decision_time=DecisionTime(DECISION),
        created_at=DECISION,
        code_revision="fixture-revision",
        configuration_id=ArtifactId("candidate-config-fixture"),
        configuration_hash=canonical_hash({"fixture": "candidate"}),
        source_manifest_id=ArtifactId("source-manifest-fixture"),
        source_manifest_hash=HASH,
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("candidate-model-fixture"),
        model_version="fixture-v1",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("IMMUTABLE_RECORDED_FIXTURE",),
        limitations=("TEST_ONLY",),
    )
    return CandidateSet(
        envelope=envelope,
        records=records,
        minimum_candidate_population=1,
        reason_codes=("IMMUTABLE_RECORDED_FIXTURE",),
    )


def _command(count: int, *, max_attempts: int = 2, concurrency: int = 3):
    return CandidateMinuteAcquisitionCommand.create(
        candidate_set=_candidate_set(count),
        decision_time=DECISION,
        provider_profile_id="tencent-public-minute-archive-v1",
        concurrency_limit=concurrency,
        per_request_timeout_seconds=2.0,
        max_attempts=max_attempts,
        retry_backoff_seconds=0.0,
        hard_cutoff=HARD_CUTOFF,
    )


def _payload(symbol: str, *, rows: list[str] | None = None) -> bytes:
    code = f"{symbol[-2:].lower()}{symbol[:6]}"
    return json.dumps(
        {
            "code": 0,
            "data": {
                code: {
                    "data": {
                        "date": "20260805",
                        "data": rows
                        or [
                            "0930 10.00 1 1000",
                            "0931 10.01 2 2001",
                        ],
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()


class _ResponseClient:
    def __init__(
        self,
        *,
        symbol: str,
        status: int = 200,
        content_type: str = "application/json",
        raw_payload: bytes | None = None,
        received_at: datetime = START,
    ) -> None:
        self.symbol = symbol
        self.status = status
        self.content_type = content_type
        self.raw_payload = raw_payload
        self.received_at = received_at

    def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
        assert request.symbols == (self.symbol,)
        return MinuteSourceResponse(
            request=request,
            request_started_at=START,
            response_received_at=self.received_at,
            http_status=self.status,
            content_type=self.content_type,
            raw_payload=self.raw_payload or _payload(self.symbol),
            provider_timestamp="20260805",
            limitations=("PUBLIC_TENCENT_EXPLORATORY_ONLY",),
        )


@pytest.mark.parametrize("count", [1, 5, 10])
def test_batch_archives_all_candidates_with_bounded_concurrency_and_roundtrip(
    tmp_path: Path, count: int
) -> None:
    active = 0
    peak = 0
    lock = Lock()

    class TrackingClient(_ResponseClient):
        def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.005)
                return super().fetch(request)
            finally:
                with lock:
                    active -= 1

    command = _command(count, concurrency=3)
    artifact = CandidateMinuteBatchAcquirer(
        client_factory=lambda symbol, _attempt, _timeout: TrackingClient(symbol=symbol),
        clock=lambda: START,
    ).run(command=command, output_root=tmp_path)

    assert artifact.coverage_state is MinuteCoverageState.COMPLETE
    assert artifact.candidate_count == count
    assert artifact.succeeded_count == count
    assert artifact.failed_count == artifact.late_count == 0
    assert peak <= 3
    path = tmp_path / "coverage" / str(artifact.artifact_id)
    assert load_minute_acquisition_coverage(path) == artifact
    assert len(tuple((tmp_path / "sources").iterdir())) == count


def test_partial_failure_retries_429_and_preserves_each_attempt(tmp_path: Path) -> None:
    command = _command(5, max_attempts=2)

    def factory(symbol: str, attempt: int, _timeout: float):
        if symbol == "000001.SZ" and attempt == 1:
            return _ResponseClient(symbol=symbol, status=429)
        if symbol == "000002.SZ":
            return _ResponseClient(symbol=symbol, status=503)
        if symbol == "000003.SZ":
            return _ResponseClient(symbol=symbol, raw_payload=b"<html>unavailable</html>")
        return _ResponseClient(symbol=symbol)

    artifact = CandidateMinuteBatchAcquirer(
        client_factory=factory,
        clock=lambda: START,
    ).run(command=command, output_root=tmp_path)

    assert artifact.coverage_state is MinuteCoverageState.PARTIAL
    assert artifact.succeeded_count == 3
    assert artifact.failed_count == 2
    by_symbol = {item.symbol: item for item in artifact.symbol_coverage}
    assert len(by_symbol["000001.SZ"].attempt_references) == 2
    assert by_symbol["000001.SZ"].state is MinuteSymbolState.SUCCEEDED
    assert len(by_symbol["000002.SZ"].attempt_references) == 2
    assert by_symbol["000003.SZ"].state is MinuteSymbolState.FAILED
    assert len(by_symbol["000003.SZ"].attempt_references) == 1


@pytest.mark.parametrize("error", [TimeoutError("timeout"), ConnectionError("dns")])
def test_timeout_and_dns_failure_are_finite_and_all_failed(
    tmp_path: Path, error: Exception
) -> None:
    class FailingClient:
        def fetch(self, _request: MinuteSourceRequest) -> MinuteSourceResponse:
            raise error

    artifact = CandidateMinuteBatchAcquirer(
        client_factory=lambda _symbol, _attempt, _timeout: FailingClient(),
        clock=lambda: START,
    ).run(command=_command(1, max_attempts=2), output_root=tmp_path)

    assert artifact.coverage_state is MinuteCoverageState.FAILED
    assert artifact.failed_count == 1
    assert len(artifact.symbol_coverage[0].attempt_references) == 2


def test_late_response_is_archived_but_never_accepted(tmp_path: Path) -> None:
    artifact = CandidateMinuteBatchAcquirer(
        client_factory=lambda symbol, _attempt, _timeout: _ResponseClient(
            symbol=symbol,
            received_at=DECISION + timedelta(seconds=1),
        ),
        clock=lambda: START,
    ).run(command=_command(1), output_root=tmp_path)

    symbol = artifact.symbol_coverage[0]
    assert artifact.coverage_state is MinuteCoverageState.DEADLINE_MISSED
    assert artifact.late_count == artifact.failed_count == 1
    assert symbol.state is MinuteSymbolState.LATE
    assert symbol.accepted_source_artifact_id is None
    assert len(tuple((tmp_path / "sources").iterdir())) == 1


def test_no_request_or_retry_starts_at_or_after_decision_time(tmp_path: Path) -> None:
    calls = 0

    def factory(_symbol: str, _attempt: int, _timeout: float):
        nonlocal calls
        calls += 1
        raise AssertionError("client must not be constructed after DecisionTime")

    artifact = CandidateMinuteBatchAcquirer(
        client_factory=factory,
        clock=lambda: DECISION,
    ).run(command=_command(5), output_root=tmp_path)

    assert calls == 0
    assert artifact.attempted_count == 0
    assert artifact.coverage_state is MinuteCoverageState.DEADLINE_MISSED
    assert all(
        item.state is MinuteSymbolState.DEADLINE_NOT_STARTED
        for item in artifact.symbol_coverage
    )


def test_wrong_symbol_and_malformed_json_do_not_retry(tmp_path: Path) -> None:
    command = _command(1, max_attempts=3)
    symbol = command.candidate_symbols[0]
    wrong = _payload("000999.SZ")
    artifact = CandidateMinuteBatchAcquirer(
        client_factory=lambda _symbol, _attempt, _timeout: _ResponseClient(
            symbol=symbol, raw_payload=wrong
        ),
        clock=lambda: START,
    ).run(command=command, output_root=tmp_path)

    assert artifact.coverage_state is MinuteCoverageState.FAILED
    assert len(artifact.symbol_coverage[0].attempt_references) == 1


def test_valid_json_with_content_type_mismatch_remains_explicit(tmp_path: Path) -> None:
    command = _command(1)
    symbol = command.candidate_symbols[0]
    artifact = CandidateMinuteBatchAcquirer(
        client_factory=lambda _symbol, _attempt, _timeout: _ResponseClient(
            symbol=symbol, content_type="text/html"
        ),
        clock=lambda: START,
    ).run(command=command, output_root=tmp_path)

    assert artifact.coverage_state is MinuteCoverageState.COMPLETE
    source_package = next((tmp_path / "sources").iterdir())
    source_payload = json.loads((source_package / "artifact.json").read_text())
    assert "PROVIDER_CONTENT_TYPE_MISMATCH_VALID_JSON" in source_payload[
        "retrieval_limitations"
    ]


def test_command_rejects_non_positive_limits_and_bad_cutoff() -> None:
    candidate_set = _candidate_set(1)
    with pytest.raises(ValueError, match="concurrency_limit"):
        CandidateMinuteAcquisitionCommand.create(
            candidate_set=candidate_set,
            decision_time=DECISION,
            provider_profile_id="profile",
            concurrency_limit=0,
            per_request_timeout_seconds=1,
            max_attempts=1,
            retry_backoff_seconds=0,
            hard_cutoff=HARD_CUTOFF,
        )
    with pytest.raises(ValueError, match="hard cutoff"):
        CandidateMinuteAcquisitionCommand.create(
            candidate_set=candidate_set,
            decision_time=DECISION,
            provider_profile_id="profile",
            concurrency_limit=1,
            per_request_timeout_seconds=1,
            max_attempts=1,
            retry_backoff_seconds=0,
            hard_cutoff=DECISION,
        )
