"""Read-only observation selection never weakens canonical reconciliation."""

from contextlib import contextmanager
from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from market_regime_alpha.interfaces import daily_observations as surface
from market_regime_alpha.interfaces.daily_research import encode_daily_plan
from market_regime_alpha.interfaces.daily_health import daily_health
from market_regime_alpha.infrastructure.postgres.queries.daily_predictions import PostgresDailyPredictionReads
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


@pytest.fixture
def observation_app(monkeypatch):
    values = {field.name: uuid4() for field in fields(DailyPredictionPlan)}
    artifact = ArtifactBinding(uuid4(), "a" * 64, 1)
    values.update(
        universe_scope=artifact, code_artifact=artifact, config_artifact=artifact,
        instrument_ids=(uuid4(),), classification_scheme="fixture", classification_code="fixture",
        input_cutoff=datetime(2026, 9, 9, 9, tzinfo=timezone.utc),
        decision_time=datetime(2026, 9, 9, 9, tzinfo=timezone.utc),
        input_content_sha256="b" * 64, code_sha="c" * 40,
    )
    plan = DailyPredictionPlan(**values)
    commitment = uuid4()
    decision = uuid4()
    partition = uuid4()
    row = {
        "state": "COMPLETED", "prediction_id": plan.prediction_id,
        "run_id": plan.runtime_run_id, "plan_sha256": plan.content_sha256,
        "target_session": date(2026, 9, 10), "input_session": date(2026, 9, 9),
        "model_version_id": plan.model_version_id, "target_definition_id": plan.target_definition_id,
        "experimental_model_use_id": plan.experimental_model_use_id, "dataset_id": plan.dataset_id,
        "evaluation_id": uuid4(),
    }
    publication = {"decision_run_id": decision, "predictions": [{"commitment_id": commitment}]}
    acquired = {"observations": [{"commitment_id": commitment}], "labels": [], "outcomes": [], "sources": []}
    replay = {"matched": True, "mismatch_count": 0, "business_writes": 0}
    partition_calls = []
    reads = SimpleNamespace(
        run_plan_content=lambda _: encode_daily_plan(plan),
        decision_run=lambda _: decision,
        forecast_projection=lambda _: publication,
        evaluation_projection=lambda _: {"evaluation": {"research_partition_id": partition}, "metrics": []},
        evaluation_observations=lambda _: acquired,
        require_partition_roster=lambda identity, roster: partition_calls.append((identity, roster)),
        validity_observation_facts=lambda *_: {"commitments": [{"commitment_id": commitment}]},
    )
    app = SimpleNamespace(daily_prediction_reads=reads, daily_research=SimpleNamespace(replay_completed_cycle=lambda _: replay))
    monkeypatch.setattr(surface, "daily_health", lambda _, **kwargs: {"ledger": [row], "observed_at": plan.decision_time})
    return SimpleNamespace(app=app, plan=plan, row=row, replay=replay, acquired=acquired,
        commitment=commitment, decision=decision, partition=partition, partition_calls=partition_calls)


def test_exact_range_and_lineage_filters_preserve_frozen_plan(observation_app):
    fixture = observation_app
    result = surface.daily_observations(fixture.app, target_session_from=date(2026, 9, 9),
        target_session_to=date(2026, 9, 10), experimental_model_use_id=fixture.plan.experimental_model_use_id,
        dataset_id=fixture.plan.dataset_id, decision_run_id=fixture.decision)
    assert result["business_writes"] == 0
    assert len(result["cycles"]) == 1
    assert result["cycles"][0]["frozen_plan_content"].encode() == encode_daily_plan(fixture.plan)
    assert fixture.partition_calls == [(fixture.partition, (fixture.commitment,))]
    assert not surface.daily_observations(fixture.app, target_session_from=date(2026, 9, 11))["cycles"]
    for key in ("experimental_model_use_id", "dataset_id", "decision_run_id"):
        assert not surface.daily_observations(fixture.app, **{key: UUID(int=0)})["cycles"]


