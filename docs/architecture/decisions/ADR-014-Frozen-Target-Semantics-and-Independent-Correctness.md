# ADR-014: Frozen Target Semantics and Independent Correctness

> **Status:** CURRENT_ARCHITECTURE
> **Implementation State:** ACCEPTED_DESIGN / CODE_NOT_STARTED
> **Authority:** Approved architecture decision for WP-ALPHA-CORRECTNESS-02
> **Owner:** Market Regime Alpha maintainers
> **Decision Date:** 2026-08-26
> **Starting Main:** `1a92ee41b02dd94df9ef4488c59cba55df4674ce`
> **Evidence Ceiling:** `DISCOVERY_ONLY / PIT_INCOMPLETE / FORMAL_OOS=false / PRODUCTION_QUALIFIED=false`

## Context

WP-ALPHA-PROOF-02 is terminal immutable evidence. Its reacquired physical
packages and all 6,548,518 Raw-to-Normalized observations reproduce, but its
Target correctness proof is `CORRECTNESS_FAILED`: 8 of 37,800 persisted
T+1 10:30 Targets have `PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE`.

Owner-backed diagnosis established one concrete semantic defect:

- three affected Decision sessions have no same-session five-minute bar;
- five have a same-session 14:55 placeholder whose OHLC values are absent;
- all eight materialized the previous trading session's suspended Daily close
  as though it were the exact 14:55 Decision reference;
- all eight have a genuinely observed, complete twelve-bar T+1 09:30-10:30
  five-minute path.

The writer and independent checker therefore disagreed about the Decision
reference while the Outcome path itself was complete. The old Experiment,
Target protocol, labels, component owners, physical artifacts, checksums,
correctness Evidence and report remain immutable.

## Decision

Adopt one content-addressed Target semantic specification and bind it into a
new `OutcomeTargetProtocol` revision and a new `ResearchExperimentDefinition`.
The specification is declarative and shared by materialization, independent
checking, report projection and replay. Materialization and checking continue
to reload source owners independently; the checker never treats persisted
Target values as expected values.

The Target result has three independent state dimensions:

1. `decision_reference_status`;
2. `outcome_window_status`;
3. per-derived-metric status, including `checkpoint_return_status`,
   `mfe_status`, `mae_status` and barrier/path diagnostic status.

Each dimension uses the closed vocabulary:

```text
COMPLETE | PARTIAL | UNAVAILABLE | FAILED
```

`PARTIAL` is meaningful for a window or a diagnostic family. It is not a
permitted substitute for an exact point-in-time Decision reference under this
protocol. `FAILED` denotes semantic or integrity conflict, not ordinary data
absence.

For the eight diagnosed rows the required state is:

```text
decision_reference_status = UNAVAILABLE
outcome_window_status      = COMPLETE
checkpoint_return_status   = UNAVAILABLE
mfe_status                 = UNAVAILABLE
mae_status                 = UNAVAILABLE
```

The complete T+1 path and all of its exact source lineage remain persisted even
though reference-dependent metrics cannot be calculated.

## Exact Decision reference rule

The WP-ALPHA-CORRECTNESS-02 Decision reference accepts exactly one source bar
that satisfies every condition below:

- the bar belongs to the same owner-resolved trading session as the Decision;
- its timezone is interpreted as `Asia/Shanghai`;
- `event_end` is exactly `14:55:00` local time;
- its timeframe is `MINUTE_5`;
- its price basis is Raw/unadjusted;
- open, high, low and close are all present, finite and strictly positive;
- `high >= max(open, low, close)` and `low <= min(open, high, close)`;
- the source identity and content hash verify against the Normalized owner;
- it is not a suspended/placeholder observation.

Zero qualifying bars produces `UNAVAILABLE`. More than one conflicting
qualifying bar, an identity/hash conflict, overlapping interval or invalid
price structure produces `FAILED`.

Daily bars, previous-session closes and the most recent available bar are
diagnostic lineage only. They may be retained with reason codes such as
`DIAGNOSTIC_PREVIOUS_SESSION_DAILY_CLOSE_IGNORED` or
`DIAGNOSTIC_LAST_AVAILABLE_BAR_IGNORED`; they never contribute a value to the
Decision reference, Target return, MFE, MAE, estimable population or any
downstream gate.

The semantic specification freezes reason codes rather than free-form text.
The minimum closed set for this revision is:

```text
DECISION_EXACT_1455_BAR_MISSING
DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER
DECISION_EXACT_1455_BAR_SUSPENDED
DECISION_EXACT_1455_PRICE_STRUCTURE_INVALID
DECISION_EXACT_1455_SOURCE_CONFLICT
DIAGNOSTIC_PREVIOUS_SESSION_DAILY_CLOSE_IGNORED
DIAGNOSTIC_LAST_AVAILABLE_BAR_IGNORED
OUTCOME_GRID_COMPLETE
OUTCOME_GRID_PARTIAL
OUTCOME_GRID_EMPTY
OUTCOME_SOURCE_CONFLICT
DERIVED_DECISION_REFERENCE_UNAVAILABLE
DERIVED_OUTCOME_WINDOW_INCOMPLETE
CORPORATE_ACTION_RAW_POLICY_CONFLICT
PRICE_LIMIT_OBSERVED_NOT_FILLABILITY_PROOF
```

Each code has one declared state effect. Diagnostic codes have none.

## Outcome window and derived metrics

The primary Outcome window is the owner-resolved next trading session from
09:30 inclusive through 10:30 inclusive by five-minute event boundaries.
Weekday inference is prohibited.

For the T+1 10:30 Target:

- `COMPLETE` requires the exact twelve Raw five-minute bars from 09:30-09:35
  through 10:25-10:30, with valid prices, unique identities, no overlap and the
  exact expected grid;
