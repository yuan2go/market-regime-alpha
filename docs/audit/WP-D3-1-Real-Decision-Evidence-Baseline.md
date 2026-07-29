# WP-D3.1 Real Decision Evidence Baseline Audit

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound implementation audit before WP-D3.1 production changes
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** WP-D3-Public-Live-Semantic-Closure.md, ../superpowers/specs/2026-07-30-wp-d3-1-real-decision-evidence-design.md, ../superpowers/plans/2026-07-30-wp-d3-1-real-decision-evidence.md
> **Code Evidence:** `main@2ecf4aad5096fa8e978f2b4e73b7630a87415a32`; `src/market_regime_alpha`; `tests`

## 1. Audited baseline

The audit started from the clean, synchronized `main` HEAD
`2ecf4aad5096fa8e978f2b4e73b7630a87415a32`. PR #25 is present through merge
commit `8f10bd8`; the later merge `2ecf4aa` reconciles documentation and removes
local IDE metadata without replacing the WP-D3 implementation.

The focused pre-change suite passed:

```text
tests/application/daily_loop
tests/data/test_public_composite_provider.py
tests/data/test_public_source_stage_artifact.py
tests/data/test_source_manifest_and_quality.py
tests/universe/test_daily_exploratory.py
tests/features/test_daily_pipeline.py
tests/daily_decision
```

No production code had been modified when this audit was written.

## 2. Actual acquisition and orchestration chain

The CLI `scripts/run_exploratory_daily_loop.py::main()` constructs one
`DailyRunCommand`, creates `PublicCompositeLiveProfile` with
`BaoStockHistoryClient` and `TencentCurrentQuoteClient`, and invokes
`DailyLoopRunner.run()`.

For LIVE, `DailyLoopRunner._freeze_source()` enters `SOURCE_ACQUIRING` and calls
`_acquire_live()`. That method:

1. freezes `HISTORY_SOURCE_FROZEN` through
   `_load_or_acquire_live_stage()` and
   `PublicCompositeLiveProfile.acquire_history()`;
2. immediately freezes `DECISION_QUOTE_SOURCE_FROZEN` through the same helper
   and `PublicCompositeLiveProfile.acquire_current()`;
3. composes both batches into `PublicCompositeProviderResult`;
4. adds protocol and Universe-policy evidence;
5. builds an intermediate SourceManifest, evaluates policy eligibility, and
   adds Eligibility-policy evidence;
6. publishes a Source Archive, derives `DailyRunIdentity`, and binds the
   immutable `RunRequestId -> DailyRunId` mapping in SQLite.

Only after that source freeze does `run()` execute quality, Universe,
Feature, B0/B1, Recommendation, Entry and Phase D Artifact publication.

This is a recoverable two-source-stage acquisition inside one command. It is
not yet an operator-controlled History/Status/Quote schedule.

## 3. Current temporal semantics

### BaoStock history

`BaoStockHistoryClient.acquire()` requests prior-session daily rows through
`query_history_k_data_plus` with:

```text
frequency = d
adjustflag = 3
fields include tradestatus and isST
end_date = decision_date - 1 calendar day
```

The raw canonical API response preserves `tradestatus` and `isST`, but the
normalizer currently emits only `PublicBar`. It discards both status columns
as normalized facts. Prior bars intentionally retain:

```text
available_time = None
finality = UNKNOWN
HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
data_eligibility = EXPLORATORY
```

`features/daily_pipeline.py::_daily_bars()` admits those prior-session bars
only under the versioned exploratory policy and does not rewrite the Provider
SourceManifest fact into Formal PIT.

### Tencent Decision Quote

`TencentCurrentQuoteClient.acquire()` preserves the HTTP response bytes.
`event_time` comes from Tencent field 30 through
`parse_tencent_quote_text()` and `_parse_tencent_time()`.
`available_time` and the source payload `retrieved_time` both use the actual
HTTP completion time. The quote `finality` is `PRELIMINARY`.

The current manifest rejects quote event or availability after Decision Time,
but it does not independently reject a Provider field whose source
`retrieved_time` is after Decision Time. The new stage must enforce all three:

```text
event_time <= decision_time
available_time <= decision_time
retrieved_time <= decision_time
```

Tencent normalization always writes `TradingStatus.UNKNOWN`; its response is
not used as qualified trading, ST or listing evidence.

### Protocol time

`build_daily_control_source_evidence()` correctly derives Decision Time from
`DailyRunCommand` under `SourceAuthorityKind.PROTOCOL`. A late operator runtime
does not mutate that protocol time or turn it into a Provider fact.

## 4. Current status authorities

The V2 authority split is:

