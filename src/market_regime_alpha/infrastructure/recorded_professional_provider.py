"""Local recorded protocol substitute behind the existing MarketProvider port."""

from hashlib import sha256
from dataclasses import asdict
import base64
import json
from threading import Lock
from uuid import UUID

from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.ports.provider import CaptureRequest, MarketProviderError, ProviderResponse
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


class RecordedProfessionalMarketProvider:
    def __init__(self,contract: ProfessionalDailyContract, content: bytes, *, expected_sha256: str, normalization_evidence: bytes | None = None) -> None:
        if sha256(content).hexdigest()!=expected_sha256:
            raise ValueError("professional recording physical hash differs")
        self.verification=contract.verify_recording(content)
        contract_payload={"schema":"mra-xtquant-daily-recording-contract-v1",**asdict(contract)}
        self.resource="recorded-xtquant-daily:"+canonical_json_sha256(asdict(contract))+":"+expected_sha256
        # The original Capture Artifact is sufficient after a fresh restore:
        # it contains the full contract and lossless vendor-recording bytes.
        self._envelope={"schema":"mra-recorded-professional-capture-v2","contract":contract_payload,
            "recording_sha256":expected_sha256,"recording_base64":base64.b64encode(content).decode("ascii")}
        if normalization_evidence is not None:
            from market_regime_alpha.market.domain.professional_normalization import verify_normalization_evidence
            verify_normalization_evidence(contract,normalization_evidence,recording_kind=self.verification["evidence_kind"])
            self.resource += ":normalization-v1:"+contract.semantics_evidence_sha256
            self._envelope.update(schema="mra-recorded-professional-capture-v3",
                normalization_evidence_base64=base64.b64encode(normalization_evidence).decode("ascii"))
            self.verification["normalization_mapping"]="EMBEDDED_EXACT_EVIDENCE_REQUIRES_MARKET_OWNER"
        self._remaining_requests=contract.maximum_requests
        self._budget_lock=Lock()

    def capture(self,request: CaptureRequest) -> ProviderResponse:
        if request.resource!=self.resource:
            raise MarketProviderError("RECORDED_REQUEST_MISMATCH","recorded Provider only serves its exact frozen resource")
        with self._budget_lock:
            if self._remaining_requests<1:
                raise MarketProviderError("RECORDED_REQUEST_BUDGET_EXHAUSTED","recorded Provider invocation exhausted its request budget")
            self._remaining_requests-=1
        envelope={**self._envelope,"request":{"provider_product_id":str(request.provider_product_id),
            "capture_key":request.capture_key,"resource":request.resource,"request_headers_sha256":str(request.request_headers_hash)}}
        content=json.dumps(envelope,sort_keys=True,separators=(",",":"),default=str,allow_nan=False).encode()
        return ProviderResponse(content,"application/json","UTF-8",None,SourceAvailabilityStatus.UNKNOWN,None,
            "RECORDED_PROTOCOL_ONLY_NO_PROVIDER_QUALIFICATION")


def replay_professional_capture(content: bytes) -> tuple[ProfessionalDailyContract, bytes, dict]:
    from market_regime_alpha.market.domain.professional_daily import _closed
    if len(content)>134_000_000:
        raise ValueError("recorded Capture envelope exceeds the bounded base64 budget")
    raw=json.loads(content,object_pairs_hook=_closed)
    fields={"schema","contract","recording_sha256","recording_base64"}
    if not isinstance(raw,dict) or not isinstance(raw.get("schema"),str) or raw["schema"] not in {"mra-recorded-professional-capture-v1","mra-recorded-professional-capture-v2","mra-recorded-professional-capture-v3"}:
        raise ValueError("unsupported recorded Capture envelope")
    version_two=raw["schema"]!="mra-recorded-professional-capture-v1"
    version_three=raw["schema"]=="mra-recorded-professional-capture-v3"
    if set(raw)!=(fields|({"request"} if version_two else set())|({"normalization_evidence_base64"} if version_three else set())):
        raise ValueError("recorded Capture envelope fields differ")
    if not isinstance(raw["recording_base64"],str) or not isinstance(raw["recording_sha256"],str):
        raise ValueError("recorded Capture byte identity fields require text")
    contract=ProfessionalDailyContract.from_bytes(json.dumps(raw["contract"],sort_keys=True).encode())
    try:
        recording=base64.b64decode(raw["recording_base64"],validate=True)
    except ValueError as exc:
        raise ValueError("recorded Capture has invalid byte encoding") from exc
    if sha256(recording).hexdigest()!=raw["recording_sha256"]:
        raise ValueError("recorded Capture original byte hash differs")
    verification=contract.verify_recording(recording)
    if version_three:
        from market_regime_alpha.market.domain.professional_normalization import verify_normalization_evidence
        if not isinstance(raw["normalization_evidence_base64"],str):
            raise ValueError("professional normalization evidence requires exact encoded bytes")
        evidence=base64.b64decode(raw["normalization_evidence_base64"],validate=True)
        verification["normalization_evidence"]=verify_normalization_evidence(contract,evidence,recording_kind=verification["evidence_kind"])
        verification["normalization_mapping"]="EMBEDDED_EXACT_EVIDENCE_REQUIRES_MARKET_OWNER"
    verification["capture_request_identity"]="LEGACY_UNVERIFIED"
    if version_two:
        request=raw["request"]
        if not isinstance(request,dict) or set(request)!={"provider_product_id","capture_key","resource","request_headers_sha256"} or any(not isinstance(v,str) for v in request.values()):
            raise ValueError("recorded Capture requires exact non-sensitive request fields")
        expected_resource="recorded-xtquant-daily:"+canonical_json_sha256(asdict(contract))+":"+raw["recording_sha256"]
        if version_three:
            expected_resource += ":normalization-v1:"+contract.semantics_evidence_sha256
        if request["resource"]!=expected_resource:
            raise ValueError("recorded Capture request and source contract differ")
        identity=CaptureRequest(UUID(request["provider_product_id"]),request["capture_key"],request["resource"],ContentHash(request["request_headers_sha256"]))
        verification.update(capture_request_identity="BOUND_ENVELOPE_REQUIRES_OWNER_MATCH",
            capture_request_sha256=canonical_json_sha256(identity),capture_request=request)
    return contract,recording,verification
