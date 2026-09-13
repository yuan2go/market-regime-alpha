"""Explicit recorded-source mapping evidence; no vendor or PIT qualification.

Only unadjusted daily prices are supported. A caller must retain the actual
mapping evidence inside Capture; a hash or a field name alone is insufficient.
"""

from datetime import datetime, timedelta
from hashlib import sha256
import json
import re
from uuid import UUID

from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract, _closed


def verify_normalization_evidence(contract: ProfessionalDailyContract, content: bytes, *, recording_kind: str) -> dict:
    if not isinstance(content, bytes) or len(content) > 100_000 or sha256(content).hexdigest() != contract.semantics_evidence_sha256:
        raise ValueError("professional normalization evidence bytes/hash differ")
    raw = json.loads(content, object_pairs_hook=_closed)
    expected = {"schema", "evidence_kind", "sdk_version", "dividend_type", "price_basis", "price_unit", "volume_unit",
        "amount_unit", "timestamp_meaning", "timezone", "suspension_mapping", "source_reference"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema"] != "mra-professional-normalization-evidence-v1":
        raise ValueError("professional normalization requires its exact mapping evidence contract")
    evidence_kind = "LOCAL_PROTOCOL_SUBSTITUTE" if recording_kind == "LOCAL_PROTOCOL_SUBSTITUTE" else "PROVIDER_SEMANTIC_EVIDENCE"
    if raw["evidence_kind"] != evidence_kind or not isinstance(raw["source_reference"], str) or not 1 <= len(raw["source_reference"]) <= 1000:
        raise ValueError("recording and mapping evidence kinds/reference differ")
    if contract.dividend_type != "none" or raw["dividend_type"] != "none" or raw["price_basis"] != "RAW_UNADJUSTED":
        raise ValueError("professional adjusted-price mapping is not established; no cross-provider equivalence")
    for name in ("sdk_version", "price_unit", "volume_unit", "amount_unit", "timestamp_meaning", "timezone"):
        if raw[name] != getattr(contract, name):
            raise ValueError("professional mapping differs from its frozen source semantics: " + name)
    if raw["suspension_mapping"] != {"0": "ACTIVE", "1": "SUSPENDED", "-1": "ACTIVE_RESUMED_FLAG_RETAINED_IN_CAPTURE"}:
        raise ValueError("professional suspension mapping is unknown")
    return raw


def verify_recorded_archive_scope(content: bytes) -> dict:
    """Decode the distinct RAW-only recorded inventory scope, not acquisition v1."""
    if not isinstance(content, bytes) or len(content)>1_000_000:
        raise ValueError("recorded Archive scope exceeds its byte budget")
    raw=json.loads(content,object_pairs_hook=_closed)
    fields={'schema','securities','price_inventory','universe','source_contract','recording_capture_id','reference_capture_ids',
        'captures','code_sha','wheel_sha256','lockfile_sha256','budgets','qualification'}
    if not isinstance(raw,dict) or set(raw)!=fields or raw['schema']!='mra-recorded-archive-scope-v1':
        raise ValueError("unsupported recorded Archive scope")
    if not isinstance(raw['source_contract'],dict) or 'schema' in raw['source_contract']:
        raise ValueError("recorded Archive source contract has an invalid shape")
    contract=ProfessionalDailyContract.from_bytes(json.dumps({'schema':'mra-xtquant-daily-recording-contract-v1',**raw['source_contract']}).encode())
    if (contract.dividend_type!='none' or raw['price_inventory']!={'target':'RAW_UNADJUSTED','cross_day_features':'NOT_SUPPORTED'}
            or raw['universe']!='STATIC_UNIVERSE/SURVIVORSHIP_LIMITED'
            or raw['qualification']!='RECORDED_SOURCE_NOT_PIT_OR_PROVIDER_QUALIFICATION'):
        raise ValueError("recorded Archive cannot infer adjustment, membership or qualification")
    securities=raw['securities']
    if (not isinstance(securities,list) or any(not isinstance(row,list) or len(row)!=2 for row in securities)
            or tuple(row[0] for row in securities)!=contract.instruments):
        raise ValueError("recorded Archive securities differ from the source contract")
    def identity(value):
        if not isinstance(value,str):
            raise ValueError("recorded Archive requires textual UUID identities")
        return UUID(value)
    ids=tuple(identity(row[1]) for row in securities)
    if len(set(ids))!=len(ids):
        raise ValueError("recorded Archive repeats a canonical instrument")
    references=raw['reference_capture_ids']
    if not isinstance(references,list) or not 1<=len(references)<=8:
        raise ValueError("recorded Archive reference Capture budget is invalid")
    capture_ids=tuple(identity(x) for x in (*references,raw['recording_capture_id']))
    if len(set(capture_ids))!=len(capture_ids) or not isinstance(raw['captures'],list) or len(raw['captures'])!=len(capture_ids):
        raise ValueError("recorded Archive Capture roster is incomplete or repeated")
    capture_fields={'capture_id','request_sha256','known_at','artifact_sha256','artifact_size_bytes'}
    if any(not isinstance(row,dict) or set(row)!=capture_fields for row in raw['captures']):
        raise ValueError("recorded Archive Capture fields differ from its closed contract")
    if tuple(identity(row['capture_id']) for row in raw['captures'])!=capture_ids:
        raise ValueError("recorded Archive Capture identities differ from its frozen roster")
    def digest(value,length):
        if not isinstance(value,str) or re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is None:
            raise ValueError("recorded Archive code/artifact/request digest is invalid")
    for name,length in (('code_sha',40),('wheel_sha256',64),('lockfile_sha256',64)):
        digest(raw[name],length)
    budgets=raw['budgets']
    if (not isinstance(budgets,dict) or set(budgets)!={'reserved_free_bytes','maximum_slice_bytes','maximum_archive_bytes'}
            or any(type(v) is not int for v in budgets.values()) or budgets['reserved_free_bytes']<0
            or not 1<=budgets['maximum_slice_bytes']<=budgets['maximum_archive_bytes']):
        raise ValueError("recorded Archive byte budgets are invalid")
    known=[]
    for row in raw['captures']:
        digest(row['request_sha256'],64)
        digest(row['artifact_sha256'],64)
        if type(row['artifact_size_bytes']) is not int or not 1<=row['artifact_size_bytes']<=budgets['maximum_slice_bytes']:
            raise ValueError("recorded Archive Capture exceeds its slice byte budget")
        if not isinstance(row['known_at'],str):
            raise ValueError("recorded Archive knowledge timestamp must be explicit UTC")
        value=datetime.fromisoformat(row['known_at'])
        if value.utcoffset()!=timedelta(0):
            raise ValueError("recorded Archive knowledge timestamp must be explicit UTC")
        known.append(value)
    if any(t>known[-1] for t in known) or sum(row['artifact_size_bytes'] for row in raw['captures'])>budgets['maximum_archive_bytes']:
        raise ValueError("recorded Archive Capture knowledge order or total byte budget is invalid")
    return raw