| Fact | Current authority | Current real LIVE value |
|---|---|---|
| Decision Time | Protocol | complete |
| Universe Membership | Universe Policy | complete |
| Price | Tencent Provider | complete only when event/availability are in-window |
| Trading Status | Tencent Provider placeholder | `UNKNOWN` |
| ST Status | Tencent-linked Provider placeholder | `UNKNOWN` |
| Listing Status | Tencent-linked Provider placeholder | `UNKNOWN` |
| History Window | BaoStock Provider plus explicit exploratory admission policy | degraded but usable when coverage is sufficient |
| Eligibility | Eligibility Policy | ineligible when current Provider status is unknown |

`daily_quality.py` treats V2 Provider status failures as per-symbol findings.
`daily_exploratory.py::_evaluate_daily_policy_inputs()` then excludes the
symbol. It does not convert unknown evidence into eligibility.

## 5. Why real LIVE has no Candidate Population

The real WP-D3 run occurred after 14:55, so all Tencent prices were unavailable
by the protocol Decision Time. Independently, all trading, ST and listing
facts were unknown. Each of the 20 policy decisions therefore became
`INELIGIBLE`. `DailyLoopRunner` then applied
`MINIMUM_CANDIDATE_POPULATION = 5` and published verified `DATA_BLOCKED` with
empty Prediction, Recommendation and Entry collections.

This behavior is fail-closed and must not be weakened.

## 6. Fixture-only facts absent from real LIVE

`tests/application/daily_loop/public_fixture.py::public_v2_fixture()` creates:

```text
provider_id = provider-fixture-security-status
ST_STATUS = NOT_ST
LISTING_STATUS = LISTED
quality = COMPLETE
available_time = 14:54
```

The base Fixture also emits `TradingStatus.TRADING`. Those explicit artificial
facts make all 20 symbols eligible and allow Replay to reach
`OUTCOME_PENDING`. They characterize pipeline behavior; they are not real
Provider evidence and cannot be reused by LIVE.

## 7. Why the CLI cannot freeze a 14:55 quote reliably

The current `run` command downloads approximately 90 calendar days of history
for every symbol before it calls Tencent. The command exposes no stage-level
entry point. An operator cannot prepare history early, separately freeze
security status, or invoke only Tencent inside the 14:55 window. Restart
recovery exists internally, but scheduling and stage verification remain
coupled to the monolithic CLI command.

## 8. Verified public product semantics

The installed BaoStock client and a real API probe returned:

```text
query_history_k_data_plus:
  date, code, tradestatus, isST
query_stock_basic:
  code, code_name, ipoDate, outDate, type, status
```

BaoStock's official knowledge-base definitions state:

```text
tradestatus: 1 normal trading, 0 suspended
isST: 1 ST, 0 not ST
query_stock_basic.status: 1 listed, 0 delisted
```

A real after-close probe for `sh.601919` on 2026-07-29 returned an exact
decision-date row `tradestatus=1,isST=0` and `query_stock_basic.status=1`.
That probe does not prove the same row is available before 14:55. WP-D3.1 may
therefore implement the product and archive its exact response, but real
14:55 qualification remains a runtime acceptance condition.

For a current observation, actual retrieval time may be used as the earliest
demonstrated observation availability time. This is not a claim about the
Provider's historical publication time and remains `EXPLORATORY`. Historical
rows continue to use `available_time=None`.

## 9. Frozen invariants

- `daily_research` V1 files, schemas, IDs, Reader and `ENTER` semantics remain
  untouched.
- SourceManifest V1/V2, source-stage V1/V2 and existing Phase D Readers keep
  their historical routing and identities.
- B0/B1 Features, weights, scores, ranks, percentiles, tie breaks and Target
  remain unchanged.
- `MR1TargetId.NEXT_SESSION_1030_RETURN` remains the unique next-session 10:30
  Target.
- Entry remains `REJECT` or `WAIT_CONFIRMATION`, never `ENTER`.
- all public evidence remains `DataEligibility.EXPLORATORY`.

## 10. Minimal implementation boundary

WP-D3.1 will add:

1. a typed Provider observation for current/prior security status;
2. a BaoStock current security-status client with raw response preservation,
   per-symbol isolation and socket timeout;
3. `SECURITY_STATUS_SOURCE_FROZEN`;
4. source-stage Artifact V3 with complete RunRequest scope;
5. independent Runner/CLI History, Status, Quote and Finalize operations;
6. manifest projection of independently owned Provider status;
7. retrieved-time Decision-window enforcement;
8. three-stage recovery, replay and B0/B1 equivalence evidence.

It will not add a new Universe, Feature, Candidate, Target, model, Entry model,
portfolio, broker, 100–300 pool or Formal PIT claim.

