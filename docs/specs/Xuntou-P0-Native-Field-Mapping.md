# Xuntou P0 Native Field Mapping

Status: `P0 MAPPING CONTRACT COMPLETE; RUNTIME SEMANTICS PARTIALLY VERIFIED`
Contract version: `xuntou-p0-native-field-mapping-v3`
Provider ID: `xuntou-thinktrader-xtquant-p0-v3`
Decision Time: `14:55:00 Asia/Shanghai`
Maximum authority: `REHEARSAL`
Official documentation reviewed: `2026-07-16`

## 1. Purpose and boundary

This specification defines the smallest truthful translation from Xuntou-native evidence into the
existing R5 canonical rehearsal contracts. It does not define a Candidate model, Entry/Exit policy,
Portfolio decision, execution rule, or formal-research data authority.

The implemented boundary is:

```text
Xuntou native fields retained in an identified export
        -> Xuntou P0 normalization and conservative state materialization
        -> existing Calendar / Universe / Eligibility / Rehearsal contracts
        -> ProviderRehearsalMarketArtifact (REHEARSAL only)
```

The adapter does not call XtQuant at runtime. A producer in an authorized Xuntou environment must
create the normalized native export and preserve its content hash, retrieval time, locator,
availability assertions, and limitations.

## 2. Provider identity and verified product relationships

- **Provider:** Xuntou (迅投).
- **Product family:** ThinkTrader / QMT / MiniQMT are provider-side products or clients. This
  contract does not claim that those product names are interchangeable.
- **Python API:** XtQuant is the Python library/framework. Official documentation says it is based
  on MiniQMT and exposes market-data and trading APIs; `xtdata` is the market-data module and talks
  to MiniQMT. Trading APIs are outside P0.
- **Runtime:** the official quick start requires an appropriate XtQuant build and normally a
  running MiniQMT client. XtQuant is not treated as a normal cross-platform mandatory project
  dependency.
- **Contract identity:** `ProviderReference(provider_id="xuntou-thinktrader-xtquant-p0-v3",
  product="ThinkTrader/XtQuant normalized native export", contract_version=
  "xuntou-p0-native-field-mapping-v3")`.

Primary official sources:

