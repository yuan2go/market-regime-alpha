# H5 Artifact-Derived Thesis Health Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved bounded design for H5 Artifact-Derived Thesis Health
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../status/Current-State.md
> **Code Evidence:** Design and implementation branch starts from `origin/main@df5c731da018819d9710f2d2f1ecffb4995fa082` after merged PR #30.

## 1. Goal and bounded context

H5 removes caller-authored Thesis-health conclusions from the new operational
path. It derives a content-addressed observation from verified research
Artifacts, a machine-executable invalidation rule set and an explicit health
configuration:

```text
TradingThesis + TradingOpportunity
+ current verified research chain
+ DecisionPriceSnapshot
+ typed invalidation rules
+ explicit health configuration
+ optional ManualInvalidationEvidence
+ optional prior ThesisHealthObservationV2
→ ThesisHealthObservationBuilder
→ immutable ThesisHealthObservationV2
→ append-only SQLite persistence
→ V2-only Holding/Exit assessment service
```

The output is evidence. It does not mutate a Thesis, create an H4 decision,
create a ManualTrade or Fill, update a Position, contact a Broker or grant
trading authority.

## 2. Baseline facts

At `main@df5c731da018819d9710f2d2f1ecffb4995fa082`:

- PR #30 is merged and migration 007 is the latest migration;
- H4 is implemented and verified but remains decision-only;
- `position/assessment.py` defines V1 `ThesisHealthObservation` with caller
  fields `signal_support`, `theme_support`, `capital_support` and
  `triggered_condition_ids`;
- `LifecycleReviewApplicationService` consumes that V1 type and the existing
  lifecycle CLI accepts its canonical payload;
- the concrete V1 fixtures are `tests/position/test_assessments.py` and
  `tests/evaluation/test_lifecycle_replay.py`;
- Platform V2 Market, Theme, Capital and Candidate Artifacts share an
  `ArtifactEnvelope`; Candidate binds Market, Theme and Capital, Signal binds
  Candidate, and PathForecast binds Signal through exact IDs and hashes;
- `DecisionPriceSnapshot` is already content-addressed and carries unique
  symbol observations, DecisionTime, event time, availability time, source
  identity and price quality;
- no complete machine representation exists for `InvalidationCondition`;
- no durable Thesis-health repository exists.

The verified local baseline is 1305 passed tests, Ruff PASS, configured mypy
PASS over 256 source files, package build PASS and documentation-link PASS.

## 3. Chosen approach

The accepted approach is a complete H5 vertical slice plus a thin V2
operational assessment adapter. H5 does not introduce `LifecycleReviewRunV2`
or copy its publisher, Reader, replay or complete evaluation package.

The adapter consumes a verified `ThesisHealthObservationV2`, resolves a
health context and reuses the existing Holding/Exit decision internals. It
does not synthesize a V1 observation or reconstruct support booleans.

## 4. Domain objects

H5 introduces these versioned, frozen types in the Position bounded context:

```text
ThesisHealthSupportState
InvalidationRuleType
CapitalRuleScope
PriceBelowRule
PriceAboveRule
MarketStateInRule
TradePermissionInRule
ThemeRotationStateInRule
CapitalEvolutionStateInRule
SignalStateInRule
TimeAfterRule
ManualEvidenceRequiredRule
ThesisInvalidationRuleSet
ThesisHealthRuleConfiguration
ManualInvalidationEvidence
ThesisHealthInputBundle
ThesisHealthObservationV2
ThesisHealthObservationBuilder
```

Every configuration, rule set, manual evidence item, replay input bundle and
V2 observation has an exact schema, semantic payload, SHA-256 content hash and
content-derived identity. Canonical Readers reject missing, extra or
ill-typed fields and revalidate identity.

`ThesisHealthSupportState` is:

```text
SUPPORTED
WEAKENING
INVALIDATING
DATA_INSUFFICIENT
```

The existing `ThesisHealth` enum remains the observed/effective health state
vocabulary:

```text
HEALTHY
WEAKENING
INVALIDATED
DATA_INSUFFICIENT
```

An effective state is nullable. `None` means `NOT_ESTABLISHED`; it is required
for the first data-insufficient observation and cannot be silently replaced by
`HEALTHY`.

## 5. Typed invalidation rules

