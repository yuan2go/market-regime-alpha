# H4.5 Risk-Reduction Manual Intent Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved bounded design for H4.5 risk-reducing decision confirmation
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** The design-only H4.5 outline in WP-PDL-HARDENING where this document is more specific
> **Superseded By:** None
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../status/Gap-Register.md
> **Code Evidence:** Design baseline is `origin/main@190fede53ab01487e7f339c38cf223b944ac861e`.

## 1. Goal and authority ceiling

H4.5 converts one still-valid H4 reducing-risk decision into one auditable,
human-confirmed SELL intent after reloading every durable authority and
rechecking current A-share execution constraints:

```text
OperationalExitDirectiveV2
+ PERMITTED RiskReducingDecision
+ latest Fill-derived T+1 Position
+ fresh reducing execution observation
+ explicit confirmation policy
+ human audit fields
→ immutable RiskReductionConfirmationAttempt
→ ManualTradeRecord V3 REDUCING intent
```

The success boundary is fixed:

```text
MANUAL_INTENT_CREATED
NO_FILL_CREATED
NO_BROKER_ORDER_CREATED
TRADING_AUTHORITY_NOT_GRANTED
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
```

Only a later human-recorded Fill may change Position. H4.5 does not contact a
Broker, append a Fill, close a PositionBook, transition a Thesis or schedule
future work.

## 2. Verified baseline and structural blockers

The code chain at the baseline is:

```text
TraceableManualExecutionApplicationService.create_trade
→ constructs ManualTradeRecord V2
→ SQLiteTraceableManualExecutionRepository.create_traceable_trade
→ validates CompleteAccountRiskDecision + PortfolioDecision + delta
→ opens or reuses PositionBook
→ writes manual_trade_records + traceable_manual_trade_bindings
```

The actual blockers are:

- `ManualTradeRecord` V1/V2 requires `risk_decision_id`,
  `risk_decision_hash`, `portfolio_decision_id` and
  `target_position_hash` as non-null domain fields;
- migration 004 projects `manual_trade_records.risk_decision_id` as
  `TEXT NOT NULL`;
- migration 006 `traceable_manual_trade_bindings` requires CompleteAccount
  Portfolio/Risk, post-trade snapshot and target-delta authority;
- `create_traceable_trade()` replays increasing-risk authority and may create
  a PositionBook, so it cannot represent a strict reducing route;
- base `append_fill()` loads a trade without validating the immutable V2 trace
  binding;
- `trades_for_book()`, `fills_for_book()` and the T+1 projector enumerate only
  V2 increasing bindings/schemas;
- H4 stores a complete replay bundle but exposes only the Decision through its
  public Repository Protocol;
- H5 similarly stores the complete replay bundle but exposes only the
  Observation;
- H6 exposes a verified package, while its source-package locator is not part
  of the Protocol;
- Decision, H4, H5, H6 and Execution repositories can point at different
  SQLite files, so separate repository writes cannot be described as atomic.

No H4 `RiskReducingDecision` may be inserted into the old
`risk_decision_id`, and no synthetic Portfolio/Risk/Target authority is
introduced.

## 3. Chosen architecture

The chosen approach is a versioned route authority plus one SQLite lifecycle
composition repository.

New domain behavior is split into:

1. `execution/risk_reduction.py`: immutable Directive, confirmation Policy and
   Attempt contracts;
2. `ManualTradeRecord` V3 in `execution/manual.py`: one strict route-aware
   aggregate while V1/V2 canonical dictionaries remain unchanged;
3. `application/trading_lifecycle/risk_reduction_lineage.py`: cross-domain
   H4/H5/H6 directive construction and lineage validation;
4. `application/trading_lifecycle/sqlite_risk_reduction.py`: migration 010,
   authority reload, one-transaction confirmation and reducing binding;
5. `application/trading_lifecycle/risk_reduction_confirmation.py`: an
   ID/hash-only command boundary over the repository port;
6. `scripts/confirm_risk_reduction.py`: CLI over canonical evidence paths and
   identifiers.

The Application Service canonicalizes the caller evidence behind an ID/hash
boundary. The SQLite composition repository reads and replays every durable
authority inside one `BEGIN IMMEDIATE` transaction before writing anything. This
read is the authoritative concurrency boundary.

All participating SQLite repositories must resolve to the same database path
and migrations 002, 004, 006, 007, 008, 009 and 010 must be present. A mixed
database composition fails closed with
`LIFECYCLE_DATABASE_COMPOSITION_REQUIRED`; no cross-database atomicity is
claimed.

## 4. ManualTrade V3 route authority

The new schema is:

```text
manual-trade-record-v3-route-authorized
```

`ManualTradeAuthorityRoute` contains `INCREASING` and `REDUCING`.

Common V3 trace fields are:

```text
position_book_id
thesis_id
opportunity_id
account_id
symbol
side
intended_quantity
expected_price_lower / expected_price_upper
operator audit and mutable manual-order state
```

The INCREASING route requires exactly:

