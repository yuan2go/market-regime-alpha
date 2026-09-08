"""Exact immutable baseline plus one forward-only correction; disposable DBs only."""
from pathlib import Path

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres import schema
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager, SchemaChecksumMismatchError
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import ArtifactApplication
from market_regime_alpha.shared.hashing import sha256_bytes
from tests.refoundation.test_operational_schema_upgrade import _dump, _authorization, _context


_BASELINE = 'f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27'
_V5_CATALOG = 'd14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1'
_V6_CATALOG = '233c60c2b8b6efca4682f92fff8acbe85895a967cef0e11f7838f572e6ed69db'
_PATCH = 'bd5978ae2ccfd56a9d117c41e13e0a8f7c76fbdd4d83d4aa1b32757dbe753063'


def _bootstrap_v5(database_url):
    manager = SchemaManager(database_url)
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT to_regnamespace('mra')").fetchone() == (None,)
        connection.execute(manager._baseline_sql)
        checksum = schema._target_catalog_checksum(connection)
        assert checksum == _V5_CATALOG
        connection.execute(manager._seed_sql, (
            manager.baseline_checksum, manager.seed_checksum, checksum,
            'd08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b', manager.baseline_checksum,
        ))
        connection.commit()
    return manager


def test_fresh_schema_records_exact_immutable_baseline_and_correction(target_database_url):
    manager = SchemaManager(target_database_url)
    result = manager.bootstrap()
    assert result.baseline_checksum == _BASELINE
    assert result.catalog_checksum == schema._DAILY_CATALOG_SHA256
    with psycopg.connect(target_database_url) as connection:
        assert connection.execute('SELECT version,name,checksum FROM mra.schema_migrations ORDER BY version').fetchall() == [
            (1, '001_baseline', _BASELINE), (2, '002_prospective_revision_gap', _PATCH),
            (3, '003_daily_model_research', schema._DAILY_BUNDLE_SHA256),
        ]
    assert manager.bootstrap().created is False
    assert manager.verify().catalog_checksum == result.catalog_checksum


def test_prior_baseline_and_all_five_published_upgrade_bundles_remain_exact(target_database_url):
    manager = SchemaManager(target_database_url)
    assert sha256_bytes(manager._baseline_sql.encode()) == _BASELINE
    definitions = schema._wp18q_operational_upgrade_definitions(
        baseline_sql=manager._baseline_sql,
        next_baseline_sha256=manager.baseline_checksum,
        next_reference_vocabulary_sha256=manager.reference_vocabulary_checksum,
    )
    assert [definition.additive_bundle_sha256 for definition in definitions] == [
        'cbd98d6502e675d0b11d0f1b542861d615bb2f007087fdd49203a0bfc2af8241',
        '2dfe756539fccf1d25b73d190248ad6e819b3c67192400db2f444338c3cad91e',
        '1f33e51b6ac9e02acd38fa1f9cfef54170d3068c236870f5904d0a5201a9b742',
        'cbfb125bb8ac0df211fe7835329026afcb76bed9b24d092bf89a440cdd2c0773',
        '45849ef8e6571eb640876190c47b87272de4676f7c6fe2c60581d3bac1177b2a',
        _PATCH,
        schema._DAILY_BUNDLE_SHA256,
    ]
    for definition in definitions:
        assert manager._resolve_operational_upgrade_definition(
            prior_baseline_sha256=definition.prior_baseline_sha256,
            prior_catalog_sha256=definition.prior_catalog_sha256,
            prior_reference_vocabulary_sha256=definition.prior_reference_vocabulary_sha256,
        ) == definition