`InvalidationCondition.description` is never parsed. A condition ID does not
encode executable semantics. A `ThesisInvalidationRuleSet` binds exact
machine rules to one Thesis ID and version.

The supported mapping is:

| Typed rule | Required `InvalidationKind` | Executable meaning |
|---|---|---|
| `PRICE_BELOW` | `PRICE` | current verified price is below the explicit threshold |
| `PRICE_ABOVE` | `PRICE` | current verified price is above the explicit threshold |
| `MARKET_STATE_IN` | `MARKET_REGIME` | current Market state belongs to an explicit set |
| `TRADE_PERMISSION_IN` | `MARKET_REGIME` | current TradePermission belongs to an explicit set |
| `THEME_ROTATION_STATE_IN` | `THEME` | the symbol primary theme has an explicitly listed state |
| `CAPITAL_EVOLUTION_STATE_IN` | `CAPITAL` | explicit theme, symbol or both scope matches configured states |
| `SIGNAL_STATE_IN` | `SIGNAL` | current Signal state belongs to an explicit set |
| `TIME_AFTER` | `TIME` | assessed time is at or after the exact Thesis time invalidation |
| `MANUAL_EVIDENCE_REQUIRED` | `MANUAL` | valid explicit manual evidence exists for the condition |

The rule set is valid only when:

- each Thesis condition is mapped exactly once;
- no extra, duplicate or unknown condition ID exists;
- the typed rule and `InvalidationKind` match;
- the rule's Thesis ID/version match the current Thesis;
- `TIME_AFTER` contains exactly `thesis.time_invalidation`;
- all state sets are sorted, unique and non-empty;
- all numeric thresholds are finite and domain-valid.

An absent or incomplete rule set is rejected at the H5 command boundary with
`THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED`. H5 does not guess a migration
for an old Thesis and does not publish a misleading healthy observation.

Component support maps produce `SUPPORTED`, `WEAKENING` or
`DATA_INSUFFICIENT`. `INVALIDATING` is overlaid only by a matching typed rule,
so configuration cannot silently add a Thesis invalidation condition.

## 6. Explicit health configuration

`ThesisHealthRuleConfiguration` contains no production defaults. Its identity
covers:

- `builder_revision`;
- maximum ages for Market, Theme, Capital, Candidate, Signal, PathForecast,
  price and prior observation;
- `maximum_price_research_skew_seconds`;
- complete MarketState and TradePermission support maps;
- complete SignalState and ConfirmationState support maps;
- minimum Signal score and confidence;
- complete PathForecast status and calibration maps;
- PathForecast sample, MFE, MAE and barrier reward/risk gates;
- complete ThemeRotationState and CapitalEvolutionState support maps.

All enum mappings require exact coverage. Missing or duplicate mappings are
configuration errors. PathForecast gates remain explicitly exploratory and
the output always retains `FORMAL_OOS_ALPHA_NOT_ESTABLISHED`. MFE, MAE and
barrier relationships are not probabilities or return promises.

Capital support always requires both the matching `ThemeCapitalEvolution` and
the matching `SymbolCapitalEvolution`; observable-proxy inference is never
described as hidden institutional intent.

## 7. Artifact inputs and lineage

The Builder accepts actual domain types rather than dictionaries:

```text
TradingThesis
TradingOpportunity
MarketRegimeSnapshot
ThemeRotationSnapshot
CapitalEvolutionSnapshot
CandidateSet
SignalSnapshot
PathForecast
DecisionPriceSnapshot
ThesisHealthRuleConfiguration
ThesisInvalidationRuleSet
optional ManualInvalidationEvidence tuple
optional prior ThesisHealthObservationV2
explicit assessed_at, actor and reason
```

`TradingOpportunity` is required to prove the original Thesis creation
evidence. The Thesis must include the Opportunity's exact Candidate, Signal
and PathForecast references. Those creation references remain in V2 output and
are never confused with the current health inputs.

The current research chain must prove:

```text
Capital input IDs/hashes include current Theme
Candidate input IDs/hashes include current Market + Theme + Capital
Signal input IDs/hashes include current Candidate
PathForecast input IDs/hashes include current Signal
```

