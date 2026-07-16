# WP-4A Entry Path Target Contracts and Materialization Design

> **Date:** 2026-07-16
> **Status:** APPROVED DESIGN
> **Authority:** Bounded WP-4A design under `AGENTS.md`, the Constitution, and
> `docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md`

## 1. Purpose

WP-4A establishes the first categorical, path-dependent Entry research Target family:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

It makes the practical failure `Candidate -> enter -> adverse barrier first` measurable without
creating an Entry policy or trade action. The result is future Target evidence. It is not a
Candidate score, Entry Proposal, Portfolio Decision, order, or claim that buy-point accuracy has
improved.

## 2. Scope

### In scope

- Entry Target, Outcome, Observation, and Materialization contracts;
- rehearsal-scoped future daily OHLC and suspension evidence in the Data domain;
- a reusable multi-session Trading Calendar resolver;
- a pure daily-OHLC competing-event materializer;
- deterministic Target and artifact identities;
- exhaustive contract/materialization tests;
- a normative Entry Path Target specification and current-status update;
- independent pre-WP-4A repairs for current repository pytest, Ruff, and mypy failures.

### Non-goals

- Candidate contract changes;
- B0/B1 changes;
- WP-3 runner or artifact changes;
- Provider Artifact schema changes;
- an Entry Gate, Entry Proposal, calibrated probability, or Entry model;
- Position State, Exit Target, Portfolio, Execution, or broker integration;
- a real Xuntou run;
- a claim that Candidate, Entry, or Exit accuracy has been validated.

## 3. Ownership and Modules

The Data domain owns future market evidence:

```text
src/market_regime_alpha/data/path_evidence.py
```

It defines:

- `RehearsalFutureDailyBar`;
- `RehearsalFutureSuspensionEvidence`.

The Entry domain owns research Target semantics:

```text
src/market_regime_alpha/strategies/entry/contracts.py
src/market_regime_alpha/strategies/entry/materialization.py
src/market_regime_alpha/strategies/entry/__init__.py
src/market_regime_alpha/strategies/__init__.py
```

It defines:

- `EntryPathOutcome`;
- `EntryPathObservationStatus`;
- `EntryPathTriggerType`;
- `EntryBarrierSpec`;
- `EntryPathTargetContract`;
- `EntryPathObservation`;
- `EntryPathTargetMaterialization`;
- the pure materializer and deterministic identity builders.

Entry never owns provider-native OHLC. Data evidence never owns Target outcome semantics.

## 4. V1 Target Semantics

WP-4A fixes these conventions:

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

The Decision Reference Price is the existing 14:55 Asia/Shanghai snapshot. V1 begins evaluating
the path at the next exchange trading session's open. It explicitly does not observe or make claims
about the five-minute path from 14:55 to the Decision Date close.

The barrier spec requires callers to provide:

```text
lower_return < 0 < upper_return
horizon_sessions > 0
price_adjustment_basis = explicit non-empty versioned string
```

No project-wide default barrier, horizon, or adjustment basis is introduced. Test values are fixture
parameters, not research authority.

For reference price `P`:

```text
upper_price = P * (1 + upper_return)
lower_price = P * (1 + lower_return)
```

All comparisons include equality as a barrier touch.

## 5. Future Data Evidence

`RehearsalFutureDailyBar` contains:

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

Contract validation requires:

- all OHLC values are positive and finite;
- `low <= open <= high`;
- `low <= close <= high`;
- `available_at >= finalized_at`;
- semantic times are timezone-aware through the existing time wrappers.

The materializer additionally requires:

- `finalized_at >= TradingSession.session_close` for the matching session;
- evidence `available_at <= materialized_at`;
- evidence session dates exist in the identified Calendar;
- evidence price adjustment basis matches the Target contract.

`RehearsalFutureSuspensionEvidence` contains symbol, session date, explicit `is_suspended`,
`available_at`, and `finalized_at`. It obeys the same availability/finality and Calendar validation.
A confirmed suspension means no tradable price path occurred in that exchange session, so the
materializer records the session as evaluated without a barrier touch and continues within the fixed
exchange-session horizon. A missing bar without confirmed suspension evidence is `MISSING`; it is
never silently interpreted as suspension or skipped.