```text
risk_decision_id / hash
portfolio_decision_id
target_position_hash
post_trade_snapshot_id / hash
```

The REDUCING route requires exactly:

```text
risk_reducing_decision_id / hash
risk_reduction_confirmation_id / hash
source_position_snapshot_id / hash / version
target_quantity
order_quantity
```

The two authority families are mutually exclusive in both the dataclass and
the `manual_trade_records` database CHECK. REDUCING also requires `SELL`,
`intended_quantity == order_quantity`, non-negative target quantity and a
positive order quantity.

Existing V1/V2 readers continue dispatching by their exact field sets. Their
serialized JSON and transition history are not rewritten. New increasing
trades use V3/INCREASING; stored V1/V2 rows are projected as INCREASING by
migration 010.

## 5. OperationalExitDirectiveV2

`OperationalExitDirectiveV2` is content-addressed and immutable. It binds:

```text
ExitAssessment ID/hash
REDUCE or EXIT action
REDUCING_RISK_DECISION required route
Thesis ID/version, Opportunity ID, PositionBook ID and symbol
source PositionSnapshot ID/hash/version
current ThesisHealthObservationV2 ID/hash
VERIFIED CompositeOperationalInputManifest ID/hash
created_at and sorted reason codes
```

Its evidence ceiling is fixed to:

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

Creation requires an existing historical `ExitAssessment` whose action is
REDUCE or EXIT, whose H5 evidence reference matches the supplied V2
Observation and whose Position/Thesis versions match. WAIT, HOLD, ADD and
DATA_INSUFFICIENT cannot create a directive. The historical ExitAssessment
schema and its `requires_portfolio_risk` semantics remain unchanged.

Directives and their exact source ExitAssessment JSON are stored append-only
before confirmation. Confirmation accepts only directive ID/hash.

## 6. Confirmation policy and attempt

`RiskReductionConfirmationPolicy` content-identifies every threshold:

```text
profile_id
builder_revision
maximum_decision_age_seconds
maximum_position_age_seconds
maximum_execution_observation_age_seconds
maximum_reference_price_deviation
operator_authentication_requirement
```

The current operator mode is explicitly `RECORDED_ACTOR_ONLY`. It records an
audit actor but always carries `OPERATOR_AUTHENTICATION_NOT_ESTABLISHED`; no
production identity claim is made.

Every accepted command creates one immutable
`RiskReductionConfirmationAttempt` in one of:

```text
CONFIRMED_INTENT
EXPIRED
POSITION_CHANGED
BLOCKED_ON_RECHECK
DATA_INSUFFICIENT
ACTION_SEMANTICS_CONFLICT
```

An attempt binds the H4 decision, directive, source/current Position, H5/H6
lineage, fresh execution observation, original H4 Gate configuration,
confirmation policy, actor/reason/time and sorted reason codes. Only a
CONFIRMED_INTENT has a ManualTrade ID. Multiple failed attempts are allowed;
a partial unique index permits at most one CONFIRMED_INTENT per H4 decision.

H4 V1 `REDUCE target_quantity = 0` remains replayable but confirmation returns
`ACTION_SEMANTICS_CONFLICT` with `REQUIRES_NEW_EXIT_DECISION`. H4 itself is not
changed.

## 7. Repository authority and operational lineage

Public Repository Protocols gain read-only bundle methods:

```python
RiskRouteRepository.get_verified_reducing_decision_bundle(decision_id)
ThesisHealthRepository.get_verified_observation_bundle(observation_id)
CompositeOperationalRepository.get_source_package_paths(manifest_id)
```

These methods restore canonical rows and repeat the existing Gate, Builder or
package replay. The H4.5 Application Service never calls `_restore_row`,
`_restore_bundle`, `_load_trade` or another private cross-module helper.

H5/H6 verification requires:

- the supplied H5 Observation is the unique latest chain tip for the Thesis;
- its replay bundle contains Market, Theme, Capital, Candidate, Signal and
  Path artifacts;
- every current component Envelope carries the exact H6 manifest ID/hash;
- Candidate contains Market/Theme/Capital lineage, Signal contains Candidate
  lineage and Path contains Signal lineage;
- the H6 repository reloads an exact package whose manifest is VERIFIED;
- manifest ID/hash matches the command and Directive;
- H5 Thesis/Opportunity are the same current aggregates loaded from Decision
  authority.

V1 H5, synthetic/historical V1 chains, non-VERIFIED H6 manifests and an H5
bundle that omits the exact H6 reference fail closed.

## 8. Position and market recheck

Inside the write transaction the repository loads the existing OPEN
PositionBook, all V1/V2/V3 trades for that book and all append-only Fills. It
canonical-restores each aggregate and validates exactly one route binding for
every traceable trade.

It then calls:

```python
PositionProjector.project_book_t_plus_one(
    book=book,
    trades=trades,
    fills=fills,
    calendar=calendar,
    symbol_session_statuses=statuses,
    as_of=confirmed_at,
)
```

