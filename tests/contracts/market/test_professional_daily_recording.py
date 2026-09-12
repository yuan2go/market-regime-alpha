from dataclasses import replace
from datetime import date
from hashlib import sha256
import json
from uuid import UUID

import pytest

from market_regime_alpha.infrastructure.recorded_professional_provider import RecordedProfessionalMarketProvider,replay_professional_capture
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.ports.provider import CaptureRequest,MarketProviderError
from market_regime_alpha.shared.hashing import canonical_json_sha256


def contract():
    return ProfessionalDailyContract("fixture-1",("600000.SH",),date(2025,1,2),date(2025,1,3),"none","SHARES",
        "SESSION_DATE_MARKER","a"*64,2,10000)


def payload():
    return {"schema":"mra-xtquant-daily-recording-v1","evidence_kind":"LOCAL_PROTOCOL_SUBSTITUTE","sdk_version":"fixture-1",
        "rows":[{"stock_code":"600000.SH","session_date":"2025-01-02","time":1735776000000,
            "open":"10","high":"11","low":"9","close":"10.5","volume":"100","amount":"1050",
            "preClose":"10","suspendFlag":-1,"revision":"synthetic-engineering-1"}]}


def test_recorded_provider_keeps_exact_bytes_unknown_availability_and_capture_identity():
    raw=json.dumps(payload()).encode()
    digest=sha256(raw).hexdigest()
    provider=RecordedProfessionalMarketProvider(contract(),raw,expected_sha256=digest)
    request=CaptureRequest(UUID(int=1),"local-contract",provider.resource,"b"*64)
    response=provider.capture(request)
    replayed_contract,replayed_bytes,replayed_verification=replay_professional_capture(response.content)
    assert replayed_contract==contract() and replayed_bytes==raw
    assert all(replayed_verification[key]==value for key,value in provider.verification.items())
    assert replayed_verification["capture_request_sha256"]==canonical_json_sha256(request)
    assert replayed_verification["capture_request_identity"]=="BOUND_ENVELOPE_REQUIRES_OWNER_MATCH"
    assert response.source_available_at is None and response.provider_time is None
    assert provider.verification["status_counts"]=={"ACTIVE":0,"SUSPENDED":0,"RESUMED":1}
    assert provider.verification["professional_provider_validation"]=="NOT_RUN"
    with pytest.raises(MarketProviderError,match="exact frozen resource"):
        provider.capture(replace(request,resource="recorded-xtquant-daily:"+"c"*64))
    with pytest.raises(ValueError,match="physical hash"):
        RecordedProfessionalMarketProvider(contract(),raw+b" ",expected_sha256=digest)
    with pytest.raises(MarketProviderError,match="request budget"):
        provider.capture(request)
    envelope=json.loads(response.content)
    envelope["recording_sha256"]="f"*64
    with pytest.raises(ValueError,match="byte hash differs"):
        replay_professional_capture(json.dumps(envelope).encode())
    envelope=json.loads(response.content)
    envelope["request"]["resource"]="another-resource"
    with pytest.raises(ValueError,match="request and source contract differ"):
        replay_professional_capture(json.dumps(envelope).encode())
    legacy=json.loads(response.content)
    legacy.pop("request")
    legacy["schema"]="mra-recorded-professional-capture-v1"
    assert replay_professional_capture(json.dumps(legacy).encode())[2]["capture_request_identity"]=="LEGACY_UNVERIFIED"
    legacy["schema"]=[]
    with pytest.raises(ValueError,match="unsupported recorded Capture envelope"):
        replay_professional_capture(json.dumps(legacy).encode())


@pytest.mark.parametrize("field,value",[("volume","NaN"),("volume",100),("suspendFlag",True),("suspendFlag",2),("close","12"),("session_date","2026-01-01"),("time",1735776000000+86400000)])
def test_recorded_contract_rejects_ambiguous_or_invalid_rows(field,value):
    raw=payload()
    raw["rows"][0][field]=value
    with pytest.raises(ValueError):
        contract().verify_recording(json.dumps(raw).encode())


def test_recorded_contract_preserves_suspension_and_rejects_duplicates_and_auto_fill():
    raw=payload()
    row=raw["rows"][0]
    row.update(suspendFlag=1,open="0",high="0",low="0",close="0",volume="0",amount="0")
    assert contract().verify_recording(json.dumps(raw).encode())["status_counts"]["SUSPENDED"]==1
    raw["rows"].append(dict(row))
    with pytest.raises(ValueError,match="duplicate"):
        contract().verify_recording(json.dumps(raw).encode())
    with pytest.raises(ValueError,match="automatic fill"):
        replace(contract(),fill_data=True)
    with pytest.raises(ValueError,match="volume units"):
        replace(contract(),volume_unit="UNKNOWN")


def test_recorded_contract_has_no_defaults_for_missing_semantics_or_source_claims():
    raw=json.dumps({"schema":"mra-xtquant-daily-recording-contract-v1"}).encode()
    with pytest.raises(ValueError,match="missing or unknown"):
        ProfessionalDailyContract.from_bytes(raw)
    with pytest.raises(ValueError,match="availability or finality"):
        replace(contract(),source_availability="PIT")


@pytest.mark.parametrize("changes",[{"sdk_version":[]},{"instruments":None},{"dividend_type":[]},{"volume_unit":[]},{"timestamp_meaning":[]},{"semantics_evidence_sha256":[]}])
def test_recorded_contract_closes_error_types(changes):
    with pytest.raises(ValueError):
        replace(contract(),**changes)


def test_recorded_row_closes_wrong_identity_types():
    raw=payload()
    raw["rows"][0]["stock_code"]=[]
    with pytest.raises(ValueError,match="require text"):
        contract().verify_recording(json.dumps(raw).encode())
