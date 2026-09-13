"""Registered v11→v12 upgrade preserves exact prior owner facts and bytes."""

import psycopg

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres import schema
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import ArtifactApplication
from tests.contracts.test_operational_schema_upgrade import _authorization, _context, _dump


def test_registered_holdout_upgrade_preserves_v11_and_reconciles_committed_retry(target_database_url, tmp_path):
    manager=schema.SchemaManager(target_database_url)
    with psycopg.connect(target_database_url) as c:
        assert c.execute("SELECT to_regnamespace('mra')").fetchone()==(None,)
        for sql in (manager._baseline_sql,manager._post_baseline_sql,manager._daily_sql,
                    manager._daily_closure_sql,manager._static_research_sql,manager._historical_archive_sql,manager._model_subsets_sql):
            c.execute(sql)
        prior_catalog=schema._target_catalog_checksum(c)
        assert prior_catalog=="b432dcdc914f329106ac778198f6ba1fa49be17fbb012acbc3729deaa3b1d2db"
        c.execute(manager._seed_sql,(manager.baseline_checksum,manager.seed_checksum,prior_catalog,
            manager.reference_vocabulary_checksum,manager.baseline_checksum))
        for register in (schema._insert_revision_gap_migration,schema._insert_daily_migration,schema._insert_daily_closure_migration,
                         schema._insert_static_research_migration,schema._insert_historical_archive_migration,schema._insert_model_subsets_migration):
            register(c)
    store=LocalArtifactStore(tmp_path/"original-artifacts")
    pool=TargetPostgresPool(target_database_url)
    try:
        artifact=ArtifactApplication(store,PostgresUnitOfWorkProvider(pool)).publish(
            b"explicit v11 original engineering evidence",media_type="text/plain",context=_context("holdout-prior-artifact"))
        with pool.connection(read_only=True) as c:
            before=schema._historical_projection(c)
            migrations=c.execute("SELECT version,name,checksum FROM mra.schema_migrations ORDER BY version").fetchall()
    finally:
        pool.close()
    backup=tmp_path/"v11.dump"
    digest,size=_dump(target_database_url,backup)
    plan=manager.plan_operational_upgrade(_authorization(manager,backup,digest,size))
    assert plan.upgrade_code=="backtest_exploratory_holdout_v12"
    assert plan.prior_catalog_sha256==prior_catalog
    assert plan.next_catalog_sha256=="8dfcb33cccc804d68119d1ed76f7abdf2c509d656e0a00d20031013b526d52f6"
    result=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    repeated=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    assert not result.replayed and repeated.replayed and result.receipt_id==repeated.receipt_id
    # This test deliberately stops at the historic v12 target. Validate that
    # exact registered route; ordinary latest startup requires the next upgrade.
    definition=manager._resolve_operational_upgrade_definition(prior_baseline_sha256=plan.prior_baseline_sha256,
        prior_catalog_sha256=plan.prior_catalog_sha256,prior_reference_vocabulary_sha256=plan.prior_reference_vocabulary_sha256)
    with manager._connect(read_only=True) as connection:
        assert manager._verify_connection(connection,created=False,expected_upgrade=definition).catalog_checksum==plan.next_catalog_sha256
    with psycopg.connect(target_database_url) as c:
        # Match the canonical pool/upgrade serialization timezone. The same
        # timestamptz bytes must not be compared using a different text offset.
        c.execute("SET LOCAL timezone='UTC'")
        assert schema._historical_projection(c,manifest=before.manifest).sha256==before.sha256
        assert c.execute("SELECT version,name,checksum FROM mra.schema_migrations WHERE version<=7 ORDER BY version").fetchall()==migrations
        assert c.execute("SELECT name,checksum FROM mra.schema_migrations WHERE version=8").fetchone()==(
            "008_backtest_exploratory_holdout","7b3fec55f3ad340dd65b462131d378693c9ab841fb09502e484ccce746958d87")
        assert c.execute("SELECT count(*) FROM mra.backtest_holdout_reservation").fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM mra.backtest_holdout_opening").fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM mra.operational_schema_upgrade_receipt").fetchone()==(1,)
    assert store.verify(artifact.content_sha256,expected_size=artifact.size_bytes).result=="VERIFIED"
