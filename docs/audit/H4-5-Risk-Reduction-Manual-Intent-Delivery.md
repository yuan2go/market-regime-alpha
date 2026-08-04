# H4.5 Risk-Reduction Manual Intent Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound H4.5 implementation and verification record
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../superpowers/specs/2026-08-04-h4-5-risk-reduction-manual-intent-design.md, ../superpowers/plans/2026-08-04-h4-5-risk-reduction-manual-intent.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, H6-Composite-Operational-Evidence-Delivery.md, H5-Thesis-Health-Delivery.md, H4-Risk-Route-Delivery.md
> **Code Evidence:** implementation checkpoint `7c91be46c8adf1ad958e9c41b5a45021bcfa58ed`, based on `190fede53ab01487e7f339c38cf223b944ac861e`

## 1. Delivered outcome

H4.5 closes the code-level bridge:

```text
OperationalExitDirectiveV2
+ verified PERMITTED RiskReducingDecision
+ latest Fill/calendar-derived T+1 Position
+ current H5/H6 operational lineage
+ fresh execution/session evidence
+ explicit confirmation policy and audit fields
→ immutable RiskReductionConfirmationAttempt
→ ManualTrade V3 REDUCING SELL intent
```

A successful command reports only:

```text
CONFIRMED_INTENT
MANUAL_INTENT_CREATED
NO_FILL_CREATED
NO_BROKER_ORDER_CREATED
TRADING_AUTHORITY_NOT_GRANTED
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
```

The bridge never creates a Fill, Broker Order, Position mutation, Thesis
transition or PositionBook close.

## 2. Baseline and discovered schema blocker

The branch started from `origin/main` at
`190fede53ab01487e7f339c38cf223b944ac861e`. Baseline pytest, Ruff, configured
mypy, package build, documentation validation and diff checks passed before
implementation.

The actual ManualTrade V1/V2 path had one structural authority shape:

- `risk_decision_id` was non-null in the aggregate projection;
- trace bindings required a complete-account PortfolioDecision,
  CompleteAccountRiskDecision, trade delta and post-trade account snapshot;
- traceable trade creation opened a PositionBook and enforced approved
  complete-account Risk;
- Fill lookup assumed that single increasing-risk binding.

Using an H4 `RiskReducingDecision` in those columns would falsify increasing
authority. H4.5 therefore introduces a new aggregate schema and separate trace
route; it does not create fake Portfolio/Risk/TargetPosition evidence or alter
historical aggregate JSON/hash semantics.

## 3. ManualTrade V3 route authority

`manual-trade-record-v3-route-authorized` adds
`ManualTradeAuthorityRoute.INCREASING | REDUCING`.

| Route | Required authority | Forbidden authority |
|---|---|---|
| INCREASING | approved complete-account Risk, Portfolio, target delta and post-trade snapshot | H4 reducing decision, confirmation and source reducing Position |
| REDUCING | SELL, permitted H4 decision, confirmed attempt, existing OPEN book, Thesis, Opportunity, source Position, target and order quantities | complete-account Risk, Portfolio, target-position and post-trade snapshot |

Domain validation and migration 010 database checks reject both authority sets
present, both missing, route/side mismatch and quantity/scope mismatch.
Increasing trade creation keeps its former checks and now persists as V3
`INCREASING`; V1/V2 canonical Readers remain exact and readable.

## 4. Directive, policy and attempt contracts

`OperationalExitDirectiveV2` is content-addressed and accepts only REDUCE or
EXIT with `REDUCING_RISK_DECISION`. It binds the historical ExitAssessment,
H4 source Position, current H5 observation and exact VERIFIED H6 manifest. It
does not decide quantity.

`RiskReductionConfirmationPolicy` content-identifies every freshness and price
deviation threshold; the command supplies all values explicitly. The current
authentication requirement is `RECORDED_ACTOR_ONLY`, which deliberately emits
`OPERATOR_AUTHENTICATION_NOT_ESTABLISHED`.

Every persisted `RiskReductionConfirmationAttempt` is immutable and
content-addressed. Supported terminal states are `CONFIRMED_INTENT`, `EXPIRED`,
`POSITION_CHANGED`, `BLOCKED_ON_RECHECK`, `DATA_INSUFFICIENT` and
`ACTION_SEMANTICS_CONFLICT`. Failed commands may create multiple attempts; a
partial unique index and in-transaction check allow at most one confirmed
intent for each H4 decision.

## 5. Repository authority and operational lineage

The application command accepts IDs/hashes, verified package locators, current
canonical execution evidence, policy and audit fields. It does not accept
caller-submitted Thesis, Opportunity, Position, H4 Decision or ManualTrade
aggregates.

Public repository methods load and replay:

- current Thesis and Opportunity from `DecisionLifecycleRepository`;
- `VerifiedRiskReducingDecisionBundle` from `RiskRouteRepository`;
- latest `VerifiedThesisHealthBundle` from `ThesisHealthRepository`;
- the exact H6 manifest and source packages from
  `CompositeOperationalRepository`;
- existing book, trade history and Fill history from the traceable execution
  repository.