def test_v5_controlled_upgrade_preserves_bytes_business_hashes_and_unknown_commit_replay(target_database_url, tmp_path: Path):
    manager = _bootstrap_v5(target_database_url)
    with pytest.raises(SchemaChecksumMismatchError, match='REFERENCE_VOCABULARY_CHECKSUM_MISMATCH'):
        manager.verify()
    store = LocalArtifactStore(tmp_path/'old-artifacts')
    pool = TargetPostgresPool(target_database_url)
    application = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    artifact = application.publish(b'old v5 evidence bytes must remain exact', media_type='text/plain', context=_context('before-v6'))
    with pool.connection(read_only=True) as connection:
        before = schema._historical_projection(connection)
        migration = connection.execute('SELECT * FROM mra.schema_migrations').fetchall()
    pool.close()
    backup = tmp_path/'v5-original.dump'
    backup_sha, backup_size = _dump(target_database_url, backup)
    plan = manager.plan_operational_upgrade(_authorization(manager, backup, backup_sha, backup_size))
    assert plan.upgrade_code == 'wp18q_prospective_revision_gap_v6'
    assert plan.prior_catalog_sha256 == _V5_CATALOG
    assert plan.next_catalog_sha256 == _V6_CATALOG
    assert plan.prior_baseline_sha256 == plan.next_baseline_sha256 == _BASELINE
    result = manager.apply_operational_upgrade(plan, challenge=plan.challenge, operator_id=plan.operator_id)
    # Simulates loss of the successful return: reconcile the exact immutable
    # plan/receipt; no repeat DDL or second business/upgrade receipt is allowed.
    repeated = manager.apply_operational_upgrade(plan, challenge=plan.challenge, operator_id=plan.operator_id)
    assert not result.replayed and repeated.replayed
    assert result.receipt_id == repeated.receipt_id
    with psycopg.connect(target_database_url) as connection:
        connection.execute("SET LOCAL timezone='UTC'")
        assert schema._historical_projection(connection, manifest=before.manifest).sha256 == before.sha256
        assert connection.execute('SELECT * FROM mra.schema_migrations WHERE version=1').fetchall() == migration
        assert connection.execute('SELECT count(*) FROM mra.operational_schema_upgrade_receipt').fetchone() == (1,)
    assert store.verify(artifact.content_sha256, expected_size=artifact.size_bytes).result == 'VERIFIED'
    # v6 is preserved and verifiable by its upgrade receipt; it is not the
    # current daily-input v7 schema. Never inherit current-code admission.
    with pytest.raises(SchemaChecksumMismatchError, match='REFERENCE_VOCABULARY_CHECKSUM_MISMATCH'):
        manager.verify()


def test_v6_to_daily_v7_exact_additive_upgrade_preserves_immutable_evidence(target_database_url, tmp_path: Path):
    manager = _bootstrap_v5(target_database_url)
    store = LocalArtifactStore(tmp_path/'v6-artifacts')
    pool = TargetPostgresPool(target_database_url)
    artifact = ArtifactApplication(store,PostgresUnitOfWorkProvider(pool)).publish(
        b'v6 original bytes',media_type='text/plain',context=_context('v6-baseline'))
    pool.close()
    first_backup=tmp_path/'v5.dump'
    first_sha,first_size=_dump(target_database_url,first_backup)
    first=manager.plan_operational_upgrade(_authorization(manager,first_backup,first_sha,first_size))
    assert manager.apply_operational_upgrade(first,challenge=first.challenge,operator_id=first.operator_id).replayed is False
    with psycopg.connect(target_database_url) as connection:
        before=schema._historical_projection(connection)
        prior=connection.execute('SELECT version,name,checksum FROM mra.schema_migrations ORDER BY version').fetchall()
    backup=tmp_path/'v6.dump'
    backup_sha,backup_size=_dump(target_database_url,backup)
    plan=manager.plan_operational_upgrade(_authorization(manager,backup,backup_sha,backup_size))
    assert plan.upgrade_code=='daily_model_research_v7'
    assert plan.prior_catalog_sha256==_V6_CATALOG
    assert plan.next_catalog_sha256==schema._DAILY_CATALOG_SHA256
    result=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    repeated=manager.apply_operational_upgrade(plan,challenge=plan.challenge,operator_id=plan.operator_id)
    assert result.receipt_id==repeated.receipt_id and not result.replayed and repeated.replayed
    with psycopg.connect(target_database_url) as connection:
        assert schema._historical_projection(connection,manifest=before.manifest).sha256==before.sha256
        assert connection.execute('SELECT version,name,checksum FROM mra.schema_migrations WHERE version<=2 ORDER BY version').fetchall()==prior
    assert manager.verify().catalog_checksum==schema._DAILY_CATALOG_SHA256
    assert store.verify(artifact.content_sha256,expected_size=artifact.size_bytes).result=='VERIFIED'
