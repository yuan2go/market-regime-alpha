# Entry Path Target V1

> **Status:** IMPLEMENTED REHEARSAL CONTRACT
> **Schema:** `entry-path-target-v1`
> **Scope:** WP-4A only
> **Authority:** subordinate to the Constitution and current R5 status

## 1. Purpose and Authority Boundary

This specification defines the first categorical path-dependent Entry research Target:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

It measures whether a favorable or adverse return barrier is reached first after a fixed research
start point. It does not define an Entry Gate, Entry Proposal, probability, Position, Portfolio
Decision, order, or Execution result. A materialized Target is future research evidence and cannot
by itself establish buy-point accuracy or Alpha.

## 2. Versioned Target Semantics

V1 fixes the following identity-bearing conventions:

```text
target_start_convention:
  NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1

reference_price_convention:
  DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1

path_ordering_convention:
  DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1

schema_version:
  entry-path-target-v1
```

The Decision Time is exactly `14:55:00 Asia/Shanghai`. The Decision Reference Price is the
existing Decision Snapshot at that time. Path evaluation begins at the next explicit exchange
trading session's open. Daily-bar V1 does not observe and makes no claim about the path from 14:55
through the Decision Date close.

The caller must explicitly identify:

```text
upper_return > 0
lower_return < 0
horizon_sessions > 0
price_adjustment_basis
```

No default barrier size, horizon, or price adjustment is research authority. For reference price
`P`:

```text
upper_price = P * (1 + upper_return)
lower_price = P * (1 + lower_return)
```

Equality counts as a barrier touch.

## 3. Domain Ownership

Future market observations belong to Data:

```text
market_regime_alpha.data.path_evidence
    RehearsalFutureDailyBar
    RehearsalFutureSuspensionEvidence
```

Entry owns only Target semantics and materialization:

```text
market_regime_alpha.strategies.entry
    EntryBarrierSpec
    EntryPathTargetContract
    EntryPathOutcome
    EntryPathObservationStatus
    EntryPathTriggerType
    EntryPathObservation
    EntryPathTargetMaterialization
    materialize_entry_path_target
```

Provider-native fields remain outside Entry. Candidate ranking, Provider Artifact schemas, and
Execution contracts are unchanged.

## 4. Future Path Evidence

`RehearsalFutureDailyBar` carries:

```text
symbol
session_date
open
high
low
close
price_adjustment_basis
available_at
finalized_at
```

It requires timezone-aware semantic times, positive finite OHLC values, and:

```text
low <= open <= high
low <= close <= high
available_at >= finalized_at
```

The materializer additionally validates:

```text
finalized_at >= TradingSession.session_close
available_at <= materialized_at
session_date belongs to the identified Calendar and exact Target horizon
bar price_adjustment_basis == Target price_adjustment_basis
```

`RehearsalFutureSuspensionEvidence` is explicit session evidence, not an inference from a missing
bar. A confirmed suspended session remains one exchange session inside the fixed horizon and has
no tradable price path. A missing bar without explicit confirmed suspension evidence is `MISSING`;
the materializer never fabricates suspension or skips the exchange session.

## 5. Exchange-Session Horizon

The horizon is counted in exchange trading sessions, resolved only by:

```python
TradingCalendarArtifact.resolve_following_session_dates(
    decision_time,
    horizon_sessions,
)
```

The resolver returns the exact requested number of explicit Calendar dates strictly after the
Decision Time's local date. It does not infer weekdays, holidays, or sessions. Insufficient
Calendar coverage raises `LookupError` and fails the entire materialization, including an empty
Candidate Population. It is not `NOT_YET_OBSERVED`.

## 6. Daily Ordering and Outcomes

Each symbol is evaluated chronologically. For each finalized bar:

1. `open >= upper_price` -> `UP_FIRST`, `OPEN_GAP_UP`;
2. `open <= lower_price` -> `DOWN_FIRST`, `OPEN_GAP_DOWN`;
3. otherwise:
   - upper and lower touched -> `AMBIGUOUS`, `INTRADAY_DUAL_TOUCH_UNORDERED`;
   - upper only -> `UP_FIRST`, `INTRADAY_HIGH_ONLY`;
   - lower only -> `DOWN_FIRST`, `INTRADAY_LOW_ONLY`;
   - neither -> continue.

Open has known precedence because it is the session's first bar value. Daily high and low do not
encode their intraday order. A dual touch therefore terminates that symbol immediately as
`AMBIGUOUS`; later sessions cannot resolve the ambiguity.

Complete evaluation of all horizon sessions without a touch yields `TIMEOUT` with
`HORIZON_EXHAUSTED`.

## 7. Status Matrix

The only valid status/outcome combinations are:

```text
AVAILABLE        + UP_FIRST / DOWN_FIRST / TIMEOUT
AMBIGUOUS        + outcome=None
MISSING          + outcome=None
INVALID          + outcome=None
NOT_YET_OBSERVED + outcome=None
```