The H5 lineage validator accepts only H5 V2 inputs whose Market, Theme,
Capital, Candidate, Signal and Path chain descends from
`ResearchInputBundleV2.OPERATIONAL_EXPLORATORY_ARCHIVE` and the exact VERIFIED
H6 Composite manifest. V1, synthetic/historical, non-latest, non-VERIFIED,
unbound or ID/hash-mismatched evidence fails closed. This validation retains
the exploratory, non-PIT, non-OOS and non-trading ceiling.

## 6. Position and execution recheck

While holding the write transaction, the repository projects the latest
Position from the existing OPEN PositionBook, all route-aware ManualTrades,
append-only Fills, explicit `TradingCalendarArtifact` and current
`SymbolTradingSessionStatus` through
`PositionProjector.project_book_t_plus_one()`.

The ordered current Fill ledger is compared with the H4 source Fill identity.
If it is unchanged, replay uses the source Position `as_of` so elapsed wall
clock alone cannot invent a new content identity; the explicit policy then
checks the source Position age at confirmation. If any Fill was added or
corrected, replay advances to confirmation time and exposes the changed
snapshot. Current calendar/session evidence can also change sellability and
therefore the canonical Position.

The current snapshot ID, canonical hash, version, total, available, book,
Thesis, Opportunity and symbol must exactly equal the H4 source Position. Any
new or corrected Fill produces `POSITION_CHANGED`; H4.5 never adjusts the old
target/order quantity.

The fresh `ReducingExecutionObservation` is canonical evidence. Its symbol,
session, availability time, state, reference price, volume and source artifact
are validated, and the original H4 configuration reruns
`RiskReducingExecutionGate`. Only `PERMITTED_FOR_MANUAL_CONFIRMATION` can create
an intent. The submitted expected price interval must be positive, ordered,
contain the fresh reference price and remain within policy deviation.

H4 V1 replay still permits REDUCE to zero. H4.5 rejects that case as
`ACTION_SEMANTICS_CONFLICT` plus `REQUIRES_NEW_EXIT_DECISION`. The separate
`H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER` gap owns the future H4 schema change.

## 7. Migration 010 and atomicity

Migration 010 safely rebuilds `manual_trade_records`, making the old Risk ID
nullable only under strict route checks. Historical rows project as
`INCREASING`; their aggregate/event JSON, IDs, hashes, Fill ledger and foreign
keys are not rewritten.

It adds append-only `operational_exit_directives`,
`risk_reduction_confirmation_attempts`,
`risk_reduction_confirmation_commands` and
`risk_reducing_manual_trade_bindings`, together with uniqueness, route guard,
foreign-key and no-update/no-delete enforcement. Repository startup validates
columns, SQL checks, indexes, foreign keys and trigger bodies. The isolated down
migration refuses to discard reducing rows.

`SQLiteRiskReductionManualIntentRepository` composes all required authorities
against one exact SQLite path. One `BEGIN IMMEDIATE` owns authority reload,
replay, Position reconstruction, lineage/directive/Gate/price validation,
attempt write, ManualTrade V3 write, reducing binding, command ledger and final
projection reread. Any failure rolls the whole command back. No cross-database
atomicity is claimed.

## 8. Fill and compatibility evidence

`get_trade()`, `trades_for_book()`, `fills_for_book()` and `append_fill()` now
validate increasing or reducing trace bindings. A confirmed reducing SELL
intent accepts only a later explicit human Fill through the existing append-only
ledger. Partial Fill reduces the T+1 Position and makes the original H4
confirmation scope unusable; residual quantity requires a new H4 decision.
A full EXIT Fill reaches CLOSED Position state and can be consumed by the
separate explicit PositionBook close path using the same calendar/session
evidence. H4.5 itself does neither action.

Tests retain V1 manual execution, V2 traceable increasing execution, historical
aggregate replay and migration compatibility. Increasing authority was not
relaxed.

## 9. Verification evidence

Observed locally on the implementation checkpoint:

```text
H4_5_FOCUSED = 72 passed
EXECUTION_CONTEXT = 87 passed
PORTFOLIO_CONTEXT = 55 passed
POSITION_CONTEXT = 91 passed
APPLICATION_CONTEXT = 114 passed
H4_REGRESSION = 42 passed
H5_REGRESSION = 101 passed
H6_REGRESSION = 67 passed
FULL_PYTEST = 1531 passed, 8 subtests passed, 6 existing warnings
RUFF = PASS
MYPY = PASS, 265 source files
PACKAGE_BUILD = PASS, sdist and wheel
DOCUMENT_AUTHORITY_AND_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

The six warnings are the pre-existing pandas fragmentation warnings in the
Top1000 leakage-attribution tests. Remote CI evidence is recorded only after
the Draft PR checks finish.

## 10. Authority ceiling and remaining work

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
SHADOW_READY_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
```

H7 durable scheduling/acknowledgement, H8 recoverable ShadowRun and H9 formal
validation remain separate work. Qualified H6 producers, authenticated
operator identity, external account/Fill reconciliation and broker architecture
also remain unimplemented.

**Shadow Ready: NO**
**Trading Authority: NO**
