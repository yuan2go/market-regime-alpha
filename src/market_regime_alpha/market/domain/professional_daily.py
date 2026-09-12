"""Bounded XtQuant daily recording contract, without SDK access or PIT claims.

Units and bar timestamp meaning must be supplied from a verified source contract;
the vendor field names alone cannot establish them. Recordings preserve those
declarations alongside the original bytes for the existing Capture owner.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def _closed(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate professional recording field")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class ProfessionalDailyContract:
    sdk_version: str
    instruments: tuple[str, ...]
    start_date: date
    end_date: date
    dividend_type: str
    volume_unit: str
    timestamp_meaning: str
    semantics_evidence_sha256: str
    maximum_rows: int
    maximum_bytes: int
    maximum_requests: int = 1
    fill_data: bool = False
    amount_unit: str = "CNY"
    price_unit: str = "CNY_PER_SHARE"
    timezone: str = "Asia/Shanghai"
    membership_semantics: str = "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED"
    source_availability: str = "UNKNOWN"
    finality: str = "UNVERIFIED_REVISION"

    def __post_init__(self) -> None:
        import re
        if not isinstance(self.sdk_version,str) or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,79}",self.sdk_version):
            raise ValueError("record the exact SDK version")
        if not isinstance(self.instruments,tuple) or not self.instruments or len(self.instruments)>500 or any(not isinstance(s,str) for s in self.instruments) or self.instruments!=tuple(sorted(set(self.instruments))) or any(not re.fullmatch(r"[0-9]{6}\.(SH|SZ)",s) for s in self.instruments):
            raise ValueError("recording needs 1–500 sorted exact XtQuant stock codes")
        if type(self.start_date) is not date or type(self.end_date) is not date or not 0<=(self.end_date-self.start_date).days<=2000:
            raise ValueError("daily recording requires explicit dates spanning at most 2000 calendar days")
        if not isinstance(self.dividend_type,str) or self.dividend_type not in {"none","front","back","front_ratio","back_ratio"}:
            raise ValueError("XtQuant dividend types are distinct; no implicit adjustment mapping")
        if not isinstance(self.volume_unit,str) or self.volume_unit not in {"SHARES","LOTS_OF_100_SHARES"}:
            raise ValueError("volume units require explicit confirmed source semantics")
        if not isinstance(self.timestamp_meaning,str) or self.timestamp_meaning not in {"SESSION_DATE_MARKER","BAR_OPEN","BAR_CLOSE"}:
            raise ValueError("daily timestamp meaning must be explicitly evidenced")
        if not isinstance(self.semantics_evidence_sha256,str):
            raise ValueError("semantics evidence requires an exact hash")
        ContentHash(self.semantics_evidence_sha256)
        if self.fill_data is not False or self.amount_unit!="CNY" or self.price_unit!="CNY_PER_SHARE" or self.timezone!="Asia/Shanghai":
            raise ValueError("recording forbids automatic fill and unconfirmed currency/timezone conversions")
        if self.membership_semantics!="STATIC_UNIVERSE/SURVIVORSHIP_LIMITED" or self.source_availability!="UNKNOWN" or self.finality!="UNVERIFIED_REVISION":
            raise ValueError("this recorded adapter cannot confer historical membership, availability or finality")
        for value,maximum in ((self.maximum_rows,500_000),(self.maximum_bytes,100_000_000),(self.maximum_requests,100)):
            if type(value) is not int or not 1<=value<=maximum:
                raise ValueError("professional recording budget is invalid")

    @classmethod
    def from_bytes(cls,content: bytes) -> "ProfessionalDailyContract":
        if len(content)>100_000:
            raise ValueError("professional contract exceeds byte budget")
        raw=json.loads(content,object_pairs_hook=_closed)
        if not isinstance(raw,dict) or raw.pop("schema",None)!="mra-xtquant-daily-recording-contract-v1":
            raise ValueError("unsupported professional daily contract")
        required={"sdk_version","instruments","start_date","end_date","dividend_type","volume_unit","timestamp_meaning","semantics_evidence_sha256","maximum_rows","maximum_bytes"}
        if not required.issubset(raw) or not set(raw).issubset(cls.__dataclass_fields__):
            raise ValueError("professional recording contract has missing or unknown fields")
        if not isinstance(raw["instruments"],list) or not all(isinstance(raw[key],str) for key in ("start_date","end_date")):
            raise ValueError("professional instrument roster and dates have invalid types")
        raw["instruments"]=tuple(raw["instruments"])
        for key in ("start_date","end_date"):
            raw[key]=date.fromisoformat(raw[key])
        return cls(**raw)

    def verify_recording(self,content: bytes) -> dict[str, Any]:
        if len(content)>self.maximum_bytes:
            raise ValueError("professional recording exceeds frozen byte budget")
        raw=json.loads(content,object_pairs_hook=_closed)
        if not isinstance(raw,dict) or set(raw)!={"schema","evidence_kind","sdk_version","rows"} or raw["schema"]!="mra-xtquant-daily-recording-v1":
            raise ValueError("unsupported recorded daily envelope")
        if not isinstance(raw["evidence_kind"],str) or raw["evidence_kind"] not in {"LOCAL_PROTOCOL_SUBSTITUTE","PROVIDER_RECORDING"} or raw["sdk_version"]!=self.sdk_version:
            raise ValueError("recording must declare evidence kind and match exact SDK version")
        rows=raw["rows"]
        if not isinstance(rows,list) or len(rows)>self.maximum_rows:
            raise ValueError("professional recording exceeds frozen row budget")
        required={"stock_code","session_date","time","open","high","low","close","volume","amount","preClose","suspendFlag","revision"}
        seen: set[tuple[str,date]]=set()
        statuses={"ACTIVE":0,"SUSPENDED":0,"RESUMED":0}
        for row in rows:
            if not isinstance(row,dict) or set(row)!=required:
                raise ValueError("recorded daily fields differ from the frozen contract")
            if not isinstance(row["stock_code"],str) or not isinstance(row["session_date"],str):
                raise ValueError("recorded stock code and session date require text")
            day=date.fromisoformat(row["session_date"])
            key=(row["stock_code"],day)
            if key in seen or key[0] not in self.instruments or not self.start_date<=day<=self.end_date:
                raise ValueError("duplicate, conflicting or out-of-scope daily recording")
            seen.add(key)
            if type(row["time"]) is not int or row["time"]<=0 or type(row["suspendFlag"]) is not int or row["suspendFlag"] not in {-1,0,1}:
                raise ValueError("invalid timestamp or suspension flag; unknown is not active")
            try:
                recorded_day=datetime.fromtimestamp(row["time"]/1000,UTC).astimezone(ZoneInfo(self.timezone)).date()
            except (OverflowError,OSError,ValueError) as exc:
                raise ValueError("recorded timestamp is outside the supported range") from exc
            if recorded_day!=day:
                raise ValueError("recorded timestamp and declared session date disagree")
            if not isinstance(row["revision"],str) or not row["revision"] or len(row["revision"])>100:
                raise ValueError("recording needs an explicit revision token")
            values={}
            for field in ("open","high","low","close","volume","amount","preClose"):
                if not isinstance(row[field],str):
                    raise ValueError("recorded numeric fields require lossless decimal text")
                try:
                    number=Decimal(row[field])
                except InvalidOperation as exc:
                    raise ValueError("invalid recorded decimal") from exc
                if not number.is_finite() or number<0:
                    raise ValueError("recorded numeric values must be finite and nonnegative")
                values[field]=number
            if row["suspendFlag"]!=1 and (min(values[f] for f in ("open","low","high","close"))<=0 or
                    values["low"]>min(values["open"],values["close"]) or values["high"]<max(values["open"],values["close"])):
                raise ValueError("active daily OHLC is invalid")
            statuses[{0:"ACTIVE",1:"SUSPENDED",-1:"RESUMED"}[row["suspendFlag"]]]+=1
        return {"schema":"mra-professional-recording-verification-v1","evidence_kind":raw["evidence_kind"],
            "observation_count":len(rows),"status_counts":statuses,"recording_semantic_sha256":canonical_json_sha256(raw),
            "calendar_coverage":"NOT_CHECKED_REQUIRES_MARKET_CALENDAR_OWNER",
            "market_coverage":"NOT_ESTIMABLE_WITHOUT_CALENDAR_AND_INSTRUMENT_FACTS",
            "normalization":"NOT_RUN_REQUIRES_EVIDENCED_TIMESTAMP_AND_ADJUSTMENT_MAPPING",
            "source_available_at":None,"formal_pit":False,"professional_provider_validation":"NOT_RUN"}