The six research Artifacts must have compatible DecisionTime and identical
SourceManifest ID/hash lineage. Under the current executable producers this is
an exact common DecisionTime. H5 validates the actual envelopes and lineage;
it does not infer relationships from artifact names.

The current research DecisionTime cannot precede the creation Opportunity's
DecisionTime. Current Signal and Path symbol must equal the Thesis symbol.
CandidateSet must contain the symbol exactly once with a non-null
`primary_theme_id`. ThemeRotation must contain that theme exactly once.
CapitalEvolution must contain both that theme and the symbol exactly once and
the symbol capital item must bind the same theme.

Each envelope and payload is reconstructed canonically. Each envelope's
DecisionTime and created time must not be later than `assessed_at`, and its age
must satisfy the component-specific configuration threshold.

## 8. Price time policy

The existing `DecisionPriceSnapshot` is reused. H5 derives a stable price
observation ID/hash from the selected observation's canonical payload and also
records the enclosing snapshot ID/hash.

Price evidence does not have to share the research DecisionTime. It must pass:

```text
price symbol == Thesis symbol
quality == AVAILABLE
event_time <= assessed_at
availability_time <= assessed_at
assessed_at - availability_time <= maximum_price_age_seconds
abs(price DecisionTime - research DecisionTime)
    <= maximum_price_research_skew_seconds
```

The DecisionPriceSnapshot hash and identity are revalidated and its
SourceManifest ID must be compatible with the current research lineage. The
price snapshot currently carries a SourceManifest ID but not a separate
SourceManifest hash. H5 does not invent that missing authority or introduce an
H6 composite manifest.

## 9. Manual invalidation evidence

`ManualInvalidationEvidence` binds schema, evidence ID/hash, Thesis ID/version,
condition ID, actor, reason, recorded time and availability time.

No evidence means the Manual condition has not been triggered. It does not
make every manual-capable Thesis data-insufficient.

Submitted evidence must reconstruct canonically, match the Thesis and exact
manual rule, be unique for its condition, have an availability time no earlier
than its recorded time and have neither time in the future. Scope mismatch,
future evidence, conflicting evidence or incomplete references produce
`DATA_INSUFFICIENT`, unless an unrelated deterministic invalidation already
has priority.

Every V2 observation retains:

```text
MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
```

This limitation does not make structurally valid evidence false, but records
that production identity authentication has not been established.

## 10. Observation V2

`ThesisHealthObservationV2` is an independent schema and does not change V1.
Its semantic payload includes:

- Thesis ID/version, Opportunity ID, symbol and primary theme;
- assessed time, actor and reason;
- market price, price observation and snapshot IDs/hashes;
- current Market, Theme, Capital, Candidate, Signal and Path IDs/hashes;
- original Thesis supporting evidence references;
- configuration ID/hash, rule-set ID/hash and builder revision;
- Market, Signal, Path, Theme and Capital support states;
- triggered condition IDs, missing reason codes and all reason codes;
- `observed_health_state`;
- prior observation ID/hash, prior observed state and prior effective state;
- nullable `effective_health_state`;
- manual evidence IDs/hashes;
- the non-claims `FORMAL_OOS_ALPHA_NOT_ESTABLISHED`,
  `MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED` and
  `TRADING_AUTHORITY_NOT_GRANTED`.

Callers cannot provide component states, triggered conditions, observed state
or effective state. The Builder calculates every one.

## 11. Derivation priority and state machine

Observed-state priority is:

```text
deterministic typed invalidation
    → INVALIDATED
required evidence missing/stale/future/conflicted
    → DATA_INSUFFICIENT
verified support weakening
    → WEAKENING
all required support satisfied
    → HEALTHY
```

Terminal Thesis state, exact Thesis time invalidation, typed price
invalidation and valid typed manual evidence are deterministic. Explicit
Market, Theme, Capital or Signal invalidation rules are deterministic only
when their own required Artifact is verified. A determined invalidation is not
masked by missing unrelated evidence.

Effective-state transitions are:

