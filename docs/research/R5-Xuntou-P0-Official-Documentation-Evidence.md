# R5 Xuntou P0 Official Documentation Evidence

Status: official-documentation evidence note for WP-1 / WP-2
Research date: 2026-07-16
Source policy: Xuntou / ThinkTrader first-party documentation only

## 1. Purpose and evidence rules

This note records what the official Xuntou knowledge base actually establishes for the P0 Candidate-research data path. It is supporting evidence for the normative field-mapping specification; it is not itself a provider contract and does not claim that a real Xuntou export has been acquired.

The labels used below are deliberately strict:

- `CONFIRMED`: the named API, field, parameter or return shape is explicitly documented by Xuntou.
- `CONFIRMED_WITH_LIMIT`: the native capability is documented, but a P0 research semantic such as historical PIT correctness, availability time or finality is not.
- `UNVERIFIED`: an official page hints at the capability, but the exact callable contract or required research semantic is not established.
- `UNKNOWN`: the inspected official pages do not establish the fact.
- `NOT_PROVIDED`: the documented return does not contain the required canonical fact.

An API returning a historical timestamp is not treated as proof that the value was available at that historical time. Retrieval time, observation time, availability time and finalization time remain separate.

## 2. First-party sources inspected

| Official page | Material used |
|---|---|
| [XtQuant quick start](https://dict.thinktrader.net/nativeApi/start_now.html) | XtQuant / MiniQMT relationship, supported Python runtime statement, `xtdata` role |
| [XtQuant.XtData market-data module](https://dict.thinktrader.net/nativeApi/xtdata.html) | code convention, periods, adjustment modes, market-data fields and return shapes, calendar, instrument metadata, current sector list, full quote |
| [Stock data dictionary](https://dict.thinktrader.net/dictionary/stock.html) | stock instrument fields, historical ST API, historical/current market data, daily suspension field, historical price-limit data |
| [Data functions](https://dict.thinktrader.net/innerApi/data_function.html) | built-in-Python `ContextInfo` data functions and historical sector-member time parameter |
| [Function lookup table](https://dict.thinktrader.net/VBA/check_sheet.html) | first-party lookup entry for `ContextInfo.get_stock_list_in_sector(sectorname, timetag)` and suspension helpers |
| [Scenario-based example](https://dict.thinktrader.net/dictionary/scenario_based_example.html) | daily static-data update behavior, historical-contract download, local historical vs server current-day data split |
| [Complete XtData example](https://dict.thinktrader.net/nativeApi/code_examples.html) | historical local data plus subscribed real-time data behavior |
| [Industry / sector data](https://dict.thinktrader.net/dictionary/industry.html) | sector-list and constituent-list return conventions |

No secondary blog, forum post or remembered API name is used as authority here.

The supplied provider pages are also recorded in the local
[Xuntou / XtQuant provider-document reference](../references/providers/xuntou/README.md), with URL,
retrieval date and exact response-byte SHA-256 values in its machine-readable source manifest.
ThinkTrader pages remain first-party evidence. The MiniQMT page is retained only as a supplementary
cross-check and cannot override a conflicting first-party definition.

## 3. Provider and product relationship

The official quick-start page establishes the following limited relationship:

- `XtQuant` is a Python strategy framework derived from Xuntou `MiniQMT`.
- `xtdata` is XtQuant's market-data module.
- The documented runtime model requires starting MiniQMT before running an XtQuant program; the `xtdata` module communicates with MiniQMT, which handles requests and returns results to Python.
- The official knowledge base separately presents QMT tutorials, built-in Python, XtQuant documentation and the data dictionary.

The inspected pages do **not** define `Xuntou`, `ThinkTrader`, `QMT`, `MiniQMT` and `XtQuant` as interchangeable names. A mapping contract should therefore preserve them as distinct provider / product / client / Python-API identities rather than collapse them.

Official evidence: [XtQuant quick start](https://dict.thinktrader.net/nativeApi/start_now.html), [XtData runtime logic](https://dict.thinktrader.net/nativeApi/xtdata.html).

## 4. P0 evidence summary

| P0 evidence group | Official native evidence | Capability status | Historical PIT status | Availability / finality status |
|---|---|---|---|---|
| Trading calendar | `xtdata.get_trading_calendar`; `get_trading_dates` | `CONFIRMED` | historical date sequence is returned; revision/PIT guarantee `UNVERIFIED` | session close and publication time `NOT_PROVIDED` |
| Security identity | `code.market`; `get_instrument_detail`; `get_instrument_type` | `CONFIRMED` | identity fields exist; historical taxonomy revisions `UNVERIFIED` | instrument info is documented as updated at 09:00 each trading day; exact availability SLA `UNKNOWN` |
| Historical universe membership | current sector list; `ContextInfo.get_stock_list_in_sector(..., timetag)`; XtData changelog mentions `real_timetag` | `CONFIRMED_WITH_LIMIT` for ContextInfo, `UNVERIFIED` for exact XtData signature | full historical A-share population and revision correctness `UNVERIFIED` | download/effective time `UNKNOWN` |
| Listing date / age | `get_instrument_detail().OpenDate` | `CONFIRMED` | date value direct; historical correction policy `UNVERIFIED` | listing age is derived; source availability time `UNKNOWN` |
| Historical ST | `download_his_st_data`; `get_his_st_data` returning ST / *ST / PT intervals | `CONFIRMED_WITH_LIMIT` | historical intervals direct; as-was-known PIT/revision guarantee `UNVERIFIED` | async download; publication/finality `UNKNOWN` |
| Historical suspension | K-line `suspendFlag` | `CONFIRMED_WITH_LIMIT` | historical daily observation direct when downloaded with no fill; provider revision guarantee `UNVERIFIED` | intraday 14:55 suspension fact not explicitly provided by this daily field |
| Previous close | K-line `preClose`; tick `lastClose`; current instrument `PreClose` | `CONFIRMED` | daily `preClose` supports historical observation; current metadata is current-only | exact availability/finality `UNKNOWN` |
| Price limits | historical `stoppricedata`; current `UpStopPrice` / `DownStopPrice` | `CONFIRMED_WITH_LIMIT` | historical rows direct but VIP and PIT-revision guarantee `UNVERIFIED` | exact publication/finality `UNKNOWN` |
| Daily OHLCV / amount | `get_market_data_ex`, period `1d`, OHLCV and `amount` | `CONFIRMED` | historical series supported; corrections/PIT `UNVERIFIED` | completed-bar finality window `UNKNOWN` |
| 14:55 reference price | period `1m` or `tick`, price fields and timestamp | `CONFIRMED_WITH_LIMIT` at raw-data level | historical intraday retrieval is supported | minute label convention and exact 14:55 availability/finality `UNVERIFIED` |
| Decision-time buyability | tick `stockStatus`, prices, current instrument status, suspension and limits | `UNVERIFIED` as a single buyability fact | no documented historical `BUYABLE` semantic | fillability and evidence-completeness semantics `NOT_PROVIDED` |
| Liquidity | daily `amount` | `CONFIRMED` as raw input | trailing statistic is derived from historical native rows | amount unit described as turnover amount; currency/PIT/finality details `UNVERIFIED` |
| Next-session OHLC | trading calendar + next daily raw OHLC row | `CONFIRMED` inputs, `DERIVED` join | correct only when next session is resolved from the calendar | available only after the next session completes; provider finality SLA `UNKNOWN` |
| Source retrieval provenance | local download/cache/runtime mechanics | `CONFIRMED_WITH_LIMIT` | native API does not return artifact hash or retrieval record | retrieval timestamp, locator and content hash must be captured by the project export boundary |
| Availability / finality | local history vs subscribed current-day split | `CONFIRMED_WITH_LIMIT` | no general historical as-of guarantee | per-field availability, correction and finalization times mostly `UNKNOWN` |

## 5. Detailed findings

### 5.1 Trading calendar

`xtdata.get_trading_calendar(market, start_time='', end_time='')` is documented to return a complete list of trading-date strings for a market. The examples use markets such as `SH` and values such as `20240109`. `xtdata.get_trading_dates(market, start_time='', end_time='', count=-1)` is separately documented to return a list of timestamps. Downloading holiday data is required for future dates.

Confirmed:

- an explicit historical trading-date sequence is available;
- the date-range parameters are documented;
- the calendar can be market-specific.

Not established:

- the returned timestamp timezone for `get_trading_dates`;
- a provider-native historical session-close timestamp;
- the calendar publication time, revision policy, or finalization time;
- whether SH, SZ and BJ calendars are guaranteed identical for every historical date.

Therefore `TradingSession.trade_date` can be direct native evidence. A `session_close` such as 15:00 Asia/Shanghai must be a separately versioned A-share convention, not described as a Xuntou-returned field. The minimum adapter accepts only an explicit `SH` or `SZ` calendar export; `.BJ` remains valid security-identity evidence, but a BJ calendar contract is not established by the reviewed P0 pages.

Official evidence: [XtData trading calendar and trading dates](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock data dictionary calendar example](https://dict.thinktrader.net/dictionary/stock.html).

### 5.2 Security identity and instrument filtering

XtData documents stock codes in `code.market` form, with examples `000001.SZ`, `600000.SH` and `000300.SH`. Official examples also show `688...SH`, `300...SZ` and `430017.BJ`. `get_instrument_detail` returns `ExchangeID`, `InstrumentID`, `ExchangeCode`, `UniCode`, name, listing/expiry dates and other fields. `get_instrument_type` returns booleans for categories including `stock`, `index`, `fund` and `etf`.

Confirmed:

- the native symbol can be preserved as the canonical `code.market` string;
- `.SH`, `.SZ` and `.BJ` market codes appear in official material;
- `get_instrument_type` provides an explicit way to exclude index/fund/ETF instruments from an A-share stock population.

Not established:

- a single official field that directly names Main Board, STAR Market or ChiNext;
- a stable official rule in the inspected pages for inferring board identity solely from numeric prefixes;
- a complete enumeration for every security category across client versions.

P0 should require the explicit native `stock` type plus the allowed A-share markets, and should reject or preserve as unsupported all other instrument types. Numeric prefix filtering alone is insufficient official evidence.

Official evidence: [XtData common types and instrument type](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock instrument dictionary](https://dict.thinktrader.net/dictionary/stock.html).

### 5.3 Historical A-share universe membership

The stock dictionary documents `xtdata.get_stock_list_in_sector("沪深A股")` as returning a stock-code list. The scenario example uses `沪深京A股`, and the XtData changelog says the sector-list API added a Beijing Stock Exchange sector and later a `real_timetag` parameter. Separately, the official function lookup documents built-in Python `ContextInfo.get_stock_list_in_sector(sectorname, timetag)`: omitting `timetag` returns the latest constituents, while providing a date/timestamp requests historical constituents.

This is useful evidence, but not enough to claim a verified historical PIT all-A-share universe:

- the current XtData function reference still shows only `get_stock_list_in_sector(sector_name)` and does not specify the exact current `real_timetag` call signature or return behavior;
- the ContextInfo function documents historical sector membership, but the inspected page does not guarantee historical completeness, handling of delisted names, revision policy, or as-of availability;
- `download_history_contracts()` is documented to add retired/delisted instrument information, but combining listing/expiry dates with current membership is a reconstruction, not a documented historical universe snapshot;
- sector data is documented as static data that should be downloaded daily, which shows retrieval workflow but not effective-time/PIT guarantees.

Conservative conclusion: a dated native membership export may be retained and materialized, but `pit_correct_for_scope=True` is not supported by the inspected official evidence alone. A current-list backfill must be labelled current-membership backfill bias.

Official evidence: [Stock sector list](https://dict.thinktrader.net/dictionary/stock.html), [XtData changelog and sector API](https://dict.thinktrader.net/nativeApi/xtdata.html), [ContextInfo function lookup](https://dict.thinktrader.net/VBA/check_sheet.html), [Scenario data preparation](https://dict.thinktrader.net/dictionary/scenario_based_example.html).

### 5.4 Listing date and listing age

For stocks, `get_instrument_detail().OpenDate` is documented as the IPO/listing date. The documented type is string in XtData, although examples and older built-in APIs may show an integer. Special sentinel values `19700101` through `19700106` are assigned other event meanings, and `ExpireDate` values `0` and `99999999` mean no current delisting/expiry date.

Consequences:

- a valid eight-digit `OpenDate` outside the documented sentinel set is direct native listing-date evidence;
- `listing_age_calendar_days` is derived as decision date minus listing date;
- sentinel, missing or malformed values must not become an invented old listing date;
- official documentation does not establish correction history or original availability time, so source PIT semantics remain unverified even though the date itself is historical.

Official evidence: [Stock instrument-detail fields and sentinel values](https://dict.thinktrader.net/dictionary/stock.html), [XtData instrument detail](https://dict.thinktrader.net/nativeApi/xtdata.html).

### 5.5 Historical ST state

The stock dictionary explicitly documents:

- `xtdata.download_his_st_data()` to download market historical ST data;
- `xtdata.get_his_st_data(stock_code)` to return a dictionary keyed by `ST`, `*ST` and `PT`;
- each key maps to date intervals; a historically never-ST security returns an empty dictionary;
- the data requires VIP permission and the download call is asynchronous.

Thus historical ST intervals are a real native capability and should not be reported as wholly unavailable. However, the official page does not define:

- whether interval endpoints are inclusive or exclusive;
- the intraday effective time of a change;
- the data's historical publication/availability time;
- revision/correction policy or an as-was-known-at-decision-time guarantee;
- how to distinguish “never ST” from incomplete/missing download solely from an empty result.

P0 classification should therefore be `DIRECT_NATIVE` for the returned interval evidence and `UNVERIFIED` for historical PIT/availability. Empty native results require export-completeness evidence before they may be converted to `is_st=False`; otherwise canonical `None` / `UNKNOWN` is safer.

Official evidence: [Stock historical ST section](https://dict.thinktrader.net/dictionary/stock.html).

### 5.6 Suspension and trading status

The official K-line field list includes `suspendFlag`, documented as `0` normal, `1` suspended and `-1` resumed that day. The stock dictionary's built-in-Python field table gives the simpler `1` suspended / `0` not suspended description. Current instrument detail also exposes `InstrumentStatus` and `IsTrading`; the stock dictionary describes `InstrumentStatus <= 0` as normal/resumed and `>= 1` as suspended days.

For historical daily eligibility, the daily K-line `suspendFlag` is the relevant dated evidence. Current `InstrumentStatus` / `IsTrading` must not be projected backward. Because the official tables are inconsistent about whether `-1` belongs to the enumeration, an export using that value must retain its runtime/client build identity. Because `get_market_data_ex` supports `fill_data`, suspension evidence should be exported without forward-filled values; otherwise a filled bar could be mistaken for a native observation.

Unverified:

- historical intraday trading status specifically at 14:55;
- status-code details for tick `stockStatus`;
- availability, correction and finality times;
- whether a daily `-1` resumed flag proves continuous tradability at 14:55.

Official evidence: [XtData K-line fields](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock market-data and instrument-status fields](https://dict.thinktrader.net/dictionary/stock.html).

### 5.7 Previous close and price limits

Three different contexts are documented:

- historical K-lines include `preClose`;
- tick/full-quote data include `lastClose`;
- current instrument detail includes `PreClose`, `UpStopPrice` and `DownStopPrice`.

For historical price limits, Xuntou documents VIP period `stoppricedata`, downloaded with `download_history_data` and read with `get_market_data_ex`. Its example returns per-symbol DataFrames with `time`, `涨停价` and `跌停价`. This is preferable to reconstructing limits with a fixed multiplier.

Limits:

- current `UpStopPrice` / `DownStopPrice` are only documented as the current day's values;
- historical `stoppricedata` is documented, but its publication time, revision policy and row-finality semantics are not;
- zero values appear in the official historical example, but the page does not define whether zero means no limit, unavailable, not applicable or bad data;
- no inspected page provides a complete versioned derivation policy for board/ST/IPO special rules.

Therefore missing or zero historical price limits must not be replaced with `prev_close * 1.10` or another convenience rule.

Official evidence: [Stock historical limit-price data](https://dict.thinktrader.net/dictionary/stock.html), [XtData instrument and K-line fields](https://dict.thinktrader.net/nativeApi/xtdata.html).

### 5.8 Historical daily OHLCV and amount

`xtdata.get_market_data_ex` is documented for periods including `1d`, `1m`, `5m` and `tick`. The stock dictionary describes its return as `{stock_code: DataFrame}`; K-line fields include `time`, `open`, `high`, `low`, `close`, `volume`, `amount`, `preClose` and `suspendFlag`. Historical data is downloaded to local storage; real-time data is obtained via subscription, and the APIs can combine the two.

Adjustment is explicit through `dividend_type`:

- `none`: unadjusted;
- `front`: forward adjusted;
- `back`: backward adjusted;
- `front_ratio`: ratio forward adjusted;
- `back_ratio`: ratio backward adjusted.

For target-side tradable prices, `dividend_type='none'` is the only directly documented unadjusted choice. Any feature-side adjustment must carry its own identity and must not silently overwrite target-side raw prices. `fill_data=False` is the conservative export choice where an actual observation is required.

The official documentation does not establish historical correction/version policy, exact currency metadata for `amount`, or the timestamp at which a completed daily bar becomes final.

Official evidence: [XtData periods, adjustment modes and fields](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock historical market-data section](https://dict.thinktrader.net/dictionary/stock.html).

### 5.9 Historical 14:55 observation

The official API supports historical `1m` and `tick` data with time-range strings in `YYYYMMDDhhmmss` form. A 1-minute K-line contains OHLCV/amount fields; tick contains `time`, `stime` and `lastPrice`. This establishes possible raw evidence sources for a 14:55 research observation.

It does **not** establish the semantic needed to call a row an exact 14:55 exchange snapshot:

- the official field tables call `time` a timestamp but do not say whether a 1-minute bar label is bar-open time or bar-close time;
- the interval covered by a row labelled `14:55` is not defined;
- the exact arrival/availability time of that row is not defined;
- a tick selected before/at 14:55 would be a last-observation convention, not an exchange snapshot unless separately evidenced;
- historical corrections and bar finalization are not specified.

Accordingly, P0 must name and version its own reference-price convention. The v3 mapping bounds staleness by accepting only completed observation labels inside `[14:54:00, 14:55:00]` Asia/Shanghai that the exporter declares available by the Decision Time. This freshness window does not resolve the native bar-open/bar-close ambiguity and does not turn the row into an exact 14:55:00 exchange snapshot. An older same-day row or an export that cannot preserve an aware timestamp remains ambiguous/unsupported.

Official evidence: [XtData periods and range semantics](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock market-data fields](https://dict.thinktrader.net/dictionary/stock.html).

### 5.10 Real-time / full-quote evidence and buyability

XtData documents:

- `subscribe_quote` for a single instrument and period;
- `subscribe_whole_quote` for whole-market or selected-instrument tick pushes;
- `get_full_tick` returning the latest full-quote slice;
- full/tick fields including timestamp, latest price, OHLC-so-far, previous close, cumulative amount/volume, `stockStatus` and bid/ask arrays.

The official pages do not define a canonical decision-time `BUYABLE` field. `IsTrading`, `InstrumentStatus`, `suspendFlag`, `stockStatus`, reference price and price limits are pieces of evidence, not proof of fillability. In particular:

- not suspended does not prove a buy order could execute;
- a last/reference price equal to the historical upper-limit price does not prove `NOT_BUYABLE`; without dated ask-side, sealed-limit or queue evidence, the official fields do not establish whether a buy order could enter or fill;
- the exact `stockStatus` enumeration for A-share buyability is not documented in the inspected field table;
- historical full-quote availability at exactly 14:55 is not guaranteed.

Therefore a P0 adapter can only emit `BUYABLE` when an explicitly versioned rule has complete decision-time native evidence; otherwise `UNKNOWN` is the truthful result. Fillability remains out of scope.

Official evidence: [XtData subscription and full-quote APIs](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock data dictionary](https://dict.thinktrader.net/dictionary/stock.html).

### 5.11 Liquidity

Daily `amount` is a confirmed native field. A trailing measure such as a 20-session median amount is therefore `DERIVED_FROM_NATIVE`, computed from dated daily rows, not a provider-returned scalar.

The computation identity must specify:

- `dividend_type='none'` (adjustment does not logically apply to amount, but the request contract should still be explicit);
- `fill_data=False`;
- lookback length in trading sessions;
- statistic (median versus mean);
- missing-row policy;
- whether the decision day is included and, if so, whether its value was complete at decision time.

The official pages label `amount` as turnover amount but do not provide a formal field currency/scale contract or historical finality guarantee in the inspected sections. P0 should preserve provider units and require the export contract to assert CNY only when verified in the actual runtime/export environment.

Official evidence: [XtData K-line fields](https://dict.thinktrader.net/nativeApi/xtdata.html), [Stock market-data fields](https://dict.thinktrader.net/dictionary/stock.html).

### 5.12 Next-session OHLC

The inputs are documented: the calendar supplies ordered trading dates and the daily K-line supplies `open`, `high`, `low`, `close`. The next-session bar is therefore produced by resolving the next calendar session and selecting that date's unadjusted daily row. It must not use calendar-day `decision_date + 1`.

Availability is necessarily later than the decision observation: a next-session OHLC bar cannot be treated as known at 14:55 on the decision date. The official docs do not state an exact post-close finalization or correction SLA, so `available_at` must come from the export convention/provenance rather than an invented provider timestamp.

Official evidence: [XtData trading calendar and market-data fields](https://dict.thinktrader.net/nativeApi/xtdata.html).

### 5.13 Source retrieval provenance and runtime limitations

Official documentation establishes that historical Level-1 data is downloaded into local storage/cache, current-day data comes from subscription/server paths, and `xtdata` interacts with MiniQMT. It does not return a content hash, immutable artifact ID, source locator or retrieval timestamp as part of each market-data row.

Those provenance fields must therefore be captured by the project-controlled export boundary:

- provider/product and mapping-contract versions;
- runtime/client identity when available;
- retrieval timestamp;
- export locator;
- byte-derived content hash;
- request parameters, including symbols, periods, time range, adjustment and fill policy;
- limitations and completeness declarations.

The official quick start says XtQuant is supplied for particular 64-bit Python versions and requires MiniQMT to be started. This supports an optional runtime boundary rather than a hard import-time dependency in a cross-platform research package. This research did not execute XtQuant and does not establish the locally installed package/version or access permissions.

Official evidence: [XtQuant quick start](https://dict.thinktrader.net/nativeApi/start_now.html), [XtData runtime logic](https://dict.thinktrader.net/nativeApi/xtdata.html), [Scenario data preparation](https://dict.thinktrader.net/dictionary/scenario_based_example.html).

## 6. Availability and finality conclusions

The first-party documentation supports only a limited availability model:

1. historical Level-1 data must be downloaded and is read from local storage/cache;
2. current-day / real-time data is obtained by subscription/server paths;
3. the APIs may concatenate local historical data and subscribed real-time data;
4. sector/classification data is static-ish and should be refreshed daily;
5. instrument information is documented as updating at 09:00 each trading day;
6. historical ST download is asynchronous.

The following are **not established** across the inspected pages:

- per-field historical first-availability timestamps;
- exchange observation time versus provider ingestion time;
- bar-close publication latency;
- correction windows and finalization time;
- immutable historical snapshots or vintage identifiers;
- proof that data retrieved in 2026 was identical to what a strategy could retrieve at the historical decision time;
- timezone for every numeric timestamp;
- exact 1-minute bar timestamp-label convention.

Consequently, a native timestamp may populate observation time only after the exporter makes its date/time interpretation explicit, while retrieval time must come from the export process. The v3 normalized boundary accepts date-only `YYYYMMDD` / `YYYY-MM-DD` strings and timezone-aware ISO-8601 intraday values; it rejects numeric epoch guessing because the inspected pages do not establish a timezone-aware epoch contract. Availability and finalization fields must be explicit conventions or remain unknown; they must never be copied from retrieval time or invented from observation time.

For a completed daily bar, a project convention may conservatively require `available_at` not earlier than the versioned 15:00 Asia/Shanghai session close. That lower bound is derived from the project's A-share session-close convention; it is not a provider-native publication timestamp and does not prove Xuntou correction/finality semantics. A daily row whose asserted `available_at` precedes that boundary cannot be treated as finalized evidence.

## 7. Minimum conservative P0 use of official capabilities

The official evidence supports the following narrow extraction plan, subject to real-environment verification:

- calendar: `get_trading_calendar` date strings;
- identity/type: `get_instrument_detail` plus `get_instrument_type`;
- dated membership: export a native dated membership observation when the runtime API and completeness are demonstrated, otherwise mark current-only/backfilled;
- listing date: valid non-sentinel `OpenDate`;
- ST: downloaded `get_his_st_data` intervals, while preserving completeness and PIT limitations;
- suspension, previous close, daily prices and liquidity input: unfilled, unadjusted daily K-line fields;
- historical price limits: `stoppricedata` when permission/data are present, otherwise unknown;
- decision reference: a separately versioned 1-minute/tick selection convention whose label semantics are declared by the export;
- next-session target bar: next trading date plus unadjusted daily OHLC;
- buyability: unknown whenever decision-time evidence is incomplete;
- provenance: project-generated hash, retrieval record and request identity around the native export.

## 8. Explicitly unresolved official-documentation questions

The following must remain `UNKNOWN` / `UNVERIFIED` until a stronger first-party contract or real-runtime evidence is captured:

- exact XtData `get_stock_list_in_sector` historical `real_timetag` signature and completeness in the target installed version;
- a provider-documented BJ trading-calendar contract equivalent to the confirmed SH/SZ P0 path;
- historical all-A-share universe membership including delisted names, with PIT/revision guarantees;
- 1-minute bar open-time versus close-time labels;
- interval endpoint convention and change effective time for historical ST ranges;
- meaning of zero rows in `stoppricedata`;
- detailed A-share `stockStatus` enumeration and a provider-defined buyability semantic;
- amount currency/scale guarantee across target client editions;
- provider publication/finality/correction SLA for daily, minute, tick, calendar, ST, suspension and limit-price data;
- immutable vintage/version identifiers for historical data;
- exact installed XtQuant/MiniQMT versions and permissions in the future provider environment.
- numeric `time` epoch unit/timezone semantics across the exact installed runtime version.

These gaps do not prevent a truthful `REHEARSAL` export adapter. They do prevent promotion to verified historical PIT or `FORMAL_RESEARCH` authority.

## 9. Execution statement

No XtQuant runtime extraction was executed during this documentation research. No provider-backed data artifact was acquired. Tests and quality commands were not run, in accordance with the task instruction.