## 6. Trading Calendar Resolver

`TradingCalendarArtifact` adds:

```python
resolve_following_session_dates(
    decision_time: DecisionTime,
    count: int,
) -> tuple[date, ...]
```

Rules:

- `count` must be a positive non-boolean integer;
- sessions are strictly after the Decision Time's local calendar date;
- the returned dates are the next `count` explicit exchange trading sessions;
- weekdays and holidays are never inferred;
- insufficient Calendar coverage raises `LookupError` for the entire materialization.

`resolve_next_session_date()` delegates to this resolver with `count=1` so Calendar parsing has one
owner.

## 7. Daily Path Ordering

For each symbol, the materializer processes the resolved exchange sessions in order.

For a finalized daily bar:

1. `open >= upper_price` -> `UP_FIRST`, trigger `OPEN_GAP_UP`;
2. `open <= lower_price` -> `DOWN_FIRST`, trigger `OPEN_GAP_DOWN`;
3. otherwise the open lies between barriers:
   - `high >= upper_price` and `low <= lower_price` -> status `AMBIGUOUS`, trigger
     `INTRADAY_DUAL_TOUCH_UNORDERED`;
   - only the upper barrier is touched -> `UP_FIRST`, trigger `INTRADAY_HIGH_ONLY`;
   - only the lower barrier is touched -> `DOWN_FIRST`, trigger `INTRADAY_LOW_ONLY`;
   - neither is touched -> continue.

Open is evaluated first because daily OHLC identifies it as the first session price. High and low do
not contain intraday ordering. Once `AMBIGUOUS` occurs, evaluation stops for that symbol. Later dates
must never resolve or override the ambiguity.

If all horizon sessions are completely evaluated without a touch, the result is `TIMEOUT` with
trigger `HORIZON_EXHAUSTED`.

## 8. Missing, Pending, and Structural Errors

Observation states are exact:

```text
AVAILABLE        + UP_FIRST / DOWN_FIRST / TIMEOUT
AMBIGUOUS        + outcome=None
MISSING          + outcome=None
INVALID          + outcome=None
NOT_YET_OBSERVED + outcome=None
```

Per-symbol evidence states:

- missing Decision Snapshot -> `INVALID`;
- a required past/completed exchange session lacks both a finalized bar and confirmed suspension
  evidence -> `MISSING`;
- once a missing session occurs before an outcome, later bars are not examined;
- missing sessions after an earlier resolved outcome do not change that outcome;
- if the next unresolved exchange session has not closed as of `materialized_at`, the result is
  `NOT_YET_OBSERVED`;
- `TIMEOUT` requires complete finalized bar or confirmed suspension evidence for every horizon
  session.

The following fail the entire materialization:

- duplicate Decision Snapshot;
- duplicate daily bar for one symbol/session;
- duplicate suspension evidence for one symbol/session;
- wrong 14:55 Asia/Shanghai Decision Time;
- naive datetime, rejected by semantic-time contracts;
- Calendar coverage shorter than the Target horizon;
- evidence for an off-Calendar date;
- evidence outside the exact resolved Target horizon;
- evidence whose `available_at` is after `materialized_at`;
- `finalized_at` before the matching session close;
- bar and confirmed suspension evidence for the same symbol/session;
- price adjustment basis mismatch;
- duplicate or empty source Dataset identities.

These are structural input errors, not symbol-level missing observations.

## 9. Observation Audit Evidence

Every observation preserves:

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

Rules:

- `event_session_index` is one-based within the resolved horizon;
- `evaluated_session_dates` includes each finalized bar or confirmed suspended session actually
  evaluated, including an event or ambiguous session;
- missing sessions are not added to `evaluated_session_dates` and are retained in
  `first_missing_session_date`;
- missing Snapshot observations cannot supply reference/barrier prices, so those three fields are
  `None` only for `INVALID`;