- [XtQuant quick start and MiniQMT relationship](https://dict.thinktrader.net/nativeApi/start_now.html)
- [XtData APIs, periods, adjustment modes, and field dictionary](https://dict.thinktrader.net/nativeApi/xtdata.html)
- [A-share instrument, ST, bar, and historical limit-price dictionary](https://dict.thinktrader.net/dictionary/stock.html)
- [Sector data and current/expired constituent examples](https://dict.thinktrader.net/dictionary/industry.html)
- [Official XtQuant distribution history](https://dict.thinktrader.net/nativeApi/download_xtquant.html)

The claim-by-claim first-party evidence review is recorded in
[`docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md`](../research/R5-Xuntou-P0-Official-Documentation-Evidence.md).

## 3. Mandatory mapping classifications

Every mapping uses one of these statuses:

- `DIRECT_NATIVE`: the official field/API meaning directly supplies the canonical value.
- `DERIVED_FROM_NATIVE`: a versioned deterministic transformation of native evidence.
- `REQUIRES_STATE_MATERIALIZATION`: multiple as-of observations or intervals must be combined.
- `CURRENT_ONLY_NOT_HISTORICAL_PIT`: an official current value exists but cannot represent an
  earlier Decision Time.
- `UNVERIFIED`: an API/field exists, but the official material reviewed does not establish the
  required time, availability, finality, completeness, or PIT semantics.
- `UNAVAILABLE_IN_P0`: P0 has no authoritative native mapping.

`DIRECT_NATIVE` does not imply historical PIT correctness. The PIT and availability columns remain
independent assessments.

## 4. Result-affecting conventions

The following version strings must be present in the export or adapter identity:

| Convention | Versioned value | Meaning |
|---|---|---|
| Symbol normalization | `XUNTOU_SYMBOL_NORMALIZATION_V1` | Preserve official uppercase `code.market`; accept six digits plus `.SH`, `.SZ`, or `.BJ`; require an explicit A-share-stock classification. |
| Calendar close | `A_SHARE_STANDARD_SESSION_CLOSE_1500_ASIA_SHANGHAI_V1` | Derive session close at 15:00 Asia/Shanghai from a provider trading date; it is a project convention, not a provider timestamp. |
| Decision snapshot | `XUNTOU_1455_REFERENCE_PRICE_CONVENTION_V2` | Use the latest completed unadjusted 1-minute `close` whose observation label is inside the closed `[14:54:00, 14:55:00]` Asia/Shanghai window and whose exporter-declared availability is no later than 14:55. The native bar-open/bar-close label convention is not assumed. |
| Availability | `XUNTOU_EXPLICIT_EXPORT_AVAILABILITY_V1` | Every bar/state record carries an exporter-supplied timezone-aware `available_at`; no timestamp is synthesized from retrieval time. |
| Bar finality | `XUNTOU_EXPLICIT_EXPORT_FINALITY_V2` | The exporter must mark final bars. A daily/next-session bar is rejected when `available_at` is earlier than the versioned session close; the selected minute bar must be explicitly complete. This lower bound is a project convention, not a provider SLA. |
| Price adjustment | `XUNTOU_DIVIDEND_TYPE_NONE_RAW_V1` | P0 uses `dividend_type='none'` unadjusted provider prices for bars, Decision-Time reference price, and Candidate targets. “Unadjusted” does not independently certify tradability. |
| Liquidity | `MEDIAN_AMOUNT_PREVIOUS_20_FINAL_SESSIONS_XUNTOU_NATIVE_UNITS_V1` | Median native `amount` over the 20 finalized sessions strictly before the Decision Date and available by Decision Time. The reviewed official pages do not establish a formal currency/scale contract, so P0 does not rename the value to CNY. |
| Universe effective time | `XUNTOU_EXPLICIT_DATE_MEMBERSHIP_UNVERIFIED_PIT_V1` | Preserve supplied date-specific records, but do not claim that current sector data reconstructs historical membership. |
| Buyability | `XUNTOU_DECISION_BUYABILITY_EVIDENCE_V2` | A confirmed suspension is `NOT_BUYABLE`. Historical minute prices and limit levels do not prove a sealed limit, ask liquidity, queue state, or `BUYABLE`; all other P0 cases remain `UNKNOWN`. |
| ST interval | `XUNTOU_ST_INTERVAL_INCLUSIVE_DATE_V1` | Materialize ST/*ST/PT interval endpoints as inclusive dates for P0. The provider does not establish endpoint/effective-time semantics, so this is a versioned project convention and remains PIT-unverified. |

For the 14:55 convention, `time` is the native observation timestamp, while `available_at` is a
separate export assertion. P0 does not claim that a row labeled `14:55` is necessarily an exact
14:55:00 exchange snapshot, a bar-open label, or a bar-close label. A producer must select a
completed row inside the versioned one-minute freshness window whose availability is no later than
the canonical Decision Time. An older same-day row is stale evidence and is rejected.

## 5. P0 evidence requirement matrix

### 5.1 Trading calendar

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Historical trading dates | `TradingCalendarArtifact` | `xtdata.get_trading_calendar(market, start_time, end_time)`; `get_trading_dates` is also documented | list item | `str` (`YYYYMMDD`) or timestamp list for the older API | trade date | `TradingSession.trade_date` | Parse explicit date | Export `retrieved_at`; historical knowledge time is not asserted | Returned calendar is treated as a provider calendar snapshot | Historical dates direct; future calendar can change | `DIRECT_NATIVE` | No weekday inference | HIGH | P0 accepts only explicit `SH` or `SZ` calendar exports; completeness still depends on downloaded holiday/calendar data, and BJ calendar equivalence/support is unverified |
| Session close | Calendar consumers | No provider-native close timestamp returned by the calendar API | none | none | trade date only | `TradingSession.session_close` | Combine date with 15:00 Asia/Shanghai under the versioned convention | Derived convention | Convention, not provider finality | Not provider-native PIT evidence | `DERIVED_FROM_NATIVE` | Reject another silent close time | HIGH for transformation | Half-days or exceptional sessions require a future convention version |

### 5.2 Security and instrument identity

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Provider symbol | Universe, bars, eligibility | `get_instrument_detail`; all market APIs | `stock_code`, `ExchangeID`, `InstrumentID` | string | none | `symbol` | Preserve official `code.market` form | Known at export retrieval; symbol existed by dated evidence | Static identifier record | Current instrument detail is not a historical security master | `DIRECT_NATIVE` | Reject malformed symbols | HIGH | Official examples confirm `.SH`, `.SZ`, `.BJ`; no case conversion beyond uppercase validation |
| A-share instrument type | Candidate Universe filter | `xtdata.get_instrument_type(stock_code)` plus explicit market scope | returned `stock`, `index`, `fund`, `etf` flags | dict[str, bool] | retrieval state | accepted instrument | Export normalized `A_SHARE_STOCK` only when the native `stock` classification and SH/SZ/BJ market scope agree; filter ETF/index/fund and unsupported instruments | Explicit exporter classification | N/A | Classification provenance may be current-only | `DIRECT_NATIVE` for native type; historical PIT `UNVERIFIED` | Reject missing/ambiguous stock classification; never infer solely from code prefix | HIGH for API meaning | The reviewed official pages do not provide one complete stable enumeration for every security category/client version |
| STAR / ChiNext / BSE | Universe filter | Native symbol plus explicit stock classification | `.SH`, `.SZ`, `.BJ` | string | none | canonical symbol | No board-based exclusion | Same as symbol | N/A | Same as identity evidence | `DIRECT_NATIVE` | Keep if classified A-share stock | HIGH | ETF and index codes can overlap numeric prefixes, hence explicit type is mandatory |

### 5.3 Historical Candidate Universe membership

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Current A-share list | Universe exporter | `get_stock_list_in_sector("沪深A股")`, corresponding BSE sector, or `"沪深京A股"` where available | returned code list | list[str] | retrieval state; optional time parameter is version/interface dependent | membership records | Explicitly date and label the exported list | Available when retrieved | Snapshot of provider sector data | **Not historical PIT by default** | `CURRENT_ONLY_NOT_HISTORICAL_PIT` | Preserve only as current observation | HIGH | Must never be backfilled across earlier dates |
| Date-specific membership | `HistoricalPITUniverseArtifact` | Some official ContextInfo documentation accepts a `timetag`; native `real_timetag` exists in newer XtData versions | returned code list | list[str] | requested date/time | `is_member` by date | Materialize explicit positive/negative records for each supplied date | Export must preserve request time and retrieval time | Depends on downloaded sector-history snapshot | Completeness and survivorship semantics not established for the full A-share market | `UNVERIFIED` | Force `pit_correct_for_scope=False` | LOW/MEDIUM | `CURRENT_MEMBERSHIP_BACKFILL_BIAS`; delisted/expired sectors do not alone prove complete daily membership history |

The P0 adapter always builds the existing artifact shape but always passes
`pit_correct_for_scope=False`. A real provider-backed run must independently establish historical
membership coverage before any authority upgrade.

### 5.4 Listing date and listing age

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IPO/listing date | Eligibility evidence | `xtdata.get_instrument_detail(stock_code)` | `OpenDate` | str `YYYYMMDD` | listing date | intermediate listing date | Parse only valid dates; reject documented sentinel dates as missing | Current instrument detail retrieval | Generally static after listing | Current detail, not a versioned historical security master | `CURRENT_ONLY_NOT_HISTORICAL_PIT` | Invalid/sentinel -> `None` | HIGH for field meaning | Corporate identity changes and provider corrections are not versioned |
| Listing age | Eligibility policy | derived | `OpenDate` + Decision Date | int days | Decision Date | `listing_age_calendar_days` | `(decision_date - OpenDate).days` | Available only if listing date evidence is present | Deterministic | Inherits source limitation | `DERIVED_FROM_NATIVE` | Missing -> `None`, never a large sentinel | HIGH | Existing policy threshold remains 61 calendar days; adapter does not change policy |

### 5.5 Historical ST state

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ST/*ST/PT intervals | Eligibility evidence | `download_his_st_data`; `get_his_st_data(stock_code)` | keys `ST`, `*ST`, `PT`, values date intervals | dict[str, list[list[str]]] | inclusive interval endpoints are provider data; exact boundary convention is not expressly stated | `is_st` at Decision Date | Interval materialization under explicit inclusive-date P0 convention | Exporter must declare download complete and provide explicit `available_at` | Historical interval dataset snapshot | Historical state source exists; historical knowledge/retroactive corrections not established | `REQUIRES_STATE_MATERIALIZATION` | Missing/unlicensed/not downloaded -> `None` | MEDIUM | VIP data; an empty dict is authoritative only when export marks lookup complete |
| Current name/status heuristic | none | current instrument name/detail | `InstrumentName` or current status | string/int | retrieval state | none | No mapping | Current only | Current only | Not historical | `CURRENT_ONLY_NOT_HISTORICAL_PIT` | Never use for past dates | HIGH | Auxiliary source may be required if historical ST export is unavailable; not implemented |

### 5.6 Suspension / trading status

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Historical bar suspension flag | Eligibility evidence | `get_market_data_ex(..., period='1m'/'1d')` | `suspendFlag`: 0 normal, 1 suspended; one official XtData table also documents -1 as resumed that day | int | bar `time` | `is_suspended` | 1 -> True; 0 or -1 -> False | Must be explicit and available by Decision Time | Requires completed selected bar | Historical row exists, but availability assertion remains exporter-owned | `DIRECT_NATIVE` | Missing/other value -> `None` | MEDIUM/HIGH for version-scoped field mapping | Official pages are inconsistent about whether -1 is in the enumeration; capture the runtime/client build, require `fill_data=False`, and never let filled bars manufacture trading state |
| Current instrument status | current diagnostics only | `get_instrument_detail` | `InstrumentStatus`, `IsTrading` | int/bool | retrieval state | none for historical Decision Time | No historical mapping | Current retrieval only | Current only | Not historical | `CURRENT_ONLY_NOT_HISTORICAL_PIT` | Ignore for historical eligibility | HIGH | Current normal trading must never overwrite a past suspension |

### 5.7 Previous close and price limits

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Previous close | Eligibility | K-line data | `preClose` | float | bar `time` | `prev_close` | Positive finite float | Must be available by Decision Time | Selected completed bar | Direct dated bar evidence | `DIRECT_NATIVE` | Missing/zero -> `None` | HIGH | Do not substitute current `get_instrument_detail.PreClose` for history |
| Historical limit prices | Eligibility | `download_history_data(..., period='stoppricedata')`; `get_market_data_ex(..., period='stoppricedata')` | `涨停价`, `跌停价` | float | `time` | `limit_up_price`, `limit_down_price` | Positive finite floats | Explicit export availability | Historical dataset row | Historical values exist; correction/availability history not established | `DIRECT_NATIVE` | Missing/zero -> `None` | HIGH for field meaning | Xuntou Research/VIP entitlement required |
| Current limit prices | current diagnostics only | `get_instrument_detail` | `UpStopPrice`, `DownStopPrice` | float | retrieval state | none for past decisions | No historical mapping | Current retrieval only | Current only | Not historical | `CURRENT_ONLY_NOT_HISTORICAL_PIT` | Ignore for past decisions | HIGH | Never derive past limits from current detail |
| Limit regime identity | Eligibility | no complete native P0 rule identity found | none | none | Decision Date | `limit_regime` | Only accept an explicit exporter-supplied versioned regime identifier | Explicit evidence | Explicit evidence | Unverified | `UNVERIFIED` | Missing -> `None` | LOW | Do not use `prev_close * 1.10`; board/ST/IPO/special rules remain outside P0 derivation |

### 5.8 Historical daily OHLCV / amount

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Daily prices and activity | Feature evidence and next-session target input | `get_market_data_ex`, period `1d`, `dividend_type='none'`, `fill_data=False` | `time`, `open`, `high`, `low`, `close`, `volume`, `amount`, `preClose`, `suspendFlag` | int/float | `time` | `RehearsalDailyBar`; provider-native DTO retains full OHLCV | Raw finite prices; canonical daily bar uses `close` and `amount` | Daily feature bar must be available before its consuming Decision Time | Export must mark the bar final, and `available_at` must not precede the versioned session close | Dated market data; vendor correction history not established | `DIRECT_NATIVE` | Reject non-final, pre-close-available, or missing required values | HIGH for field meaning | `amount` is documented as turnover amount, but formal currency/scale and provider finality SLA remain unverified; no adjusted/raw mixing |

All P0 price-side data uses `dividend_type='none'`. Adjusted prices may be introduced later as a
separate Feature-side artifact with a separate identity, never by altering this target-side raw
artifact.

### 5.9 14:55 Decision-Time price snapshot

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Intraday reference price | `RehearsalDecisionSnapshot` | `get_market_data_ex`, period `1m`, `dividend_type='none'`, `fill_data=False` | `time`, `close` | int/float | normalized aware `time` plus exporter `available_at` | `decision_time`, `reference_price`, `available_at` | Select the latest completed row labelled from 14:54 through 14:55 and explicitly available by 14:55; use its `close` | Must satisfy `available_at <= 14:55` | Exporter must mark selected minute complete | Timestamp-label semantics not established | `UNVERIFIED` + `DERIVED_FROM_NATIVE` | Ambiguous, stale, or unavailable -> explicit adapter error, never use a later or older same-day bar | MEDIUM | This is not claimed to be an exchange exact snapshot; only the versioned freshness window bounds staleness while bar-open/bar-close meaning remains unverified |

### 5.10 Decision-Time buyability

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Candidate-population buyability | Eligibility | selected minute row + historical `suspendFlag`; historical limits retained only as separate metadata | multiple fields | mixed | exact Decision Time evidence | `DecisionBuyabilityStatus` | Confirmed suspension -> `NOT_BUYABLE`; every non-suspended/missing-status case -> `UNKNOWN` | Selected evidence must be available by Decision Time | Selected row complete | Inherits all sources | `REQUIRES_STATE_MATERIALIZATION` + `UNVERIFIED` | `UNKNOWN`; P0 does not emit `BUYABLE` | HIGH for conservative rule | A reference price at the upper limit is not universal non-buyability; dated sealed-limit/ask/queue evidence is not established in P0 |

### 5.11 Liquidity evidence

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20-session median amount | Eligibility raw evidence | 20 prior `1d` rows | `amount` | float | daily `time` | `liquidity_value`, `liquidity_measure_id` | Median of exactly 20 prior finalized session amounts, strict date-before-decision | Every contributing bar available by Decision Time | All contributing bars final | Dated bar evidence | `DERIVED_FROM_NATIVE` | Fewer than 20 valid rows -> both fields `None` | HIGH | This is separately materialized eligibility evidence even if a predictive Feature later uses the same raw amount family |

### 5.12 Next-session OHLC

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Next trading-session raw bar | Candidate target materialization | `get_market_data_ex`, period `1d`, `dividend_type='none'`, `fill_data=False` | `open`, `high`, `low`, `close`, `time` | float/int | `time` | `RehearsalNextSessionBar` | Resolve date only through `TradingCalendarArtifact.resolve_next_session_date()` and match the final native row | `available_at` must be after the Decision Time | Must be final after next-session close | Target evidence is intentionally future to Decision Time | `DIRECT_NATIVE` | Missing resolved bar -> explicit adapter error | HIGH | Never use calendar-date + 1; target evidence remains separate from feature evidence |

### 5.13 Source retrieval provenance

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Export identity | `DatasetContract` and rehearsal artifact | project-controlled export process around native extraction | export envelope, locator, exact bytes | strings/bytes | exporter-captured `retrieved_at` | `ProviderReference`, `SourceArtifactReference` | SHA-256 of exact JSON bytes; content-derived artifact ID | Retrieval time is explicit and never reused as market availability | Hash fixes exact exported content | N/A | `DERIVED_FROM_NATIVE` | In-memory mapping must supply a valid SHA-256; file loader verifies it | HIGH for project transformation | These are not Xuntou-returned native fields; file name alone is not identity, and runtime client/version should be retained in locator or limitations |

### 5.14 Availability and finality semantics

| Canonical Evidence | Canonical Consumer | Xuntou Native API / Source | Xuntou Native Field | Native Data Type | Native Timestamp / Date Field | Canonical Field | Transformation | Availability Semantics | Finality Semantics | Historical PIT Status | Direct / Derived / Unavailable | Fallback Policy | Confidence | Limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Observation time | all consumers | native data row normalized by the exporter | `time` / requested date | explicit date string or aware ISO-8601 datetime | native market timestamp | `session_date`, `decision_time`, `as_of` | Accept `YYYYMMDD` / `YYYY-MM-DD` for date-only rows and timezone-aware ISO-8601 for intraday rows | Does not itself prove availability | Does not itself prove finality | Dated observation only | `DIRECT_NATIVE` after explicit export normalization | Reject numeric epoch and timezone ambiguity | MEDIUM/HIGH | Official numeric epoch unit/timezone semantics are not established; the adapter never guesses milliseconds or UTC and requires the exporter to normalize them |
| Availability time | PIT consumers | normalized export metadata | `available_at` | aware ISO datetime | separate field | `AvailabilityTime` | Strict parse, no inference | First usable time asserted by exporter | independent | Unverified until runtime acquisition is audited | `UNVERIFIED` | Missing -> `None` where allowed or error where canonical contract requires it | MEDIUM | Historical timestamp existence is not proof of historical availability |
| Retrieval time | provenance | project export envelope | `retrieved_at` | aware ISO datetime | separate field | source artifact retrieval | Strict parse | When the export was obtained | N/A | Not historical availability | `UNVERIFIED` provider semantic / explicit project metadata | Required | HIGH for export record | Not returned by the native market-data row; never copy to `available_at` |
| Finalization time/state | bars | export metadata | `finalized`, `available_at` | bool/datetime | separate fields | canonical finalized/availability | Require explicit true for used bars | After data producer says bar complete | explicit exporter assertion | Unverified until runtime audited | `UNVERIFIED` | Non-final rows rejected | MEDIUM | Provider correction/revision policy is not established by reviewed documentation |

## 6. Normalized native export contract

The P0 adapter accepts a JSON-compatible mapping with schema
`xuntou-p0-native-bundle-v3`. It preserves official native field names where they are mapped and
adds explicit metadata that the native API does not carry:

```text
schema_version
source_artifact { retrieved_at, optional content_hash, locator }
conventions { all versioned convention values, including st_interval }
calendar { market=SH|SZ, trade_dates as YYYYMMDD or YYYY-MM-DD strings }
securities [ stock_code, instrument_type, OpenDate ]
universe { historical_pit_status, records[] }
daily_bars [ stock_code, time as YYYYMMDD or YYYY-MM-DD, open, high, low, close, volume, amount,
             preClose, suspendFlag, available_at, finalized ]
minute_bars [ same native K-line fields, with time normalized to timezone-aware ISO-8601,
              plus available_at and finalized ]
st_history [ stock_code, lookup_complete, available_at, periods{ST,*ST,PT} ]
limit_prices [ stock_code, time, 涨停价, 跌停价, available_at, limit_regime ]
decision_times [ timezone-aware ISO-8601 values fixed at 14:55 Asia/Shanghai ]
limitations [ explicit strings ]
```

`instrument_type` is normalized export metadata, not presented as a native field. P0 accepts only
`A_SHARE_STOCK`; it explicitly rejects `ETF`, `INDEX`, `BOND`, `OPTION`, `FUTURE`, and unknown
types. `historical_pit_status` may document the producer's claim, but P0 still forces the canonical
PIT flag false until an independent scope audit exists.

File-mode ingestion computes SHA-256 over the exact bytes; `content_hash` may be omitted from the
file to avoid a self-referential hash. If present, it is treated as a detached expected value and
must equal the computed hash. In-memory mode requires a declared 64-character lowercase SHA-256
because no byte representation is available to recompute. Calendar and Universe source Dataset
identities are derived from that source hash rather than accepted as unverified caller labels.

## 7. Explicit limitations and auxiliary-source role

- `CURRENT_MEMBERSHIP_BACKFILL_BIAS`: full A-share daily historical membership is not established.
- `XUNTOU_HISTORICAL_PIT_UNVERIFIED`: source correction history and historical availability have
  not been audited in a real provider environment.
- `XUNTOU_1M_BAR_LABEL_SEMANTICS_UNVERIFIED`: exact minute label/open-close semantics are not
  stated strongly enough for an exact-snapshot claim.
- `XUNTOU_EXPORT_AVAILABILITY_ASSERTION_UNVERIFIED`: exporter `available_at` assertions require a
  real acquisition audit.
- `XUNTOU_LIMIT_REGIME_IDENTITY_UNVERIFIED`: limit prices can be direct, but the complete rule
  regime identity is not supplied by the reviewed P0 API.
- `XUNTOU_DECISION_BUYABILITY_UNVERIFIED`: historical minute price, suspension and limit values do
  not establish sealed-limit, ask-liquidity, queue, or affirmative `BUYABLE` evidence.
- `XUNTOU_NATIVE_TIME_EPOCH_SEMANTICS_UNVERIFIED`: official documentation does not establish a
  timezone-aware numeric epoch contract; P0 rejects numeric epochs and requires explicit exporter
  normalization.
- `XUNTOU_BJ_CALENDAR_SUPPORT_UNVERIFIED`: official P0 calendar evidence is clear for SH/SZ but not
  for a BJ calendar contract; the adapter accepts only an explicit SH or SZ calendar export.
- Historical ST and limit-price datasets may require Xuntou Research/VIP permissions and explicit
  downloads. Missing access produces `None`/`UNKNOWN`, never `False` or a formula-derived limit.
- Potential auxiliary sources such as Eastmoney or Tencent may later fill explicitly identified
  gaps. No auxiliary adapter or silent fallback is implemented in WP-2.
- Provider-side revisions, corporate-action corrections, exceptional session closes, and exact
  runtime availability/finality require a real Xuntou environment and remain `UNVERIFIED`.
- XtQuant runtime extraction is `NOT IMPLEMENTED` in P0. The adapter has no top-level or late
  runtime import of `xtquant`; it consumes an identified export only.

## 8. Authority and stop condition

Artifacts built under this mapping remain `REHEARSAL`, including when all optional native evidence
is present. A real Xuntou provider-backed run, historical PIT verification, availability/finality
audit, and reproducibility review are separate work. This mapping must not be used to claim Alpha,
formal research authority, fillability, or live-trading readiness.
