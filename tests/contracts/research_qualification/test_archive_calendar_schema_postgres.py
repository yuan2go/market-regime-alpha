"""Exact v12→v13 forward correction; original facts and migrations stay byte-exact."""

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres import schema
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import ArtifactApplication
from tests.contracts.test_operational_schema_upgrade import _authorization, _context, _dump


def test_registered_archive_calendar_upgrade_preserves_prior_facts_and_lost_ack(target_database_url,tmp_path):
    manager=schema.SchemaManager(target_database_url)
    with psycopg.connect(target_database_url) as connection:
        assert connection.execute("SELECT to_regnamespace('mra')").fetchone()==(None,)
        for sql in (manager._baseline_sql,manager._post_baseline_sql,manager._daily_sql,
                    manager._daily_closure_sql,manager._static_research_sql,manager._historical_archive_sql,
                    manager._model_subsets_sql,manager._holdout_sql):
            connection.execute(sql)
        prior_catalog=schema._target_catalog_checksum(connection)
        assert prior_catalog=="8dfcb33cccc804d68119d1ed76f7abdf2c509d656e0a00d20031013b526d52f6"
        connection.execute(manager._seed_sql,(manager.baseline_checksum,manager.seed_checksum,prior_catalog,
            manager.reference_vocabulary_checksum,manager.baseline_checksum))
        for register in (schema._insert_revision_gap_migration,schema._insert_daily_migration,schema._insert_daily_closure_migration,
                         schema._insert_static_research_migration,schema._insert_historical_archive_migration,
                         schema._insert_model_subsets_migration,schema._insert_holdout_migration):
            register(connection)
    # Latest startup cannot silently upgrade the frozen prior catalog.
    with pytest.raises(schema.CatalogDriftError):
        manager.verify()
    with pytest.raises(schema.OperationalUpgradeIntegrityError,match="NO_APPROVED_OPERATIONAL_UPGRADE_ROUTE"):
        manager._resolve_operational_upgrade_definition(prior_baseline_sha256='0'*64,
            prior_catalog_sha256=prior_catalog,prior_reference_vocabulary_sha256=manager.reference_vocabulary_checksum)
    store=LocalArtifactStore(tmp_path/'prior-artifacts')
    pool=TargetPostgresPool(target_database_url)
    try:
        artifact=ArtifactApplication(store,PostgresUnitOfWorkProvider(pool)).publish(
            b'unchanged v12 engineering evidence',media_type='text/plain',context=_context('calendar-prior'))
        with pool.connection(read_only=True) as connection:
            before=schema._historical_projection(connection)
            migrations=connection.execute('SELECT version,name,checksum FROM mra.schema_migrations ORDER BY version').fetchall()
    finally:
        pool.close()
    backup=tmp_path/'v12.dump'
    digest,size=_dump(target_database_url,backup)
    plan=manager.plan_operational_upgrade(_authorization(manager,backup,digest,size))
    assert plan.upgrade_code=='exploratory_archive_calendar_v13'
    assert plan.prior_catalog_sha256==prior_catalog
    result=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    repeated=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    assert not result.replayed and repeated.replayed and result.receipt_id==repeated.receipt_id
    assert manager.verify().catalog_checksum==plan.next_catalog_sha256
    with psycopg.connect(target_database_url) as connection:
        connection.execute("SET LOCAL timezone='UTC'")
        assert schema._historical_projection(connection,manifest=before.manifest).sha256==before.sha256
        assert connection.execute('SELECT version,name,checksum FROM mra.schema_migrations WHERE version<=8 ORDER BY version').fetchall()==migrations
        assert connection.execute('SELECT count(*) FROM mra.operational_schema_upgrade_receipt').fetchone()==(1,)
    assert store.verify(artifact.content_sha256,expected_size=artifact.size_bytes).result=='VERIFIED'
