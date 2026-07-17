# WP-4A.1 Entry Path Temporal and Price-Lineage Hardening Design

> **Date:** 2026-07-18  
> **Status:** APPROVED DESIGN  
> **Authority:** Bounded WP-4A.1 design under `AGENTS.md`, the Constitution, and
> `docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md`

## 1. Purpose and Boundary

WP-4A.1 hardens the existing Entry competing-event Target materialization against two evidence
gaps:

1. a 14:55 Decision Reference Price must carry its own explicit adjustment-basis and source
   lineage; and
2. absence of a future daily bar must not be classified as `MISSING` merely because the exchange
   session has closed.

The work remains REHEARSAL-only Target infrastructure. It does not create an Entry Gate, Entry
Proposal, Entry model, Candidate-score change, WP-3 runner change, Provider Rehearsal Market
Artifact expansion, Position state, Portfolio decision, Execution action, accuracy claim, or Alpha
claim. It stops after WP-4A.1; the next approved operational dependency is a real, content-hashed
Xuntou normalized bundle and the WP-3 provider-backed run.

## 2. Ownership and Compatibility Boundary

The Data domain owns all market-evidence facts and their lineage:

```text
market_regime_alpha.data.path_evidence
    RehearsalEntryReferenceEvidence
    RehearsalFutureDailyBar
    RehearsalFutureSuspensionEvidence
    RehearsalFuturePathEvidenceCompleteness
```

The Entry domain continues to own only Target semantics, observation validation, and the pure
materializer. `materialize_entry_path_target()` accepts only complete
`entry_reference_evidence`; it removes the `decision_snapshots` argument.

There is deliberately no general compatibility adapter from `RehearsalDecisionSnapshot`. A naked
snapshot lacks an adjustment basis, identified source Dataset, and versioned evidence convention,
so an adapter could only manufacture prohibited facts. If a real caller later requires migration,
the Research/Adapter layer may provide a separately named explicit adapter that requires an
identified source, explicit basis, and versioned assertion convention. It must not live in the
Entry materializer, infer any value from the Target contract, or elevate REHEARSAL authority.

## 3. Reference Evidence and Price Lineage

`RehearsalEntryReferenceEvidence` has exactly these semantic inputs:

```text
symbol
decision_time
reference_price
price_adjustment_basis
available_at
source_dataset_id
evidence_convention
```

It exposes a deterministic `evidence_id` derived from its complete canonical payload. Its
constructor requires a positive finite price, non-empty versioned basis/convention and Dataset ID,
and `available_at <= decision_time`.

The materializer requires exactly one reference evidence item for every symbol in the complete
Candidate Population. Duplicate symbols, Population-external symbols, wrong Decision Time, or a
missing Population symbol are structural input errors that fail the full materialization. They do
not produce per-symbol `INVALID` or `ENTRY_REFERENCE_MISSING`, because tuple omission is not a
confirmed market-data fact.

For each symbol, the materializer fail-closes unless:

```text
reference price basis == EntryBarrierSpec.price_adjustment_basis
reference price basis == every consumed future daily-bar basis
reference source Dataset is in the declared evidence-source range
```

No Dataset name, Provider name, caller context, or Target specification may be used to infer the
reference price basis.

## 4. Future Evidence Lineage

`RehearsalFutureDailyBar` and `RehearsalFutureSuspensionEvidence` gain an explicit
`source_dataset_id` and deterministic `evidence_id` derived from all canonical evidence fields.
The existing finalization and availability contracts remain unchanged.

`RehearsalFuturePathEvidenceCompleteness` is a versioned, provider-neutral assertion of what the
identified future-evidence source has made knowable. It carries:

```text
source_dataset_id
available_at
completeness_convention
covered_symbols
coverage_through_session_date
session_readiness
```

`session_readiness` is a complete chronological tuple of records containing one exact
`session_date` and one timezone-aware `evidence_ready_at`. The completeness contract has a
deterministic `evidence_id` derived from its complete canonical payload.

The materializer validates all lineage against an explicit, narrow source range: each reference,
bar, suspension and completeness assertion source Dataset must be declared; bars and suspensions
must use the completeness assertion's source Dataset. Top-level source Dataset identities remain
the explicit materialization source set, not a substitute for evidence-level lineage.

## 5. Exact Population and Readiness Semantics

The completeness assertion's `covered_symbols` must equal the complete sorted
`CandidatePopulation.symbols` exactly. Partial coverage, Population-external coverage, duplicate
symbols, or a date watermark standing alone is insufficient to establish that a specific symbol's
bar should exist.