The current Position must equal the H4 source Position on snapshot ID,
canonical hash, version, total quantity, available quantity, PositionBook,
Thesis, Opportunity and symbol. Any difference produces POSITION_CHANGED; the
old target/order is never resized.

The latest Position must be OPEN and no older than the confirmation policy.
The PositionBook must be OPEN. The current Thesis may be APPROVED or
INVALIDATED, but CLOSED is rejected.

The fresh `ReducingExecutionObservation` must match symbol/session, be
available no later than confirmation, satisfy policy freshness, and use its
own reference price. The original H4 action, target/order quantities and
`RiskReducingGateConfiguration` are replayed through
`RiskReducingExecutionGate`. Only PERMITTED continues.

The expected price range must contain the fresh reference price, and each edge
must remain within the policy's configured proportional deviation from that
reference price.

## 9. Atomic transaction and idempotency

The command hash covers only accepted command inputs: IDs/hashes, verified
calendar/status/recheck evidence, explicit policy, expected prices and human
audit fields. Same key/same hash replays the stored attempt and optional
ManualTrade; same key/different hash fails.

The successful transaction is:

```text
BEGIN IMMEDIATE
→ resolve command
→ restore/replay H4
→ restore OPEN book and current Fill-derived Position
→ restore current Decision aggregates
→ restore/replay latest H5
→ reload/replay VERIFIED H6 package
→ validate Directive and all scope/lineage
→ replay H4 Gate with fresh observation
→ validate expected price range
→ insert immutable attempt
→ insert ManualTrade V3 REDUCING projection/event
→ insert reducing binding
→ insert command ledger
→ reread/revalidate attempt, trade, binding and book projections
→ COMMIT
```

Every exception rolls the whole transaction back. Failed business attempts
write only attempt + command in the same transaction. No Repository A /
Repository B split write exists.

## 10. Migration 010

Migration 010 safely rebuilds `manual_trade_records` while preserving the
event and Fill ledgers. It makes `risk_decision_id` nullable and adds:

```text
authority_route
risk_reducing_decision_id
risk_reduction_confirmation_id
```

The route CHECK enforces exactly one projected authority. Historical rows are
copied as INCREASING without changing `aggregate_json` or event JSON.

New append-only tables are:

```text
operational_exit_directives
risk_reduction_confirmation_attempts
risk_reduction_confirmation_commands
risk_reducing_manual_trade_bindings
```

Partial unique indexes enforce one confirmed attempt per H4 decision, one
ManualTrade per confirmed attempt and one reducing binding per ManualTrade.
The disposable/test down migration succeeds only when remaining rows can be
represented by the old increasing-only schema; reducing rows fail closed.

## 11. Fill compatibility

`SQLiteTraceableManualExecutionRepository.get_trade()`, `trades_for_book()`,
`fills_for_book()` and the base fill path validate both increasing and
reducing bindings. The Position projector accepts V2 traceable and V3
route-authorized records with identical book/symbol/Thesis/Opportunity scope.

A later manual SELL Fill updates only the existing manual order state and
append-only Fill ledger. Projection then reduces the Position. Partial and
full fills do not allow the same H4 decision to create another intent; a new
H4 decision is required for any remainder. H4.5 never closes the book.

## 12. CLI and outputs

`scripts/confirm_risk_reduction.py` accepts a lifecycle database path,
decision/directive/H5/H6 IDs and hashes, a canonical trading-calendar path,
canonical symbol-status/recheck/policy paths, expected price range, actor,
reason, confirmation time and idempotency key. It accepts no caller-provided
Decision, Thesis, Opportunity, Position, PositionBook or ManualTrade JSON.

Success prints the fixed manual-intent/no-fill/no-broker boundary. Business
failure prints attempt ID/state/reasons, decision and source/current Position
identities, recheck identity and a null ManualTrade ID.

## 13. Testing strategy

TDD seams are the public domain constructors/Readers, Repository Protocols,
SQLite restart/migration behavior, confirmation Application Service, manual
Fill Application Service, Position projector and CLI. Tests do not call
private restoration helpers.

Vertical slices cover V3 route invariants; Directive/Policy/Attempt identity;
migration compatibility; authority bundle reads; latest Position and H5/H6
lineage; Gate/price replay; atomic success/failure/idempotency; reducing
binding tamper; later Fill projection; CLI output; V1/V2 and H4/H5/H6
regressions.

## 14. Rollback and forward repair

Operational rollback stops H4.5 writes and retains append-only attempts,
trades, Fills and Artifacts for audit. Existing V1/V2 Readers and increasing
execution remain available. Production-like databases use forward repair;
the migration 010 down script is only for empty/disposable tests and refuses
lossy conversion of reducing rows.

## 15. Explicit non-goals and remaining gaps

This phase does not implement H4 V2 quantity semantics, durable H7 queues or
acknowledgements, H8 ShadowRun, H9 validation, production authentication,
qualified formal data, broker authority, automatic Fill or automatic
Position/Thesis/Book transitions.

The Gap Register must retain:

```text
H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
SHADOW_READY_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
```
