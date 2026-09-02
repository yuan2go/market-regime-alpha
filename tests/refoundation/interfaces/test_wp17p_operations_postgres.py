from __future__ import annotations

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.interfaces.wp17p_authorities import (
    build_wp17p_authority_catalog,
)
from market_regime_alpha.interfaces.wp17p_operations import Wp17pResearchOperations
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.shared.hashing import canonical_json_sha256

from tests.refoundation.research_qualification import (
    test_exploratory_backtest_postgres as _backtest,
)


def test_canonical_composition_registers_and_replays_wp17p_catalog(
    target_database_url,
    tmp_path,
    request,
) -> None:
    stack = _backtest.backtest_stack.__wrapped__(
        target_database_url,
        tmp_path,
        request,
    )
    archive, seal, source_sessions = _backtest._archive_sessions(stack)
    with bootstrap_application(
        TargetSettings(
            database_url=target_database_url,
            artifact_root=(tmp_path / "wp17p-composed-artifacts").resolve(),
            pool_min_size=0,
            pool_max_size=4,
        )
    ) as application:
        code = application.artifacts.publish(
            b"wp17p canonical composition\n",
            media_type="text/plain",
            context=_backtest._context("composed-code"),
        )
        config = application.artifacts.publish(
            b'{"pilot":"WP17P_ENGINEERING_EXPLORATORY_32"}\n',
            media_type="application/json",
            context=_backtest._context("composed-config"),
        )
        sessions = application.archive_trading_sessions.sessions(
            exchange="XSHG",
            start_date=source_sessions[0].session_date,
            end_date=source_sessions[-1].session_date,
        )
        catalog = build_wp17p_authority_catalog(
            provider_product_id=stack.product.provider_product_id,
            market_archive_id=archive.market_archive_id,
            market_archive_seal_id=seal.market_archive_seal_id,
            sessions=sessions,
            code_artifact=ArtifactBinding(
                code.artifact_id,
                code.content_sha256,
                code.size_bytes,
            ),
            config_artifact=ArtifactBinding(
                config.artifact_id,
                config.content_sha256,
                config.size_bytes,
            ),
            provenance_sha256=canonical_json_sha256(
                {"authority": "WP17P_COMPOSITION_TEST"}
            ),
        )
        operations = Wp17pResearchOperations(application)

        operations.register_catalog(catalog)
        operations.register_catalog(catalog)

        verification = application.exploratory_backtest_verifier.verify(
            catalog.backtest.exploratory_backtest_run_id
        )
        assert verification.matched is True
        assert verification.mismatch_count == 0
