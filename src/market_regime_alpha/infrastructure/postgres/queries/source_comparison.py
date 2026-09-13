"""Exact read-only Dataset/Model inputs for bounded source sensitivity reports."""

from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import load_research_dataset_definition
from market_regime_alpha.infrastructure.postgres.queries.model_training_inputs import PostgresModelTrainingInputProvider
from market_regime_alpha.research_qualification.domain import parse_decision_input_dataset_manifest
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.research_qualification.ports.model_execution import FrozenModelVersionPayload, ModelScalarParameter, ModelScalarType
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


from market_regime_alpha.research_qualification.ports.source_comparison import SourceComparisonModel


class PostgresSourceComparisonInputs:
    def __init__(self,pool: TargetPostgresPool,byte_store: ResearchArtifactByteStore) -> None:
        self._pool,self._bytes=pool,byte_store

    def dataset(self,dataset_id: UUID):
        with self._pool.connection(read_only=True) as connection:
            definition,features=load_research_dataset_definition(connection,dataset_id=dataset_id)
            binding=definition.manifest_artifact
            readable=connection.execute("""SELECT mra.market_artifact_is_readable(integrity_state,last_verified_at)
                FROM mra.artifact WHERE artifact_id=%s AND content_sha256=%s AND size_bytes=%s""",
                (binding.artifact_id,str(binding.content_sha256),binding.size_bytes)).fetchone()
        if readable is None or not readable[0]:
            raise ArtifactIntegrityError("source comparison Dataset manifest binding is not readable")
        binding=definition.manifest_artifact
        return parse_decision_input_dataset_manifest(self._bytes.read_bytes(str(binding.content_sha256),expected_size=binding.size_bytes),
            dataset=definition,feature_definitions=features)

    def model(self,model_version_id: UUID) -> SourceComparisonModel:
        with self._pool.connection(read_only=True) as connection:
            row=connection.execute("""SELECT version.model_training_run_id,version.model_id,model.target_definition_id,
                version.content_sha256,version.fitted_model_content_sha256,version.fitted_model_size_bytes,
                version.coefficient_count,mra.artifact_has_verified_integrity(artifact.integrity_state,artifact.last_verified_at),
                (SELECT max(decision.decision_time) FROM mra.model_training_sample sample
                    JOIN mra.decision_run decision USING(decision_run_id) WHERE sample.model_training_run_id=version.model_training_run_id),
                (SELECT max(outcome.observation_cutoff) FROM mra.model_training_sample sample
                    JOIN mra.market_target_outcome_revision outcome USING(market_target_outcome_revision_id)
                    WHERE sample.model_training_run_id=version.model_training_run_id)
                FROM mra.model_version version JOIN mra.model model USING(model_id)
                JOIN mra.artifact artifact ON artifact.artifact_id=version.fitted_model_artifact_id
                WHERE version.model_version_id=%s""",(model_version_id,)).fetchone()
        if row is None or not row[7] or row[8] is None or row[9] is None:
            raise ArtifactIntegrityError("source replay requires an exact readable Model and complete original FIT time bounds")
        registered=PostgresModelTrainingInputProvider(self._pool,self._bytes).load_registered_reproducible(row[0])
        training=registered.training
        if training.model_id!=row[1]:
            raise ArtifactIntegrityError("source replay Model and original Training owner differ")
        parameters=tuple(ModelScalarParameter(p.parameter_code,ModelScalarType(p.value_type.value),p.decimal_value,
            p.integer_value,p.boolean_value,p.text_value) for p in registered.reproducibility.hyperparameters)
        payload=FrozenModelVersionPayload(training.algorithm_code,training.algorithm_version,training.implementation_sha256,
            self._bytes.read_bytes(row[4],expected_size=row[5]),row[4],training.feature_definition_ids,parameters,training.random_seed,row[6])
        return SourceComparisonModel(model_version_id,row[3],row[2],row[8],row[9],payload)

    def bars(self,dataset_ids: tuple[UUID,...],outcome_ids: tuple[UUID,...]) -> tuple[dict,...]:
        if len(dataset_ids)>40 or len(outcome_ids)>1280:
            raise ValueError("source comparison exceeds twenty dates per side or 32-member Outcome budget")
        with self._pool.connection(read_only=True) as connection,connection.cursor(row_factory=dict_row) as cursor:
            rows=cursor.execute("""WITH identities AS (
                SELECT market_bar_revision_id AS bar_revision_id FROM mra.dataset_source WHERE dataset_id=ANY(%s)
                    AND market_bar_revision_id IS NOT NULL
                UNION SELECT bar_revision_id FROM mra.market_target_outcome_source
                    WHERE market_target_outcome_revision_id=ANY(%s) AND bar_revision_id IS NOT NULL)
                SELECT bar.bar_revision_id,bar.instrument_id,bar.session_id,bar.provider_product_id,bar.capture_id,
                    bar.timeframe,bar.price_basis,bar.event_start,bar.event_end,bar.revision,
                    bar.open_value,bar.high_value,bar.low_value,bar.close_value,bar.volume_value,bar.turnover_value,bar.known_at,
                    artifact.artifact_id,artifact.content_sha256,artifact.size_bytes,
                    mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at) AS readable
                FROM identities JOIN mra.market_bar_revision bar USING(bar_revision_id)
                JOIN mra.data_capture capture USING(capture_id) JOIN mra.artifact artifact USING(artifact_id)
                ORDER BY bar.instrument_id,bar.event_start,bar.price_basis,bar.bar_revision_id LIMIT 20001
                """,(list(dataset_ids),list(outcome_ids))).fetchall()
        if len(rows)>20000:
            raise ValueError("source comparison raw dependency roster exceeds twenty thousand revisions")
        for digest,size,readable in {(r['content_sha256'],r['size_bytes'],r['readable']) for r in rows}:
            if not readable:
                raise ArtifactIntegrityError("source comparison raw Capture Artifact is not readable")
            self._bytes.read_bytes(digest,expected_size=size)
        return tuple(dict(r) for r in rows)