- `PARTIAL` requires at least one valid on-grid bar but not the complete grid;
- `UNAVAILABLE` means no valid observed path bar exists;
- `FAILED` means contradictory, duplicate, overlapping, off-grid, adjusted or
  identity-invalid source evidence.

An exact 10:30 checkpoint price may support `checkpoint_return_status=COMPLETE`
when the Decision reference is complete even if earlier path bars make the
window partial. MFE, MAE and full-path barrier diagnostics require both a
complete Decision reference and a complete applicable path. They are not
computed from a truncated path. A same-five-minute-bar barrier ordering may
remain explicitly partial/ambiguous while MFE and MAE remain complete.

Suspension and missing quotes are absence states, not zero returns. Price-limit
bars remain factual path observations and are annotated; they do not imply an
executable fill. Corporate-action or adjustment conflicts fail closed under the
existing Raw-only policy. A non-trading calendar date cannot become a Target
session.

## Domain and serialization shape

The implementation will add a content-addressed semantic specification and a
new Target label schema while retaining v1/v2 readers:

```text
OutcomeTargetProtocol v2
  -> TargetSemanticSpecification
  -> TargetOutcomeLabel v3
       decision_reference
       outcome_window
       derived_metrics
       source_lineage
       diagnostic_lineage
```

`TargetOutcomeLabel v3` permits a missing Decision reference while retaining an
observed checkpoint price and path. Its identity includes the semantic protocol
reference, all status dimensions, source identities/hashes, reason codes and
metric values. Legacy v1/v2 payloads retain their original identities and
legacy interpretation. Replay dispatches by persisted protocol/schema revision
so current code cannot rewrite an old owner under new semantics.

## Independent correctness boundary

The shared specification owns only declared semantics and deterministic state
derivation. Independence is preserved as follows:

```text
Materializer
  -> reload frozen Experiment/Target/Data/Calendar owners
  -> resolve source bars
  -> evaluate shared semantic specification
  -> persist TargetOutcomeLabel v3

Independent checker
  -> reopen exact PostgreSQL owners and physical package bytes
  -> independently select and verify source bars
  -> evaluate the same frozen specification without persisted values
  -> compare statuses, values, time boundaries and lineage
```

Correctness support requires exact agreement for `COMPLETE`, `PARTIAL`,
`UNAVAILABLE` and `FAILED` states. It does not require every row to have an
estimable return.

## Failure-detail Evidence

The prior correctness Evidence intentionally stores a bounded aggregate
projection and cannot be mutated. WP-ALPHA-CORRECTNESS-02 therefore adds one
typed, content-addressed failure-index artifact under the existing Historical
Evidence authority. It is not a second research claim or qualification owner.

The index and every detail have stable IDs, canonical serialization and
SHA-256 identities. Each detail includes:

- Decision session/time, Target session/window and symbol;
- old persisted label/component identities, values and status;
- materializer and checker results for all three state dimensions;
- exact Decision, Outcome and diagnostic source IDs/hashes;
- Raw request, Normalized Dataset, Calendar, Target protocol, Experiment and
  Evidence lineage;
- dataset/normalization revision, semantic revision and code SHA;
- concrete boundary discrepancy and final classification.

A forward-only PostgreSQL migration will store the index owner, ordered source
bindings and append-only detail projections. PostgreSQL remains the lookup and
identity Authority; any Artifact Root file is only an immutable physical
encoding. The new correctness Evidence embeds/references both the predecessor
eight-row index and the post-fix index, and report/replay verify their hashes.

The migration is additive. Fresh installs create the v3 projection and failure
index directly; an upgrade from head 104 adds them without rewriting a legacy
label, owner or hash. There is no destructive down migration. Operational
rollback means deploying the prior reader while leaving the additive tables
dormant; new v3 writes are never recast as v2. Compatibility tests must prove
that prior readers/replay paths ignore the new projection safely and that
current readers reproduce both revisions exactly.

## Call-chain convergence

No new Runtime or Golden runner is introduced:

```text
continuous-research CLI
-> historical runner / historical-phase-ii operator
-> HistoricalPhaseIIResearchService
-> HistoricalDecisionMaterializer / HistoricalAlphaCorrectnessChecker
-> shared Target semantic specification
-> PostgreSQL Target, component, failure-index and Evidence repositories
-> immutable Artifact Root payloads
-> report / replay / downstream fail-closed admission
```

External and Locked OOS read gates remain closed throughout this Work Package.
The new Discovery run may read only the original Discovery decision and Target
sessions. Locked-scope access-event tables must remain empty/false.

## Alternatives considered

### Align the checker to the current materializer

Rejected. It would legitimize a previous-session Daily close as 14:55 and hide
the defect instead of freezing the intended Target.

### Keep two independent semantic kernels

Rejected. Independent owner loading is valuable; duplicate time-window and
availability rules are not. The present failure is direct evidence of rule
drift.

### Treat missing Decision reference as a missing Outcome path

Rejected. It destroys genuinely observed T+1 facts and prevents the required
three-dimensional diagnosis.

### Store only aggregate discrepancy counts or an unowned report file

Rejected. Neither permits row-level replay, stable checksum verification or
owner lineage.

## Consequences and evidence ceiling

This decision changes neither the old Experiment nor its terminal result. It
does not alter factor direction, factor family, Target horizon, Discovery
sessions, Universe, Top-K, costs, thresholds or multiple-testing rules.

Even if the new correctness result is `CORRECTNESS_SUPPORTED`, External is not
automatically admitted. The new Discovery economics and the explanation for
the old positive-versus-current adverse direction must independently support a
Go decision. Negative economics, unexplained sign reversal, failed regression,
evidence-integrity failure or any required tuning produces `NO-GO`.
