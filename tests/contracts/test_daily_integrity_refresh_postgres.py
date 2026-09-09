"""Recovery verifies referenced bytes without relabeling market knowledge."""

from dataclasses import replace
from decimal import Decimal
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.queries.daily_feature_inputs import PostgresDailyFeatureInputReadPort
from market_regime_alpha.market.domain import BarTimeframe, MarketBarRevision, NormalizationBatch, PriceBasis
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from tests.contracts.research_qualification import test_research_postgres as research


@pytest.fixture
def stack(target_database_url, tmp_path, request):
    return research.dataset_stack.__wrapped__(target_database_url, tmp_path, request)


def test_daily_capture_reference_survives_integrity_expiry_without_new_capture(stack):
    path = Path(__file__).resolve().parents[2] / 'docs/operations/templates/verify_prospective_artifacts.py'
    spec = importlib.util.spec_from_file_location('daily_refresh_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with stack.pool.connection(read_only=True) as c:
        opening, closing = c.execute('SELECT open_at,close_at FROM mra.trading_session WHERE session_id=%s', (stack.market_session_id,)).fetchone()

    class Provider:
        def capture(self, request):
            return replace(research._BytesProvider().capture(request), content=b'{"distinct":"daily-input"}\n')

    captured = stack.market.capture(research.CaptureRequest(stack.product.provider_product_id, 'integrity-daily', 'fixture://daily-integrity', 'd'*64), Provider(), research._context('daily-integrity-capture', 'CAPTURE_PROVIDER_RESPONSE'))
    def batch(capture):
        return NormalizationBatch(source_capture_id=capture.capture_id, source_provider_product_id=capture.provider_product_id,
            bars=(MarketBarRevision(uuid4(), capture.provider_product_id, capture.capture_id, stack.instrument_id, stack.market_session_id,
                BarTimeframe.DAILY, PriceBasis.RAW_UNADJUSTED, opening, closing, 1, None,
                Money(Decimal('10'), 'CNY'), Money(Decimal('11'), 'CNY'), Money(Decimal('10'), 'CNY'), Money(Decimal('11'), 'CNY'),
                Quantity(Decimal('100'), QuantityUnit.SHARES), None),))
    stack.market.normalize(captured.capture.capture_id, research._Normalizer(batch), research._context('daily-integrity-normalize', 'NORMALIZE_MARKET_PIT'))
    with stack.pool.connection() as c:
        artifact_id, = c.execute('SELECT artifact_id FROM mra.data_capture WHERE capture_id=%s', (captured.capture.capture_id,)).fetchone()
        before = c.execute('SELECT to_jsonb(c) FROM mra.data_capture c WHERE capture_id=%s', (captured.capture.capture_id,)).fetchone()
        cutoff, = c.execute('SELECT clock_timestamp()').fetchone()
        c.execute("UPDATE mra.artifact SET last_verified_at=clock_timestamp()-interval '25 hours' WHERE artifact_id=%s", (artifact_id,))
        calendar_artifact, = c.execute('SELECT c.artifact_id FROM mra.trading_session s JOIN mra.data_capture c ON c.capture_id=s.source_capture_id WHERE s.session_id=%s', (stack.market_session_id,)).fetchone()
        c.execute("UPDATE mra.artifact SET last_verified_at=clock_timestamp()-interval '25 hours' WHERE artifact_id=%s", (calendar_artifact,))
        c.commit()
    reader = PostgresDailyFeatureInputReadPort(stack.pool, stack.store)
    args = dict(provider_product_id=stack.product.provider_product_id, session_id=stack.market_session_id, instrument_ids=(stack.instrument_id.value,), input_cutoff=cutoff)
    with pytest.raises(ArtifactIntegrityError, match='not verified/readable'):
        reader.visible(**args)
    plan = SimpleNamespace(provider_product_id=stack.product.provider_product_id, instrument_ids=(stack.instrument_id.value,), input_session_id=stack.market_session_id, target_session_id=uuid4(), input_cutoff=cutoff)
    with stack.pool.connection(read_only=True) as c:
        references = module._daily_input_artifacts(c, plan)
    assert set(references) == {(artifact_id,), (calendar_artifact,)}
    for identity, in references:
        result = stack.artifacts.verify(identity, verifier_id='operator', context=research._context(f'daily-integrity-observation:{identity}', 'VERIFY_ARTIFACT'))
        assert result.result == 'VERIFIED'
    assert reader.visible(**args)[0].capture_id == captured.capture.capture_id
    with stack.pool.connection(read_only=True) as c:
        assert c.execute('SELECT to_jsonb(c) FROM mra.data_capture c WHERE capture_id=%s', (captured.capture.capture_id,)).fetchone() == before