def test_unavailable_population_is_retained_and_completed_only_is_explicit(observation_app):
    fixture = observation_app
    fixture.row.update(state="PENDING_MATURITY", sampled=31, reason_code="NATURAL_MATURITY_PENDING")
    result = surface.daily_observations(fixture.app)
    assert not result["cycles"]
    assert result["unavailable"][0]["sampled"] == 31
    assert result["unavailable"][0]["frozen_plan_content"].encode() == encode_daily_plan(fixture.plan)
    assert result["unavailable"][0]["reason_code"] == "NATURAL_MATURITY_PENDING"
    assert not surface.daily_observations(fixture.app, completed_only=True)["unavailable"]


@pytest.mark.parametrize("change", [{"matched": False}, {"mismatch_count": 1}, {"business_writes": 1}, {"matched": None}])
def test_replay_refuses_mismatch_missing_confirmation_or_writes(observation_app, change):
    observation_app.replay.update(change)
    with pytest.raises(ArtifactIntegrityError, match="replay"):
        surface.daily_observations(observation_app.app)


@pytest.mark.parametrize("roster", [[], [{"commitment_id": UUID(int=0)}]])
def test_acquisition_roster_cannot_remove_or_replace_commitments(observation_app, roster):
    observation_app.acquired["observations"] = roster
    with pytest.raises(ArtifactIntegrityError, match="acquisition roster differs"):
        surface.daily_observations(observation_app.app)


def test_duplicate_published_commitment_and_authority_roster_fail_closed(observation_app):
    fixture = observation_app
    fixture.app.daily_prediction_reads.validity_observation_facts = lambda *_: {"commitments": []}
    with pytest.raises(ArtifactIntegrityError, match="Authority roster differs"):
        surface.daily_observations(fixture.app)
    publication = fixture.app.daily_prediction_reads.forecast_projection(fixture.plan)
    publication["predictions"] *= 2
    fixture.acquired["observations"] *= 2
    with pytest.raises(ArtifactIntegrityError, match="acquisition roster differs"):
        surface.daily_observations(fixture.app)


def test_malformed_filters_fail_before_read(observation_app):
    with pytest.raises(ValueError, match="reversed"):
        surface.daily_observations(observation_app.app, target_session_from=date(2026, 9, 11), target_session_to=date(2026, 9, 10))
    with pytest.raises(ValueError, match="exact target session or a range"):
        surface.daily_observations(observation_app.app, target_session_date=date(2026, 9, 10), target_session_to=date(2026, 9, 10))


def test_integrity_blocker_is_not_hidden_by_filters(observation_app):
    observation_app.row["state"] = "INTEGRITY_BLOCKED"
    with pytest.raises(ArtifactIntegrityError, match="unreconciled daily lineage"):
        surface.daily_observations(observation_app.app, model_version_id=UUID(int=0))


class _LedgerReadFixture:
    """Read-only DB boundary with more immutable failed requests than tick budget."""

    def __init__(self, plan, count):
        self.now = plan.decision_time + timedelta(days=2)
        self.runs = []
        self.contents = {}
        self.artifacts = {}
        self.read_only_connections = []
        self.rows = []
        self.sessions = [
            {"session_id": plan.target_session_id, "session_date": date(2026, 9, 10),
             "open_at": plan.decision_time + timedelta(days=1), "close_at": plan.decision_time + timedelta(days=1, hours=6)},
            {"session_id": plan.input_session_id, "session_date": date(2026, 9, 9),
             "open_at": plan.decision_time - timedelta(hours=6), "close_at": plan.decision_time},
        ]
        for index in range(count):
            frozen = replace(plan, prediction_id=UUID(int=index + 1000))
            content = encode_daily_plan(frozen)
            digest = sha256(content).hexdigest()
            self.contents[frozen.runtime_run_id] = content
            self.artifacts[digest] = content
            self.runs.append({"run_id": frozen.runtime_run_id, "schedule_code": "daily-model-" + frozen.prediction_id.hex,
                "requested_at": plan.decision_time + timedelta(seconds=index), "state": "FAILED",
                "terminal_reason_code": "FIXTURE_TERMINAL_FAILURE", "code_sha": frozen.code_sha,
                "config_hash": digest, "content_sha256": digest, "size_bytes": len(content)})

    @contextmanager
    def connection(self, *, read_only):
        self.read_only_connections.append(read_only)
        yield self

    @contextmanager
    def cursor(self, **kwargs):
        yield self

    def execute(self, statement, parameters=None):
        if statement.startswith("SET TRANSACTION"):
            self.rows = []
        elif "clock_timestamp() AS observed_at" in statement:
            self.rows = [{"observed_at": self.now}]
        elif "FROM mra.runtime_run" in statement:
            values = self.runs[:513] if "LIMIT 513" in statement else self.runs
            self.rows = [dict(row) for row in values]
        elif "FROM mra.runtime_step" in statement or "FROM mra.runtime_attempt" in statement:
            self.rows = []
        elif "FROM mra.trading_session" in statement:
            self.rows = self.sessions
        elif "FROM mra.data_capture" in statement:
            self.rows = [{"input_capture": None, "population_capture": None}]
        elif "FROM mra.artifact" in statement:
            self.rows = [{"last_verified_at": None}]
        else:
            raise AssertionError("unexpected query in read-only ledger test")
        return self

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows

    def read_bytes(self, content_sha256, *, expected_size):
        content = self.artifacts[content_sha256]
        assert len(content) == expected_size
        return content