- `observed_at` for a bar-derived outcome or ambiguity is the bar's `available_at`;
- `observed_at` for a suspension-derived `TIMEOUT` is the final required evidence's `available_at`;
- `observed_at` for `MISSING` or `INVALID` is the materialization availability time, because that is
  when the research artifact records the unresolved state;
- `NOT_YET_OBSERVED` has `observed_at=None`;
- retrieval time is never substituted for Target availability.

Stable reason codes distinguish outcome resolution, dual-touch ambiguity, missing future bar,
missing Snapshot, incomplete horizon, and horizon exhaustion.

## 10. Target and Artifact Identity

The Target ID is a deterministic hash of the complete Target semantics:

```text
schema_version
upper_return
lower_return
horizon_sessions
target_start_convention
reference_price_convention
path_ordering_convention
price_adjustment_basis
```

The Target contract stores the exact canonical payload represented by that identity.

The materialization artifact ID additionally includes:

```text
Target ID
source Dataset identities
Trading Calendar artifact ID
Universe ID
Decision Time
complete sorted Population
materialized_at
code revision
config hash
complete ordered observations and audit fields
```

Changing barrier semantics, evidence identity, Calendar, observations, code, or configuration must
change the relevant identity. Input ordering alone must not change identity; inputs are normalized
by symbol/session before evaluation.

## 11. Empty Population

An empty Candidate Population is valid. The materializer still validates the Target, Decision Time,
Calendar coverage, source identities, and supplied evidence structure, then returns an identified
materialization with zero observations. It does not fabricate a Candidate or outcome.

## 12. Public API

The Data package exports only future path evidence contracts. The Entry package exports the Target
contracts, enums, materializer, and stable conventions intended for research consumers. Internal
hashing, indexing, and classification helpers remain private.

No new Entry APIs are exported from Candidate or Research packages.

## 13. Test Matrix

WP-4A tests cover at least:

- next-session open-gap up;
- next-session open-gap down;
- intraday high-only;
- intraday low-only;
- same-bar dual-touch ambiguity and terminal stop;
- complete-horizon timeout;
- missing-before-event;
- missing-after-earlier-event;
- not-yet-observed;
- missing Decision Snapshot;
- duplicate Snapshot/bar/suspension evidence;
- off-Calendar and outside-horizon evidence;
- future-available evidence;
- finalization before session close;
- Calendar coverage failure;
- explicit suspension handling and missing-without-suspension behavior;
- empty Population;
- Target and artifact identity determinism/sensitivity;
- input-order normalization;
- `observed_at` uses evidence availability rather than finalization or retrieval time;
- public API boundaries.

## 14. Pre-WP-4A Repository Quality Repairs

Before WP-4A feature commits, independent commits will:

1. eliminate pytest import-file mismatch by making colliding test directories explicit packages;
2. remove the existing Ruff F401 unused test import;
3. rerun full mypy, repair the six currently reported typing errors in their owning modules, and
   commit those repairs separately from WP-4A.

These repairs do not alter WP-4A Target semantics and are not folded into feature commits.

## 15. Documentation and Status

Add a normative specification:

```text
docs/specs/Entry-Path-Target-V1.md
```

Update `R5-Current-Status.md` to report:

```text
WP-4A Entry Path Target contracts/materializer    IMPLEMENTED / VERIFIED
Entry model                                       NOT IMPLEMENTED
Entry timing accuracy                             NOT VALIDATED
WP-3 real Xuntou run                              STILL PENDING INPUT
Trading execution                                 OUT OF SCOPE
```

WP-4A completion must not close WP-3, claim a provider-backed run, or claim buy-point accuracy.

## 16. Commit Boundaries

The intended sequence is:

1. `chore: fix repository test collection and Ruff baseline`
2. `fix: close current mypy errors`
3. `feat: add future path evidence and calendar horizon resolver`
4. `feat: add Entry path Target contracts`
5. `feat: materialize Entry competing-event targets`
6. `docs: record WP-4A Entry path target status`

The design and implementation plan remain separate documentation commits. Provider, model,
Portfolio, and Execution changes are prohibited in this sequence.
