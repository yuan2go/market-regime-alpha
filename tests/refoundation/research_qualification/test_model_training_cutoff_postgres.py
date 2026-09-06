from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries import model_training_inputs as inputs
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion, ModelExecutionEnvironment, ModelScalarParameter, ModelScalarType,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest, PreparedModelTrainingInputs, ReproducibleModelTrainingRunRequest,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.shared.hashing import sha256_bytes


@pytest.mark.parametrize('status,purpose', [('COMPLETED', 'FIT'), ('OPEN', 'FIT'), ('COMPLETED', 'VALIDATION'), ('ABSENT', 'FIT')])
def test_reproducible_training_freezes_the_completed_fit_database_cutoff(target_database_url, tmp_path, monkeypatch, status, purpose):
    completed_at = datetime(2026, 1, 5, 9, tzinfo=UTC)
    evaluation_id = uuid4()
    with psycopg.connect(target_database_url) as connection:
        # Isolate the time-selection contract from the separately tested parent,
        # Feature and sample acquisitions; the clock and terminal fact are real SQL.
        connection.execute('CREATE SCHEMA mra')
        connection.execute('CREATE TABLE mra.evaluation_run (evaluation_run_id uuid PRIMARY KEY, status text, partition_purpose text, completed_at timestamptz)')
        if status != 'ABSENT':
            connection.execute('INSERT INTO mra.evaluation_run VALUES (%s,%s,%s,%s)', (evaluation_id, status, purpose, completed_at))
    artifact = ArtifactBinding(uuid4(), 'a' * 64, 1)
    training = OpenModelTrainingRunRequest(
        uuid4(), uuid4(), evaluation_id, uuid4(), uuid4(), uuid4(), uuid4(),
        'deterministic_ridge', '1.0', 'b' * 64, Decimal('0.25'), 23,
        artifact, artifact, 'c' * 64,
    )
    request = ReproducibleModelTrainingRunRequest(
        training,
        ModelExecutionEnvironment('cpython', '3.12.2', 'uv', '0.11.7', 'd' * 64,
                                  (ModelDependencyVersion(1, 'project', '0.1.0', 'e' * 64),)),
        (ModelScalarParameter(1, 'ridge_alpha', ModelScalarType.DECIMAL, decimal_value=Decimal('0.25')),),
    )
    content = b'{}'
    prepared = PreparedModelTrainingInputs(training, (), (), content, sha256_bytes(content))
    monkeypatch.setattr(inputs, '_require_reproducible_training_scope', lambda *_: None)
    monkeypatch.setattr(inputs, '_training_source_rows', lambda *_: ())
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=1)
    try:
        provider = inputs.PostgresModelTrainingInputProvider(pool, LocalArtifactStore(tmp_path))
        monkeypatch.setattr(provider, 'prepare', lambda _: prepared)
        if status != 'COMPLETED' or purpose != 'FIT':
            with pytest.raises(RuntimeStateConflictError, match='completed FIT Evaluation'):
                provider.prepare_reproducible(request)
        else:
            first = provider.prepare_reproducible(request)
            second = provider.prepare_reproducible(request)
            assert first == second
            assert first.reproducibility.training_knowledge_cutoff == completed_at
    finally:
        pool.close()