| Prior effective | Observed | New effective |
|---|---|---|
| none | `HEALTHY` | `HEALTHY` |
| none | `WEAKENING` | `WEAKENING` |
| none | `INVALIDATED` | `INVALIDATED` |
| none | `DATA_INSUFFICIENT` | none |
| `HEALTHY` | `HEALTHY` | `HEALTHY` |
| `HEALTHY` | `WEAKENING` | `WEAKENING` |
| `WEAKENING` | `HEALTHY` | `WEAKENING` |
| any non-invalidated | `INVALIDATED` | `INVALIDATED` |
| `INVALIDATED` | any | `INVALIDATED` |
| any established | `DATA_INSUFFICIENT` | unchanged |

`WEAKENING → HEALTHY` and `INVALIDATED → HEALTHY` are not implemented.

When prior evidence exists, V2 binds its ID/hash, observed state and effective
state. Prior must reconstruct, belong to the same Thesis, have a Thesis
version not greater than the current version and precede the new assessed
time. A stale prior yields an observed data-insufficient result while retaining
its established effective state, unless deterministic invalidation wins.

## 12. Private replay input bundle

`ThesisHealthInputBundle` stores exact canonical inputs required to reproduce
the Builder result. Its content-derived identity and hash are included in the
command semantics and Repository validation.

It is explicitly:

```text
H5_PRIVATE_REPLAY_BUNDLE
NOT_COMPOSITE_OPERATIONAL_INPUT_MANIFEST
NOT_H6_AUTHORITY
DOES_NOT_REPLACE_SOURCE_ARTIFACTS
DOES_NOT_INFLATE_DATA_ELIGIBILITY_OR_PIT_STATUS
```

It may contain the complete prior V2 observation to make replay independent of
mutable caller state, but the Repository must also match that prior to the
stored database row.

## 13. Repository and migration 008

H5 adds `position/migrations/008_thesis_health_up.sql` and an isolated down
migration. Package data is updated to ship Position migrations.

The up migration creates:

```text
thesis_health_observations
thesis_health_commands
```

Observation rows contain projection columns, canonical observation JSON and
the private input bundle JSON. Configuration and rule-set canonical payloads
are part of that bundle. Commands contain idempotency key, command hash,
observation ID and creation time.

Database constraints and triggers enforce:

- unique observation identity and content hash;
- append-only observations and commands;
- valid observed/effective state values;
- paired prior ID/hash fields;
- at most one root observation per Thesis;
- at most one direct successor per prior observation;
- command-to-observation foreign-key integrity.

`SQLiteThesisHealthRepository` validates migration version, exact columns,
unique indexes, foreign keys, checks and append-only trigger SQL after applying
the repeat-safe migration.

One `BEGIN IMMEDIATE` transaction performs:

```text
resolve command and verify command hash
→ restore identical replay if present
→ validate prior equals the current chain tip
→ validate an existing observation identity or insert the bundle
→ insert command
→ reload, reconstruct and replay Builder
→ COMMIT
```

Any error rolls back every write. Reads parse every JSON object through its
canonical Reader, compare every projection/reference and recompute the
Builder output. Observation JSON, bundle JSON, projection, prior reference,
configuration, rule set or command tampering is rejected.

The Repository Protocol exposes save, command resolution, observation read and
latest-observation lookup without SQLite-specific types.

## 14. Application Service and idempotency

`ThesisHealthApplicationService` accepts actual domain objects and an optional
expected prior observation ID/hash. It does not accept V1.

For a new command it:

1. requires an exact complete rule set;
2. loads the requested prior from the Repository and verifies its hash;
3. canonical-round-trips all command inputs;
4. constructs the content-addressed private input bundle;
5. hashes the command name and exact bundle semantics;
6. resolves a same-key/same-hash replay before testing the current chain tip;
7. invokes the Builder;
8. atomically persists and returns the reconstructed observation.

The command hash binds Thesis ID/version, assessed time, every input ID/hash,
configuration and rule-set identities, builder revision, prior ID/hash/states,
manual evidence and actor/reason. A same idempotency key with a different hash
is rejected. A new command that omits or references a non-latest prior is
rejected as a fork.

## 15. CLI

`scripts/build_thesis_health.py` accepts a SQLite database and a strict request
document containing paths to:

- canonical Thesis and Opportunity JSON;
- one verified Platform V2 Research Layer package;
- one verified Signal run package;
- one verified PathForecast package;
- one canonical DecisionPriceSnapshot;
- one health configuration and one invalidation rule set;
- optional manual evidence documents;
- optional prior observation ID/hash;
- explicit assessed time, actor, reason and idempotency key.

