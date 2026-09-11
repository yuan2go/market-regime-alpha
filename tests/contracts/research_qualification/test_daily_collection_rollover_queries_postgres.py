"""Isolated SQL scope fixture; no canonical research or service mutation."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4, uuid5

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.queries.daily_predictions import PostgresDailyPredictionReads
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from tests.contracts.research_qualification.test_daily_prediction import plan


class _Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=None):
        return self.connection.execute(query.replace("mra.", "pg_temp."), parameters)


@contextmanager
def _reader(database_url, *, phase="input", state="RUNNING", published=False, use_current=False, other_window=False):
    frozen = plan()
    old = uuid4()
    old_identity = uuid5(old, "daily:" + str(frozen.input_session_id) + ":" + str(frozen.target_session_id))
    current_identity = uuid5(frozen.experimental_model_use_id, "daily:" + str(frozen.input_session_id) + ":" + str(frozen.target_session_id))
    with psycopg.connect(database_url) as connection:
        connection.execute("CREATE TEMP TABLE experimental_model_use(experimental_model_use_id uuid, model_version_id uuid)")
        connection.execute("CREATE TEMP TABLE runtime_run(run_id uuid PRIMARY KEY,schedule_id uuid,fire_key text,code_sha text,config_hash text,config_artifact_id uuid,runtime_mode text,state text)")
        connection.execute("CREATE TEMP TABLE runtime_schedule(schedule_id uuid PRIMARY KEY,schedule_code text,runtime_mode text)")
        connection.execute("CREATE TEMP TABLE artifact(artifact_id uuid PRIMARY KEY,content_sha256 text,size_bytes int,integrity_state text)")
        connection.execute("INSERT INTO experimental_model_use VALUES (%s,%s)", (old, frozen.model_version_id))
        identity = current_identity if use_current else uuid4() if other_window else old_identity
        connection.execute("INSERT INTO runtime_run(run_id,state) VALUES (%s,%s)", (uuid5(identity, phase+"-collection:1"), state))
        if published:
            schedule = uuid5(old, "daily-prediction-schedule")
            artifact = uuid4()
            connection.execute("INSERT INTO runtime_schedule VALUES (%s,%s,'SHADOW')", (schedule, "daily-model-"+old.hex))
            connection.execute("INSERT INTO artifact VALUES (%s,%s,1,'AVAILABLE')", (artifact, "a"*64))
            connection.execute("INSERT INTO runtime_run VALUES (%s,%s,%s,%s,%s,%s,'SHADOW','SUCCEEDED')",
                (uuid5(old_identity, "prediction-runtime"), schedule, "daily:"+str(old_identity), "b"*40, "a"*64, artifact))
        connection.commit()
        connection.read_only = True
        @contextmanager
        def read_connection(*, read_only):
            assert read_only
            yield _Connection(connection)
        reader = object.__new__(PostgresDailyPredictionReads)
        reader._pool = SimpleNamespace(connection=read_connection)
        reader._byte_store = SimpleNamespace(read_bytes=lambda *_, **__: b"x")
        yield reader, frozen, old_identity
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)


@pytest.mark.parametrize("phase,state", [("input", "RUNNING"), ("population", "FAILED"), ("input", "WAITING"), ("population", "SUCCEEDED")])
def test_old_collection_without_prediction_requires_original_recovery(target_database_url, phase, state):
    with _reader(target_database_url, phase=phase, state=state) as (reader, frozen, _):
        with pytest.raises(ArtifactIntegrityError, match="DAILY_MODEL_USE_HANDOFF_HAS_FROZEN_COLLECTION"):
            reader.session_work_items(frozen, frozen.input_session_id, frozen.target_session_id)


@pytest.mark.parametrize("options", [{"published": True}, {"use_current": True}, {"other_window": True}])
def test_published_original_or_unrelated_collection_does_not_block(target_database_url, options):
    with _reader(target_database_url, **options) as (reader, frozen, old_identity):
        rows = reader.session_work_items(frozen, frozen.input_session_id, frozen.target_session_id)
        if options.get("published"):
            assert len(rows) == 1 and rows[0].prediction_id == old_identity
        else:
            assert rows == ()
