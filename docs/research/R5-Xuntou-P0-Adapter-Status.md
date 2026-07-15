# R5 Xuntou P0 Adapter Status

> **Status:** CURRENT
> **Mapping contract:** `xuntou-p0-native-field-mapping-v1`
> **Native bundle schema:** `xuntou-p0-native-bundle-v1`
> **Implementation revision:** `c747ca3`
> **Maximum authority:** `REHEARSAL`

## Purpose

This document records what the Xuntou P0 adapter implements now. The normative interpretation of
each native field remains in
`docs/specs/Xuntou-P0-Native-Field-Mapping.md`.

The implementation translates an identified normalized Xuntou export into the existing provider
rehearsal artifact. It does not call XtQuant, place orders, build a Candidate model, or establish a
real provider-backed research result.

## Current implementation state

```text
Xuntou P0 native field mapping specification     COMPLETE
Runtime semantic verification                    PARTIAL
Normalized Xuntou export adapter                 IMPLEMENTED
Existing canonical artifact construction         IMPLEMENTED
Public research-package API                      IMPLEMENTED
XtQuant runtime extraction                       NOT IMPLEMENTED / NOT EXECUTED
Real Xuntou provider-backed run                  NOT AVAILABLE
Formal-research authority                         NOT AVAILABLE
```

## Implemented native evidence

- Explicit SH/SZ/BJ `code.market` symbol validation and A-share-stock filtering.
- Trading dates from the normalized result of the official calendar API.
- Native daily and 1-minute K-line fields: `time`, OHLC, `volume`, `amount`, `preClose`, and
  `suspendFlag`.
- Historical ST interval payloads from `get_his_st_data` when the exporter confirms lookup
  completeness.
- Historical `stoppricedata` rows with `涨停价` and `跌停价` when the entitled dataset is present.
- `OpenDate` listing evidence with documented sentinel dates treated as missing.
- Exact source retrieval provenance: provider/product contract, retrieved time, locator, SHA-256,
  and content-derived Artifact/Dataset identities.

Unsupported instrument types are filtered before Universe, bars, snapshots, targets, or
eligibility evidence are materialized. The adapter does not infer instrument type from a numeric
code prefix.

## Derived evidence

- Session close is derived from a versioned 15:00 Asia/Shanghai A-share convention.
- Listing age is a calendar-day difference only when listing evidence has an explicit availability
  time no later than the Decision Time.
- Historical ST state is materialized from ST/*ST/PT intervals only when lookup completeness and
  availability permit it.
- Suspension maps from native `suspendFlag`; missing/unsupported values remain `None`.
- The 14:55 reference price is the latest completed raw 1-minute close explicitly available no
  later than 14:55, not an asserted exchange exact snapshot.
- Eligibility liquidity is the median amount of exactly 20 prior finalized sessions available by
  the Decision Time. This evidence is materialized separately from predictive Features.
- Candidate-population buyability is `UNKNOWN` unless complete evidence is declared. Known
  suspension or a reference price at/above the direct historical limit-up price is
  `NOT_BUYABLE`. `BUYABLE` is not fillability.
- Next-session OHLC uses only `TradingCalendarArtifact.resolve_next_session_date()`.

## Unverified and unavailable evidence

- Full historical A-share membership completeness and survivorship-free PIT semantics are not
  established. The adapter always emits `pit_correct_for_scope=False`.
- Current sector membership is not backfilled into historical dates.
- `get_instrument_detail` current fields are not used as historical status, previous close, or
  historical limit-price evidence.
- Historical availability, provider revision policy, bar correction history, and exact minute-bar
  label semantics have not been audited in a real Xuntou runtime.
- The complete historical price-limit regime identity is not supplied by P0. Limit prices can be
  direct while `limit_regime` remains missing and Eligibility remains `UNKNOWN`.
- Missing ST access does not become `is_st=False`; missing suspension does not become
  `is_suspended=False`; missing limit prices are not derived from `prev_close`; missing buyability
  does not become `BUYABLE`.
- Eastmoney and Tencent remain potential explicit auxiliary sources. No auxiliary adapter or
  fallback was implemented.

## Canonical mapping

One sufficiently complete P0 bundle can construct:

```text
ProviderReference
SourceArtifactReference
TradingCalendarArtifact
HistoricalPITUniverseArtifact shape with unverified PIT authority
RehearsalDailyBar
RehearsalDecisionSnapshot
RehearsalNextSessionBar
RawTradingEligibilityObservation
ProviderRehearsalMarketArtifact
```

All output remains `DataEligibility.REHEARSAL`. The Xuntou adapter changes no canonical contract and
adds no provider fields to Candidate ranking, Entry, Lifecycle, Portfolio, or Execution owners.

## Runtime requirements

The repository has no mandatory `xtquant` dependency and the adapter has no import-time XtQuant
import. A separate authorized provider environment must:

1. run a compatible ThinkTrader/MiniQMT/XtQuant setup;
2. download the required calendar, native bars, ST history, and limit-price data according to
   entitlement;
3. export the documented normalized native bundle with aware availability/retrieval times and
   explicit finality;
4. retain the exact file bytes and SHA-256;
5. transfer the identified export to the research environment.

## Known limitations

The canonical Dataset limitations always include:

```text
CURRENT_MEMBERSHIP_BACKFILL_BIAS
XUNTOU_HISTORICAL_PIT_UNVERIFIED
XUNTOU_1M_BAR_LABEL_SEMANTICS_UNVERIFIED
XUNTOU_EXPORT_AVAILABILITY_ASSERTION_UNVERIFIED
XUNTOU_LIMIT_REGIME_IDENTITY_UNVERIFIED
XUNTOU_RUNTIME_EXTRACTION_NOT_EXECUTED
```

Missing optional ST or limit-price sections add corresponding evidence-not-present limitations.
The adapter fails explicitly when required schema, time-zone, finalized bar, Decision snapshot, or
next-session evidence cannot support even the bounded rehearsal artifact.

## Verification status

No tests or static quality commands were executed for WP-1/WP-2 because the task explicitly
prohibited `pytest`, `ruff`, `mypy`, CI, and test-file changes. No passing result is claimed.

The implementation was reviewed by reading the diff and checking these architecture conditions:

- no current data is promoted to historical PIT;
- no retrieval time is copied into availability time;
- no missing value is converted to false, zero, or a convenient limit formula;
- no import-time XtQuant dependency exists;
- no canonical contract or B0/B1 model semantics changed;
- no authority above `REHEARSAL` is emitted.

## Current authority and next data-acquisition step

The current authority is an architecture-coherent native-export boundary, not a provider-backed
experiment. The next work package is WP-3: acquire one real, content-hashed Xuntou P0 export in an
authorized runtime and run a bounded REHEARSAL Candidate artifact chain. WP-3 must preserve all
limitations and cannot claim Alpha or formal-research authority merely because the source is
Xuntou.
