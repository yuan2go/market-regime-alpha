"""Synthetic protocol evidence only, with independent boundary/decimal checks."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.providers.recorded_professional_normalizer import RecordedProfessionalDailyNormalizer
from market_regime_alpha.infrastructure.recorded_professional_provider import RecordedProfessionalMarketProvider, replay_professional_capture
from market_regime_alpha.market.domain import GapKind, SecurityStatus
from market_regime_alpha.market.ports.professional_normalization import ProfessionalInstrumentReference
from market_regime_alpha.market.ports.provider import CaptureRequest
from market_regime_alpha.market.ports.revision_lineage import MarketBarRevisionHead
from market_regime_alpha.market.ports.session_roster import ArchiveTradingSession
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from tests.contracts.market.test_baostock_archive_normalizer import _capture
from tests.contracts.market.test_professional_daily_recording import contract, payload


def mapping(c):
    return {"schema":"mra-professional-normalization-evidence-v1","evidence_kind":"LOCAL_PROTOCOL_SUBSTITUTE",
        **{name:getattr(c,name) for name in ("sdk_version","dividend_type","price_unit","volume_unit","amount_unit","timestamp_meaning","timezone")},
        "price_basis":"RAW_UNADJUSTED","suspension_mapping":{"0":"ACTIVE","1":"SUSPENDED","-1":"ACTIVE_RESUMED_FLAG_RETAINED_IN_CAPTURE"},
        "source_reference":"Explicit synthetic mapping, not a vendor protocol or paid-source validation"}


def recorded(*, changes=None, row_changes=None, include_evidence=True):
    c=replace(contract(),**(changes or {}))
    evidence=json.dumps(mapping(c),sort_keys=True).encode()
    c=replace(c,semantics_evidence_sha256=sha256(evidence).hexdigest())
    raw=payload()
    raw["rows"][0].update(row_changes or {})
    content=json.dumps(raw).encode()
    provider=RecordedProfessionalMarketProvider(c,content,expected_sha256=sha256(content).hexdigest(),
        normalization_evidence=evidence if include_evidence else None)
    capture=_capture()
    request=CaptureRequest(capture.provider_product_id,capture.capture_key,provider.resource,"a"*64)
    capture=replace(capture,request_hash=canonical_json_sha256(request))
    return capture,provider.capture(request).content


class References:
    def __init__(self):
        self.instrument=InstrumentId(uuid4())
        def session(day):
            return ArchiveTradingSession(TradingSessionId(uuid4()),"XSHG",date(2025,1,day),
                *(datetime(2025,1,day,hour,minute,tzinfo=UTC) for hour,minute in ((1,30),(3,30),(5,0),(7,0))))
        self.sessions=(session(2),session(3))
    def references(self, contract, capture):
        return (ProfessionalInstrumentReference("600000.SH",self.instrument,self.sessions),)


class Lineage:
    def market_bar_head(self, **kwargs): return None
    def instrument_fact_head(self, **kwargs): return None


def test_normalization_budget_includes_missing_calendar_slots():
    capture,content=recorded(changes={"maximum_rows":1})
    with pytest.raises(ValueError,match="Calendar population exceeds the frozen normalization row budget"):
        RecordedProfessionalDailyNormalizer(References(),Lineage()).normalize(capture,content)


def test_evidenced_normalization_keeps_exact_values_and_missing_calendar_cell():
    capture,content=recorded(changes={"volume_unit":"LOTS_OF_100_SHARES"})
    refs=References()
    normalizer=RecordedProfessionalDailyNormalizer(refs,Lineage())
    batch=normalizer.normalize(capture,content)
    assert batch==normalizer.normalize(capture,content)
    assert len(batch.bars)==1 and batch.bars[0].volume.amount==Decimal(10000)
    assert batch.bars[0].close.amount==Decimal('10.5') and batch.bars[0].turnover.amount==Decimal(1050)
    assert (batch.bars[0].event_start,batch.bars[0].event_end)==(refs.sessions[0].open_at,refs.sessions[0].close_at)
    assert batch.security_status_facts[0].status is SecurityStatus.ACTIVE
    assert len(batch.gaps)==1 and batch.gaps[0].gap_kind is GapKind.MISSING
    assert batch.gaps[0].session_id==refs.sessions[1].session_id
    checked=replay_professional_capture(content)[2]
    assert checked['normalization_evidence']['evidence_kind']=='LOCAL_PROTOCOL_SUBSTITUTE'
    assert checked['professional_provider_validation']=='NOT_RUN'


def test_suspended_zero_prices_remain_invalid_ohlc_with_observed_suspension():
    capture,content=recorded(row_changes={"suspendFlag":1,"open":"0","high":"0","low":"0","close":"0","volume":"0","amount":"0"})
    batch=RecordedProfessionalDailyNormalizer(References(),Lineage()).normalize(capture,content)
    assert not batch.bars and batch.security_status_facts[0].status is SecurityStatus.SUSPENDED
    assert [gap.gap_kind for gap in batch.gaps]==[GapKind.INVALID_OHLC,GapKind.MISSING]


def test_observed_valid_suspension_bar_is_retained_without_active_status_or_volume_rounding():
    capture,content=recorded(row_changes={"suspendFlag":1})
    batch=RecordedProfessionalDailyNormalizer(References(),Lineage()).normalize(capture,content)
    assert len(batch.bars)==1 and batch.security_status_facts[0].status is SecurityStatus.SUSPENDED
    capture,content=recorded(changes={"volume_unit":"LOTS_OF_100_SHARES"},row_changes={"volume":"1.00000000000000000000000000000000000000001"})
    with pytest.raises(ValueError,match=r'quantity.amount exceeds numeric\(38, 10\) scale'):
        RecordedProfessionalDailyNormalizer(References(),Lineage()).normalize(capture,content)


def test_missing_reference_calendar_cannot_be_inferred_from_bar_date():
    capture,content=recorded()
    refs=References()
    refs.sessions=refs.sessions[1:]
    with pytest.raises(ValueError,match='evidenced Market Calendar'):
        RecordedProfessionalDailyNormalizer(refs,Lineage()).normalize(capture,content)


@pytest.mark.parametrize('changes',[{'dividend_type':'back'},{'dividend_type':'front_ratio'}])
def test_adjustment_mapping_is_not_inferred_from_vendor_enum(changes):
    with pytest.raises(ValueError,match='adjusted-price mapping'):
        recorded(changes=changes)


def test_exact_timestamp_reference_and_original_request_are_required():
    capture,content=recorded(changes={'timestamp_meaning':'BAR_CLOSE'})
    normalizer=RecordedProfessionalDailyNormalizer(References(),Lineage())
    with pytest.raises(ValueError,match='Calendar boundary'):
        normalizer.normalize(capture,content)
    capture,content=recorded(include_evidence=False)
    with pytest.raises(ValueError,match='embedded evidenced mapping'):
        normalizer.normalize(capture,content)
    capture,content=recorded()
    with pytest.raises(ValueError,match='original Capture request'):
        normalizer.normalize(replace(capture,capture_key='different'),content)


def test_ambiguous_replacement_order_and_tampered_embedded_mapping_are_rejected():
    capture,content=recorded()
    class Previous(Lineage):
        def market_bar_head(self,**kwargs): return MarketBarRevisionHead(uuid4(),1)
    with pytest.raises(ValueError,match='replacement revision ordering'):
        RecordedProfessionalDailyNormalizer(References(),Previous()).normalize(capture,content)
    raw=json.loads(content)
    raw['normalization_evidence_base64']='e30='
    with pytest.raises(ValueError,match='evidence bytes/hash differ'):
        replay_professional_capture(json.dumps(raw).encode())
