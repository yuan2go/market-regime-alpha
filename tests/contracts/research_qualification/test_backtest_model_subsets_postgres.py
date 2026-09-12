"""Explicit subset v2 runs through original owners; v1 keeps exact roster semantics."""

from dataclasses import replace
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_database, bootstrap_application
from market_regime_alpha.interfaces.backtest import encode_backtest_specification, decode_backtest_specification
from market_regime_alpha.research_qualification.domain.backtest import AuthorityBinding
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from tests.contracts.research_qualification.archive_campaign_fixture import _context
from tests.contracts.research_qualification.daily_campaign_fixture import daily_baseline


@pytest.mark.parametrize("version",[1,2])
def test_subset_requires_frozen_v2_and_completes_original_training_and_replay(target_database_url,tmp_path,version):
    settings=TargetSettings(target_database_url,tmp_path/"artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        spec,catalog=daily_baseline(app)
        original=catalog["feature"]
        extra=replace(original,feature_definition_id=uuid4(),feature_code="unused_daily_control")
        app.research_definitions.register_feature_definition(extra,_context("extra-feature"))
        # Put the unused Feature first: v2 preserves the Model's own order and
        # matches exact identities/hashes, not root ordinal or a positional prefix.
        spec=replace(spec,feature_definitions=(AuthorityBinding(extra.feature_definition_id,str(extra.content_sha256)),*spec.feature_definitions),
            specification_schema_version=version)
        assert decode_backtest_specification(encode_backtest_specification(spec))==spec
        app.backtests.predeclare(spec,_context("subset-predeclare"))
        reloaded=app.backtest_specifications.load_specification(spec.exploratory_backtest_run_id)
        assert reloaded==spec
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT mra.model_backtest_feature_rosters_match(%s,%s)",(catalog["model"].model_id,spec.exploratory_backtest_run_id)).fetchone()==(version==2,)
        frozen=app.backtest_specifications.load(spec.exploratory_backtest_run_id)
        if version==1:
            with pytest.raises(RuntimeStateConflictError,match="exact completed FIT Evaluation/backtest parents"):
                app.backtest_execution.run(frozen)
        else:
            result=app.backtest_execution.run(frozen)
            assert result.execution_state.value=="COMPLETED"
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT count(*) FROM mra.model_training_run WHERE model_id=%s",(catalog["model"].model_id,)).fetchone()==(1 if version==2 else 0,)
        if version==2:
            assert app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched
            with app._pool.connection(read_only=True) as c:
                before=c.execute("SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)").fetchone()
            comparison=app.historical_comparison.project(spec.exploratory_backtest_run_id)
            assert comparison==app.historical_comparison.project(spec.exploratory_backtest_run_id)
            assert len(comparison["statistics"]["common_population"])==32
            assert len(comparison["input_roster"])==64
            assert {p["model_version_id"] for p in comparison["input_roster"] if p["arm_id"]==spec.arms[0].exploratory_backtest_arm_id}=={None}
            with app._pool.connection(read_only=True) as c:
                assert c.execute("SELECT (SELECT count(*) FROM mra.command_receipt),(SELECT count(*) FROM mra.audit_event)").fetchone()==before
        # A separately registered Feature outside the frozen Backtest roster
        # cannot qualify just because the Model uses fewer columns.
        foreign=replace(extra,feature_definition_id=uuid4(),feature_code="foreign_daily_control")
        app.research_definitions.register_feature_definition(foreign,_context("foreign-feature"))
        foreign_model=replace(catalog["model"],model_id=uuid4(),model_code="foreign_subset_model",
            feature_definitions=((foreign.feature_definition_id,str(foreign.content_sha256)),))
        app.research_models.register_model(foreign_model,_context("foreign-model"))
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT mra.model_backtest_feature_rosters_match(%s,%s)",(foreign_model.model_id,spec.exploratory_backtest_run_id)).fetchone()==(False,)
        if version == 2:
            from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore, ArtifactStoreError
            with app._pool.connection(read_only=True) as c:
                digest = c.execute(
                    "SELECT manifest_content_sha256 FROM mra.dataset JOIN mra.exploratory_backtest_dataset USING(dataset_id) "
                    "WHERE exploratory_backtest_run_id=%s ORDER BY dataset_id LIMIT 1",
                    (spec.exploratory_backtest_run_id,),
                ).fetchone()[0]
            path = LocalArtifactStore(settings.artifact_root).object_path(digest)
            original_bytes = path.read_bytes()
            try:
                path.write_bytes(b"corrupt")
                with pytest.raises(ArtifactStoreError, match="SIZE_MISMATCH"):
                    app.historical_comparison.project(spec.exploratory_backtest_run_id)
            finally:
                path.write_bytes(original_bytes)
