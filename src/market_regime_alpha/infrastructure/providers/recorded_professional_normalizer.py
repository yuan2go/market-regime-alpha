"""Narrow evidenced RAW daily bridge into the existing Market owner.

Reference facts come from Market, never from weekdays or the bar's existence.
Original vendor revision tokens, resume flags and mapping bytes stay in Capture.
Unknown replacement ordering fails closed instead of replacing earlier facts.
"""

from datetime import date
from decimal import Decimal
import json
from uuid import NAMESPACE_URL, uuid5

from market_regime_alpha.infrastructure.recorded_professional_provider import replay_professional_capture
from market_regime_alpha.market.domain import (BarTimeframe, EvidenceScope, GapFactKind, GapKind, GapReasonCode,
    InstrumentFactKind, MarketBarRevision, NormalizationBatch, PriceBasis, ProviderCapture,
    SecurityStatus, SecurityStatusFactRevision, SourceGap)
from market_regime_alpha.market.ports.professional_normalization import ProfessionalNormalizationReferencePort
from market_regime_alpha.market.ports.provider import NormalizerContract
from market_regime_alpha.market.ports.revision_lineage import MarketRevisionLineageReadPort
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit


class RecordedProfessionalDailyNormalizer:
    contract = NormalizerContract("market.recorded_professional_daily", "1",
        "5523365795143c92abf0da0c2b665328b225d0b6503a17e516445417f36a2d07")

    def __init__(self, references: ProfessionalNormalizationReferencePort, lineage: MarketRevisionLineageReadPort) -> None:
        self._references, self._lineage = references, lineage

    def normalize(self, capture: ProviderCapture, content: bytes) -> NormalizationBatch:
        contract, recording, checked = replay_professional_capture(content)
        request = checked.get("capture_request", {})
        if (checked.get("capture_request_sha256") != str(capture.request_hash)
                or request.get("provider_product_id") != str(capture.provider_product_id)
                or request.get("capture_key") != capture.capture_key):
            raise ValueError("professional normalization requires the exact original Capture request")
        if "normalization_evidence" not in checked:
            raise ValueError("professional normalization requires embedded evidenced mapping, not an unverified hash")
        references = self._references.references(contract, capture)
        if tuple(r.stock_code for r in references) != contract.instruments:
            raise ValueError("professional Market reference population differs")
        if sum(len(r.sessions) for r in references) > contract.maximum_rows:
            raise ValueError("professional Calendar population exceeds the frozen normalization row budget")
        rows = {(r["stock_code"], date.fromisoformat(r["session_date"])): r for r in json.loads(recording)["rows"]}
        expected = {(r.stock_code,s.session_date) for r in references for s in r.sessions}
        if set(rows) - expected or any(not r.sessions for r in references):
            raise ValueError("professional recording date is outside the evidenced Market Calendar")
        bars, statuses, gaps = [], [], []
        for reference in references:
            for session in reference.sessions:
                key = (reference.stock_code,session.session_date)
                row = rows.get(key)
                identity = f"mra:professional-daily:{capture.capture_id}:{key[0]}:{key[1]}"
                def gap(kind, reason):
                    return SourceGap(uuid5(NAMESPACE_URL,identity+":gap"),capture.provider_product_id,capture.capture_id,
                        reference.instrument_id,session.session_id,kind,reason,GapFactKind.MARKET_BAR,None,
                        BarTimeframe.DAILY,PriceBasis.RAW_UNADJUSTED,session.open_at,session.close_at,
                        "RECORDED_SOURCE_GAP_NO_FILL_NO_FINALITY")
                if row is None:
                    gaps.append(gap(GapKind.MISSING,GapReasonCode.EXPECTED_OBSERVATION_MISSING))
                    continue
                if contract.timestamp_meaning != "SESSION_DATE_MARKER":
                    instant = session.open_at if contract.timestamp_meaning == "BAR_OPEN" else session.close_at
                    if row["time"] != int(instant.timestamp()*1000):
                        raise ValueError("professional bar timestamp differs from the exact Market Calendar boundary")
                bar_id = uuid5(NAMESPACE_URL,identity+":bar")
                status_id = uuid5(NAMESPACE_URL,identity+":status")
                head = self._lineage.market_bar_head(provider_product_id=capture.provider_product_id,
                    instrument_id=reference.instrument_id,session_id=session.session_id,timeframe=BarTimeframe.DAILY,
                    price_basis=PriceBasis.RAW_UNADJUSTED,event_start=session.open_at,event_end=session.close_at)
                status_head = self._lineage.instrument_fact_head(provider_product_id=capture.provider_product_id,
                    instrument_id=reference.instrument_id,session_id=session.session_id,fact_kind=InstrumentFactKind.SECURITY_STATUS,
                    evidence_scope=EvidenceScope.DECISION_SESSION,event_start=session.open_at)
                if ((head is not None and (head.bar_revision_id != bar_id or head.revision != 1))
                        or (status_head is not None and (status_head.fact_revision_id != status_id or status_head.revision != 1))):
                    raise ValueError("professional replacement revision ordering is not established; preserve original facts")
                statuses.append(SecurityStatusFactRevision(status_id,capture.provider_product_id,capture.capture_id,
                    reference.instrument_id,session.session_id,EvidenceScope.DECISION_SESSION,
                    SecurityStatus.SUSPENDED if row["suspendFlag"] == 1 else SecurityStatus.ACTIVE,
                    session.open_at,session.close_at,1,None))
                opening,high,low,closing = (Decimal(row[name]) for name in ("open","high","low","close"))
                if min(opening,high,low,closing) <= 0 or low > min(opening,closing) or high < max(opening,closing):
                    gaps.append(gap(GapKind.INVALID_OHLC,GapReasonCode.INVALID_OHLC))
                    continue
                volume = Decimal(row["volume"])
                if contract.volume_unit == "LOTS_OF_100_SHARES":
                    parts = volume.as_tuple()
                    assert isinstance(parts.exponent,int)  # finite checked by the recording contract
                    volume = Decimal((parts.sign,parts.digits,parts.exponent+2))
                bars.append(MarketBarRevision(bar_id,capture.provider_product_id,capture.capture_id,reference.instrument_id,
                    session.session_id,BarTimeframe.DAILY,PriceBasis.RAW_UNADJUSTED,session.open_at,session.close_at,1,None,
                    Money(opening,"CNY"),Money(high,"CNY"),Money(low,"CNY"),Money(closing,"CNY"),
                    Quantity(volume,QuantityUnit.SHARES),Money(Decimal(row["amount"]),"CNY")))
        return NormalizationBatch(capture.capture_id,capture.provider_product_id,bars=tuple(bars),
            security_status_facts=tuple(statuses),gaps=tuple(gaps))