def _historical_app(plan, count, monkeypatch):
    database = _LedgerReadFixture(plan, count)
    reads = PostgresDailyPredictionReads(database, database)
    monkeypatch.setattr(reads, "run_plan_content", lambda identity: database.contents[identity])
    monkeypatch.setattr(surface, "daily_health", daily_health)
    return SimpleNamespace(daily_prediction_reads=reads), database


def test_observation_keeps_more_than_512_requests_while_live_health_remains_bounded(observation_app, monkeypatch):
    app, database = _historical_app(observation_app.plan, 514, monkeypatch)
    with pytest.raises(ValueError, match="explicit row budget"):
        daily_health(app)
    result = surface.daily_observations(app)
    assert len(result["unavailable"]) == 514
    assert len({row["prediction_id"] for row in result["unavailable"]}) == 514
    assert {row["state"] for row in result["unavailable"]} == {"FAILED_TERMINAL"}
    assert result["cycles"] == [] and result["business_writes"] == 0
    assert database.read_only_connections and all(database.read_only_connections)


def test_complete_history_preserves_health_scopes_denominators_and_terminal_failures(observation_app, monkeypatch):
    app, _ = _historical_app(observation_app.plan, 6, monkeypatch)
    options = {"cutover_at": observation_app.plan.decision_time + timedelta(seconds=3), "recent_sessions": 1}
    bounded = daily_health(app, **options)
    complete = daily_health(app, complete_history=True, **options)
    assert complete == bounded
    scopes = complete["scopes"]
    assert scopes["ALL_HISTORY"]["prediction_requests"] == 6
    assert scopes["POST_CURRENT_CUTOVER"]["prediction_requests"] == 3
    assert scopes["LAST_N_TRADING_SESSIONS"]["prediction_requests"] == 6
    for scope, denominator in (("ALL_HISTORY", 6), ("POST_CURRENT_CUTOVER", 3), ("LAST_N_TRADING_SESSIONS", 6)):
        assert scopes[scope]["states"] == {"FAILED_TERMINAL": denominator}
        assert scopes[scope]["publication_rate"] == {"numerator": 0, "denominator": denominator,
            "denominator_kind": "DECLARED_PREDICTION_OR_ABSTENTION_REQUESTS", "state": "ESTIMABLE", "reason_code": None}


def test_complete_empty_history_keeps_missing_boundary_and_denominator_explicit(observation_app, monkeypatch):
    app, _ = _historical_app(observation_app.plan, 0, monkeypatch)
    result = daily_health(app, complete_history=True)
    assert result["scopes"]["POST_CURRENT_CUTOVER"] == {"state": "NOT_ESTIMABLE", "reason_code": "CUTOVER_BOUNDARY_NOT_SUPPLIED"}
    rate = result["scopes"]["ALL_HISTORY"]["publication_rate"]
    assert rate["numerator"] == rate["denominator"] == 0
    assert rate["state"] == "NOT_ESTIMABLE" and rate["reason_code"] == "NO_DECLARED_REQUESTS"
