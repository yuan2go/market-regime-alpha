# Xuntou / XtQuant Provider Documentation Reference

Status: local reference index  
Retrieved: 2026-07-16  
Normative mapping: [Xuntou P0 Native Field Mapping](../../../specs/Xuntou-P0-Native-Field-Mapping.md)

## Purpose

This directory preserves a compact, reviewable index of the provider documentation used by the
Xuntou P0 mapping and WP-3 execution boundary. It intentionally stores summaries and exact response
hashes rather than mirrored web pages. The URLs remain the source of record; the hashes in
`source-manifest.json` identify the exact bytes inspected on the retrieval date.

The evidence hierarchy is:

1. Xuntou's `dict.thinktrader.net` knowledge base is first-party provider evidence.
2. `miniqmt.com` is a supplementary implementation cross-check, not authority over a conflicting
   first-party definition.
3. Project specifications define the conservative canonical transformation. They never promote an
   undocumented provider behavior to a market-data fact.

## Provider and runtime relationship

The first-party quick-start material describes XtQuant as a Python strategy framework derived from
MiniQMT. `xtdata` is its market-data module, and the documented runtime model requires a running
MiniQMT client for the Python module to communicate with the provider environment. The documents do
not establish that Xuntou, ThinkTrader, QMT, MiniQMT and XtQuant are interchangeable names, so the
project keeps provider, product family, client/runtime and Python API identities separate.

XtQuant remains an optional runtime dependency. No package-level import depends on it, and WP-3 can
consume a normalized, content-hashed Xuntou export without XtQuant being installed on the research
machine.

## P0 / WP-3 API inventory

| Evidence need | Documented interface or data family | What is established | What remains unestablished |
|---|---|---|---|
| Historical market data | `download_history_data`, `get_market_data_ex`, `get_local_data` | Historical K-line/tick retrieval, explicit period and adjustment arguments | Provider correction history and per-field availability SLA |
| Trading calendar | `get_trading_calendar`, `get_trading_dates` | Explicit market trading-date sequences | Provider-native historical session-close timestamp and calendar revision semantics |
| Instrument identity | `get_instrument_detail`, `get_instrument_type` | `code.market` examples and explicit stock/index/fund/ETF classification | Historical taxonomy revisions |
| Candidate universe | `get_stock_list_in_sector`; built-in-Python sector membership with a time parameter | Current constituents; a documented route to date-addressed constituents | Complete survivorship-free historical A-share population and as-was-known PIT guarantee |
| Listing date | instrument detail `OpenDate` | Listing-date value and documented sentinels | Historical correction/availability record |
| Historical ST | `download_his_st_data`, `get_his_st_data` | ST, *ST and PT interval evidence | Intraday effective boundary, publication time and revision/PIT guarantee |
| Suspension | K-line `suspendFlag` | Dated bar-level suspension evidence | Exact historical 14:55 trading state and provider finality SLA |
| Previous close | K-line `preClose`; tick `lastClose` | Native previous-close fields | Current instrument metadata as historical evidence is not supported |
| Price limits | historical `stoppricedata`; current `UpStopPrice` / `DownStopPrice` | Explicit historical and current value families | Meaning of zero values and complete special-rule derivation policy |
| OHLCV / amount | K-line `open`, `high`, `low`, `close`, `volume`, `amount` | Native fields for daily and intraday periods | Currency/scale and completed-bar finality SLA beyond the documented field meaning |
| Intraday price | `1m` and `tick` periods | Native timestamped price observations | Exact minute label convention and exchange-exact 14:55 snapshot semantics |
| Current quote | `get_full_tick` | Current full-quote access | Historical Decision-Time buyability or fillability |
| Source provenance | local download/cache/export workflow | Local extraction is supported | Native content hash, retrieval record and canonical artifact identity |

## Period, adjustment and field conventions

The inspected XtData material documents daily, minute and tick periods, including `1d`, `1m`,
`5m` and `tick`. Adjustment is explicit through `dividend_type`, including unadjusted `none` and
forward/backward adjustment variants. The P0 target-side path uses `none`; any future adjusted
feature-side path must have a different identity and must not overwrite raw tradable-price evidence.

The relevant K-line family includes `time`, `open`, `high`, `low`, `close`, `volume`, `amount`,
`preClose` and `suspendFlag`. The supplementary MiniQMT page confirms the same broad field family
and additionally makes the `fill_data` behavior visible. P0 exports require unfilled observations;
forward-filled bars must not manufacture suspension, liquidity or trading-state evidence.

Tick/full-quote material exposes current price and quote-state fields, but it does not define one
historical `BUYABLE` fact. A valid price plus a non-suspension observation is therefore insufficient
to emit canonical `BUYABLE`; incomplete evidence remains `UNKNOWN`.

## Calendar, sector, ST and limit evidence

Trading-date APIs support an explicit historical sequence, but not a provider-native historical
session-close timestamp. The mapping consequently uses a separately versioned A-share close
convention and records it in dataset identity.

Sector APIs support lists and constituents. First-party built-in-Python material documents a time
parameter for historical sector membership, while the exact completeness and revision semantics of
an all-A-share population remain unverified. P0 must keep `pit_correct_for_scope=False` until a real
export and coverage audit establish otherwise.

The stock dictionary documents historical ST intervals and historical price-limit data. Both are
valuable native evidence, but neither page establishes as-was-known availability or provider
revision history. Current ST/name/status and current price limits must never be projected backward.

## WP-3 implications

- Xuntou is the canonical primary provider route and is capped at `REHEARSAL` until the separate PIT,
  chronology, semantic and reproducibility reviews are complete.
- Tencent remains a temporary `EXPLORATORY` training-data route and later an explicit auxiliary.
- `AUTO` may select Tencent only when Xuntou is genuinely unavailable. A present but invalid Xuntou
  bundle fails closed.
- A valid Xuntou artifact with no eligible Candidates is a valid empty research result; it does not
  trigger fallback.
- No reviewed source establishes a universal historical buyability fact. The minimum Xuntou adapter
  may emit `NOT_BUYABLE` for confirmed suspension and otherwise retains `UNKNOWN`.
- Retrieval time, market observation time, availability time and finalization time remain distinct.

## Source-by-source notes

### First-party ThinkTrader knowledge base

- **快速开始** — provider/product/runtime relationship and the role of `xtdata`.
- **XtQuant.XtData 行情模块** — periods, adjustment modes, historical/current market-data access,
  calendar, instrument metadata, sectors and full quote.
- **股票数据** — stock fields, historical ST, suspension observations and historical limit prices.
- **行业概念数据** — sector and constituent return conventions.
- **xtquant版本下载** — official release channel; it does not prove standard cross-platform PyPI
  installation and does not justify adding `xtquant` to `requirements.txt`.
- **行情函数** — built-in-Python data functions, including date-addressed sector-member context.

### Supplementary MiniQMT page

The MiniQMT `xtdata行情模块` page is retained as a useful cross-check for API naming, periods,
adjustments, K-line fields, current full quote, calendar and sector interfaces. It does not override
first-party Xuntou definitions and does not establish historical PIT, availability or finality.

## Related project evidence

- [Official-documentation evidence note](../../../research/R5-Xuntou-P0-Official-Documentation-Evidence.md)
- [Xuntou P0 adapter status](../../../research/R5-Xuntou-P0-Adapter-Status.md)
- [WP-3 provider-routing design](../../../superpowers/specs/2026-07-16-wp3-provider-routing-and-candidate-runs-design.md)