Per-symbol rules:

- missing Decision Snapshot -> `INVALID`;
- a completed required session without a bar or confirmed suspension -> `MISSING`;
- a missing session stops evaluation before any later evidence;
- missing evidence after an already resolved event cannot alter that event;
- an unresolved session whose close is still in the future -> `NOT_YET_OBSERVED`;
- `TIMEOUT` requires complete bar or confirmed-suspension evidence across the horizon.

The following are structural and fail the entire call:

- duplicate Snapshot, bar, or suspension evidence;
- wrong Decision Time;
- naive semantic datetime;
- insufficient Calendar coverage;
- off-Calendar or outside-horizon evidence;
- future-available evidence;
- finalization before session close;
- conflicting confirmed suspension and daily bar;
- price-adjustment mismatch;
- empty or duplicate source Dataset identities.

## 8. Observation Audit Contract

Every observation retains:

```text
symbol
status
outcome
reference_price
upper_price
lower_price
event_session_date
event_session_index
trigger_type
evaluated_session_dates
first_missing_session_date
reason_code
observed_at
```

`event_session_index` is one-based inside the resolved horizon. Evaluated dates include each bar or
confirmed suspended session actually consumed, including the terminal event or ambiguity date.
The first missing date is retained separately and is not evaluated.

For bar-derived `AVAILABLE` or `AMBIGUOUS`, `observed_at` is exactly that bar's `available_at`, not
its `finalized_at`, retrieval time, or materialization time. For `TIMEOUT`, it is the availability
of the last required bar or suspension evidence. `MISSING` is recorded at the explicit
completeness assertion's `available_at`; `INVALID` remains reserved for a future explicit
unavailable-reference evidence contract; `NOT_YET_OBSERVED` has no `observed_at`.

## 9. Identity

The deterministic Target ID hashes the complete Target semantics:

```text
upper_return
lower_return
horizon_sessions
target_start_convention
reference_price_convention
path_ordering_convention
price_adjustment_basis
schema_version
```

The materialization Artifact ID additionally hashes:

```text
Target ID
source Dataset identities
Trading Calendar Artifact ID
Universe ID
Decision Time
complete sorted Candidate Population and its source Dataset identities
materialized_at
code revision
config hash
complete ordered observations and audit evidence
```

Input tuple order is normalized and cannot alter identity. A result-affecting semantic, source,
Calendar, Population, code, configuration, or observation change must alter identity.

### WP-4A.1 evidence hardening

WP-4A.1 replaces naked Decision Snapshots at this Entry boundary with Data-domain
`RehearsalEntryReferenceEvidence`. Every reference has an explicit adjustment basis, Dataset
identity, availability time, versioned convention, and deterministic evidence ID. The materializer
requires exactly one reference per Candidate Population symbol and fails the complete call for any
duplicate, omission, Population-external symbol, wrong Decision Time, or basis/source mismatch.

Future bars and suspension evidence now also retain an explicit Dataset identity and deterministic
evidence ID. A provider-neutral `RehearsalFuturePathEvidenceCompleteness` assertion supplies an
exact covered Population, source Dataset, availability time, coverage-through watermark, versioned
convention, and one readiness deadline for every Target-horizon session. Readiness does not use a
global default and each deadline is at or after the Calendar close.

For an unresolved session, materialization evaluates in order: session close, session readiness,
coverage watermark, and finally absence of both a daily bar and confirmed suspension. This produces
`HORIZON_NOT_COMPLETE`, `EVIDENCE_NOT_YET_AVAILABLE`,
`EVIDENCE_COVERAGE_NOT_COMPLETE`, or confirmed `FUTURE_DAILY_BAR_MISSING` respectively. It never
declares `MISSING` from session close alone. The completeness evidence must be available by the
materialization as-of time and its Dataset must match every future bar/suspension source.

`EntryBarrierSpec` now requires `-1.0 < lower_return < 0`. `reason_code` is the versioned
`EntryPathReasonCode` enum; only valid status/outcome/trigger/reason combinations construct. The
materialization preserves reference, consumed bar, consumed suspension, and completeness evidence
IDs, and its Artifact ID is sensitive to them. Completeness/readiness changes the availability of a
materialized label, not the label truth function; it therefore belongs to Artifact identity rather
than Target identity.

## 10. Authority and Limitations

WP-4A is a rehearsal contract implementation. It does not establish that any barrier configuration
is useful, calibrated, or profitable. Daily bars cannot order high and low, so dual-touch sessions
remain explicitly ambiguous. V1 excludes the Decision Date's final five minutes and does not use
minute or tick evidence to resolve path ordering.

WP-3 remains pending a real Xuntou provider-backed input. WP-5 must define a research charter and
chronological comparison before Candidate-only and Candidate-plus-Entry timing can be evaluated.
Trading execution remains outside the current version.