Package Readers verify checksums, exact file sets and embedded canonical
objects before the CLI selects the Thesis symbol's unique Signal and Path.
The top-level schema rejects V1 support booleans, triggered conditions and
final health fields.

Output includes all V2 identities, component states, state-machine fields,
reasons and source references plus:

```text
OBSERVATION_ONLY
NO_TRADE_ACTION_CREATED
TRADING_AUTHORITY_NOT_GRANTED
```

## 16. V2-only operational assessment adapter

Existing Holding and Exit models are refactored around an internal resolved
health context:

```text
symbol
market_price
observed/effective health
health evidence reference
health reason codes
observed/availability time
```

The old V1 path remains:

```text
V1 ThesisHealthObservation
→ legacy ThesisHealthEvaluator
→ resolved health context
→ shared Holding/Exit decision internals
```

The new path is:

```text
ThesisHealthObservationV2
→ strict V2 canonical/scope/time validator
→ resolved health context
→ same Holding/Exit decision internals
```

`OperationalPositionAssessmentServiceV2` accepts only V2 and returns existing
`HoldingAssessment` and `ExitAssessment` inside an assessment-only result. It
does not construct V1 booleans, duplicate Holding/Exit rules, persist a durable
assessment schedule, call H4 or create any execution fact.

The existing ExitAssessment statements that REDUCE/EXIT require a new
Portfolio/Risk decision remain unchanged. Replacing those old statements with
the H4 reducing-risk route is H4.5/H7 work, not H5.

## 17. V1 compatibility

The V1 `ThesisHealthObservation`, `ThesisHealthEvaluator`, historical
`LifecycleReviewRun`, Reader, publisher and replay remain readable and keep
their schema semantics. Existing fixtures remain valid.

New H5 domain, Application Service, CLI and operational V2 assessment service
cannot accept V1. V1 is a compatibility boundary, not a permitted H5 command
format.

## 18. Test matrix

Tests cover:

- every typed rule, configuration/rule-set identity and exact condition map;
- V2 and input-bundle canonical round trip, identity and hash tamper;
- research lineage, SourceManifest, symbol/theme and DecisionTime scope;
- current evidence preceding Thesis creation evidence;
- price later than research within skew, over-skew, stale and future price;
- Signal/Path and Candidate/Market/Theme/Capital lineage breaks;
- all support, weakening components, risk-off/extreme-risk rules, price, time
  and manual invalidation;
- deterministic invalidation priority over unrelated missingness;
- every prior/effective transition, no recovery, first insufficient state,
  prior hash/time/scope/fork failures;
- SQLite save/read/restart, idempotency conflict, append-only triggers,
  repeat-safe migration, isolated down migration, schema/trigger spoofing,
  tamper, replay mismatch and transaction rollback;
- strict CLI request, idempotent output and explicit no-authority boundary;
- V2-only Holding/Exit service and unchanged H4.5/H7 semantics;
- V1 Reader/fixture compatibility and H4 focused regression.

Every time is fixed and timezone-aware. SQLite tests use real files.

## 19. Rollback and forward repair

H5 rollback stops new V2 assessment commands and keeps migration 008 tables
read-only. Stored observations and replay bundles are immutable evidence and
must not be rewritten. The isolated down migration is for disposable/test
databases only after evidence export.

V1 Readers remain available during rollback. Source research and price
Artifacts are never mutated or replaced by the H5 bundle. A semantic change to
rules, freshness or state transitions requires a new configuration, rule-set
or schema identity and forward repair.

## 20. Explicit non-goals and authority ceiling

H5 does not implement:

- `LifecycleReviewRunV2` or a copied review package;
- H6 Composite Operational Evidence;
- the H4.5 reducing-decision-to-manual-execution bridge;
- H7 scheduling, acknowledgement or durable Holding/Exit state;
- H8 ShadowRun or H9 formal validation;
- ManualTrade, Fill, Position or Broker schema changes;
- automatic Thesis invalidation;
- automatic H4 decisions, orders or execution;
- production parameter calibration or a new Entry Model.

Completion retains:

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
SHADOW_READY_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
```

H5 only derives trustworthy Thesis Health. It does not connect
`ExitAssessment` to the H4 reducing-risk route.