For the exact resolved Target horizon, the materializer requires one and only one readiness record
per session. Readiness dates must be chronological and unique, cannot include an outside-horizon
date, and each deadline must be at or after that session's explicit Calendar close. There is no
global default deadline. The `completeness_convention` is a non-empty versioned string.

The fixed evaluation order for an unresolved session is:

```text
1. materialized before Calendar session close
   -> NOT_YET_OBSERVED / HORIZON_NOT_COMPLETE

2. session closed but materialized before the declared readiness deadline
   -> NOT_YET_OBSERVED / EVIDENCE_NOT_YET_AVAILABLE

3. readiness deadline reached, but completeness assertion is unavailable as-of materialization
   or its coverage watermark does not include the session
   -> NOT_YET_OBSERVED / EVIDENCE_COVERAGE_NOT_COMPLETE

4. completeness assertion is available, watermark includes the session, and exact Population
   coverage is established, but neither a daily bar nor confirmed suspension exists
   -> MISSING / FUTURE_DAILY_BAR_MISSING
```

The completeness assertion itself must be available no later than `materialized_at`; an assertion
that arrives later cannot be used. For a confirmed `MISSING`, `observed_at` is precisely the
completeness assertion's `available_at`, never the runtime `materialized_at`.

## 6. Target Boundaries and Stable Reasons

`EntryBarrierSpec` rejects invalid barriers at construction:

```text
upper_return > 0
-1.0 < lower_return < 0
horizon_sessions > 0
```

`EntryPathReasonCode` becomes a versioned enum. The V1 members are:

```text
OUTCOME_RESOLVED
DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH
FUTURE_DAILY_BAR_MISSING
ENTRY_REFERENCE_MISSING
HORIZON_NOT_COMPLETE
EVIDENCE_NOT_YET_AVAILABLE
EVIDENCE_COVERAGE_NOT_COMPLETE
```

`ENTRY_REFERENCE_MISSING` is reserved for a future explicit provider unavailable-evidence
contract and is valid only with `INVALID`. It is not emitted in WP-4A.1: omitted reference tuple
items are structural input errors, not a per-symbol unavailable fact. The observation contract validates every
status/outcome/trigger/reason combination: terminal barrier outcomes use
`OUTCOME_RESOLVED`; dual touch uses its ambiguity reason; timeout uses horizon exhaustion;
`MISSING` uses future-bar missing; and each `NOT_YET_OBSERVED` state uses its exact temporal or
coverage reason. Daily open precedence and the terminal dual-touch behavior remain unchanged.

## 7. Identity Decision

The Target ID remains the barrier/path-label definition only. Readiness and completeness do not
change the truth function that maps a complete future path to `UP_FIRST`, `DOWN_FIRST`, or
`TIMEOUT`; they change whether a particular as-of artifact may establish that truth. Therefore
they do not enter `TargetId`.

`EntryPathTargetMaterialization` explicitly preserves:

```text
entry_reference_evidence_ids
consumed_future_bar_evidence_ids
consumed_future_suspension_evidence_ids
completeness_evidence_id
```

Its Artifact ID includes those identifiers and the complete resulting audit semantics. Because
each evidence ID already deterministically identifies its full canonical payload, the same payload
is not duplicated in the artifact hash merely to force sensitivity. Changes to reference price,
reference availability, basis, source identity, evidence convention, readiness deadline,
completeness availability, coverage watermark or scope therefore change the materialization
identity. Input tuple order is normalized and cannot change identity.

## 8. Tests and Delivery

TDD coverage will prove at minimum:

- reference-basis mismatch fails closed and fully aligned reference/Target/bar bases pass;
- reference Population coverage, source identity, Decision Time and duplicate validation fail
  closed;
- closure-before-readiness, unavailable completeness, and uncovered watermark each remain
  `NOT_YET_OBSERVED` with the specified reason;
- a covered session with no bar and no confirmed suspension is `MISSING` at completeness
  `available_at`;
- invalid lower barriers (`-1.0` and less) fail at contract construction;
- illegal reason/status/outcome/trigger combinations fail at observation construction;
- readiness/completeness and all evidence-lineage changes alter materialization identity;
- existing open-gap, one-sided touch, dual-touch, suspension and timeout classifications remain
  behaviorally unchanged.

The domain logic and its tests/documentation form one intentional commit. GitHub Actions CI is a
separate commit with Python 3.12, `pip install -e ".[dev]"`, `python -m pytest -q`,
`python -m ruff check .`, and `python -m mypy`.
