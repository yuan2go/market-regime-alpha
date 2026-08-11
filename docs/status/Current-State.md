# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Sole current implementation-status document
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations`, `tests`

## Implemented engineering boundary

The system is a PostgreSQL-only modular monolith with one Continuous Research Runtime. It has durable source freeze, Dataset/Feature materialization, Model Governance selection, State/StateSeries/Pool/Candidate, controlled minute/Signal/Forecast work, Research Summary, Canonical Lifecycle mechanics, manual-account Decision support, Research Shadow, prospective outcomes, Panel V2 and Research Validation harnesses. Free-data operation includes an automatic retrospective BaoStock decision/outcome/sample pipeline, a PostgreSQL Historical Registry Reader in the Research/Shadow Forecast composition, a full-A-share exploratory Security Master/Research Universe snapshot, explicit Proxy/Derived/Declared reference semantics, T+1 settlement/enrichment and factor lineage/de-duplication evidence. Research Summary and settlement bind the same Feature Bundle V2 identity used by Signal and Panel enrichment; the legacy static bundle remains its immutable Controlled-package wrapper, not a competing feature Authority.

Phase B engineering also includes daily cross-sectional evaluation science, tie-aware RankIC, label-aware purging/embargo, trading-date moving-block bootstrap, explicit `NOT_ESTIMABLE`, calibration method harnesses and a PostgreSQL Portfolio Shadow ledger. `settle-day` automatically derives eighteen horizon/barrier calibration hypotheses from PostgreSQL-owned Panel V2 forecast exposures and Targeted Outcome labels, persists positive or negative hypothesis evidence, and records exact partition bindings with label-aware purging only when Forecast and Outcome Target identity are equal. The current multi-session Forecast cannot be reused as a T+1 target Forecast, so that mismatch remains truthfully `NOT_ESTIMABLE`. Every result remains `calibrated=false`. Portfolio Shadow records per-value provenance for market facts and assumptions alongside Cash, Order Intent, Shadow Fill, Shadow Position, NAV, exposure, turnover, cost, capacity, drawdown and attribution while enforcing A-share T+1, 100-share lots, suspension, price-limit and continuous-auction constraints. Append-only Principal/Role/Approval/Audit governance serializes bootstrap and last-Admin invariants; every Continuous CLI invocation is resource-bound and audited, and non-Admin Shadow/recovery mutation requires an exact independent approval. Production-mode mutation is rejected before Journal writes. A recovery audit is available through the same CLI. External authentication is not bound, so the caller-supplied Principal ID is not an authenticated identity proof.

Actual positions derive only from observed manual fills. The system creates no broker order and does not automatically mutate actual positions.

Phase C engineering adds an immutable Formal Research Protocol with exact
canonical-owner bindings (including full Frozen Trading Calendar replay), OutcomeTarget-bound forecasts, frozen-calendar
purge/embargo, Provider-by-Contract-by-Fact qualification decisions,
owner-resolved Historical Sample and Locked OOS decisions, formal Calibration
partition replay, Entry/Holding/Exit evidence replay, prospective Strategy
Shadow qualification, persisted Production Admission floors and Controlled
Execution readiness. Strategy Shadow policies now have one reusable immutable
PostgreSQL owner, so a frozen policy can accumulate multiple prospective days;
historical session-local Policy artifacts remain unchanged. Formal Protocol
recording accepts only the Protocol reference and reloads every result-affecting
component from its PostgreSQL owner; immutable owner-resolution receipts preserve
the exact owner payload, identity, hash and recorded/resolved time, reject
backdated freezes and anchor the Calendar payload to the existing PIT Artifact
Authority. Formal Forecast computation accepts only Protocol/PIT/symbol/
idempotency scope, derives DecisionTime from Formal PIT, assigns materialization
time from PostgreSQL and resolves exact Model/Configuration/Code/Feature/Factor/
Threshold/Dataset/Universe/Target lineage. Unsupported installed executors emit
`NOT_ESTIMABLE`; older caller-submitted forecasts remain explicitly
`EXPLORATORY_CALLER_SUBMITTED` and cannot enter a new Formal family evaluation.

Migration 057 freezes one content-addressed multi-target Hypothesis Family per
Formal Protocol. One raw subject/decision-session/outcome-session path can be
unlocked only once across Model, Forecast, Protocol, Dataset, Universe, Target
and Label revisions, while every pre-registered Target may consume its own
observation during that first family unlock. Family evaluation corrects all
Target × metric × observed slice × sensitivity × fold hypotheses together and
retains every predeclared empty fold as `NOT_ESTIMABLE` in the multiplicity
denominator. Typed operator commands, PostgreSQL-clock audit, idempotency and
RBAC expose owner freeze, Protocol freeze, Formal Forecast compute and family
evaluation without a generic artifact registrar. These writers can
persist `REJECTED`, `NOT_ESTIMABLE`, `BLOCKED` and `ACCUMULATING` as first-class
results. They do not automatically promote or authorize anything.

The 2026-08-11 isolated working-schema evidence resolution applied migrations
001–056 and evaluated ten declared free-data Provider×Contract×Fact scopes:
BaoStock history Market Data and Adjustment Factor; BaoStock status Trading
Calendar, Listing Status, ST Status, Trading Status and Trading Eligibility;
BaoStock stock-basic Universe Membership; and Tencent current/minute Market Data.
All ten were durably `REJECTED` with
`FORMAL_PROVIDER_EVIDENCE_CEILING_NOT_MET`: no qualified source or typed formal
Provider evidence exists. The same schema contains zero PIT Fact Revision,
Formal PIT Validation, Formal Protocol, Historical Sample qualification,
Locked-OOS consumption, Formal OOS, Calibration qualification, Phase C stage or
Production Admission evidence. This is a negative/absent evidence result, not a
Provider-quality or Alpha conclusion.

Migrations 047–057 add free retrospective evidence, exploratory Research Universe, Portfolio Shadow, engineering access-governance owners, immutable Path Calibration Hypothesis evidence and the fail-closed Phase C owners described above. They do not alter migration 046, which removes reference-only
qualification paths from the current architecture:

- Research Validation PostgreSQL rows cannot be qualified, Production-authorized or claim Formal OOS Authority;
- Historical Samples persist as `UNQUALIFIED` only;
- pure helpers cannot promote Calibration, Entry, Holding/Exit or Strategy Shadow;
- Production Admission has only `BLOCKED`;
- PostgreSQL Model Governance rejects all Production qualification with `PRODUCTION_EVIDENCE_OWNER_RESOLUTION_NOT_IMPLEMENTED`.
- engineering RBAC has no Production Admission or Broker permission and reports authentication as not established.

This is a deliberate fail-closed state. It does not mean the missing qualification work is complete.

## Complexity census

| Measure | Current count | Interpretation |
|---|---:|---|
| Python source files | 597 | broad modular monolith; size alone is not a defect |
| Python test files | 427 | strong contract/replay coverage, with some fixture-heavy history |
| Canonical all-day Runtime | 1 | `CONTINUOUS_RESEARCH` |
| Installed CLI entry points | 6 | one scheduler/operator surface plus five bounded owner/admin tools |
| PostgreSQL migrations | 57 | contiguous, checksummed, forward-only; 046 remains closed while later owner writers fail closed on missing evidence |
| PostgreSQL Authority-schema tables | 194 | exact `EXPECTED_AUTHORITY_TABLES` catalog; includes Authority owners, journals and projections, not 194 independent business Authorities |
| PostgreSQL owner/repository/journal classes | 34 | bounded owners; not competing global Authorities |
| Repository/journal named classes | 49 | includes Protocols, in-memory research stores and compatibility types |
| Artifact/Receipt class names | 84 | immutable contracts across bounded contexts |
| Policy class names | 38 | time, risk, provider, state and research rules |
| Protocol/Port class names | 16 | external/composition seams |
| Qualification-named class types | 14 | contracts and statuses; Phase C owner writers persist fail-closed decisions, while current real Formal qualification evidence remains absent |
| Current canonical docs | 11 | index, four architecture, four status, one runbook and one research registry |
| Normative Constitution docs | 10 | unchanged `00` through `09` |
| Current research registries | 1 | negative/inconclusive results |
| Historical/superseded/archive docs | 2 | archive boundary index plus superseded Constitution implementation-status; detailed history lives in Git |
| Legacy `daily_research` | 10 files / about 1.6k lines | compatibility Readers and identities |
| Legacy `dividend_t` | 49 files / about 23.5k lines | isolated characterization and legacy UI/research |
| Explicit `legacy` and `migration/legacy` | 13 files / about 1.5k lines | adapters, migration and replay only |
| Retired `decision_replay_import` schema | 1 table | immutable historical rows retained by forward-only migrations; no current application writer/Reader |

## Complexity classification

- **Essential:** semantic time, immutable identities, PIT resolution, PostgreSQL fences/CAS, separate Candidate/Signal/Forecast/Decision/Position Authorities, replay, actual-Fill Position derivation.
- **Accidental:** installed executable surfaces are converged; uninstalled research, legacy, backtesting and diagnostic scripts retain local main guards and some fixture-heavy test compositions remain.
- **Legacy:** `daily_research`, `dividend_t`, explicit legacy adapters and their compatibility tests. They are isolated from Canonical composition but still carry maintenance cost.
- **AI-generated:** 273 stale/historical Markdown files, five reference-only promotion functions, a generic Governance binding DTO, an 800-line uncomposed Decision replay library and its 400-line pseudo-Production test seeder were removed in this convergence.

## Evidence ceiling

```text
automatic_order_execution = false
broker_integration_proven = false
free_data_engineering_complete = true
data_engineering_complete = true
research_engineering_complete = true
evaluation_engineering_complete = true
strategy_validation_engineering_complete = true
shadow_engineering_complete = true
operations_engineering_complete = true
governance_engineering_complete = true
entry_model_empirically_validated = false
formal_pit_established = false
formal_oos_alpha_established = false
calibrated = false
entry_qualified = false
holding_exit_validated = false
strategy_shadow_proven = false
production_ready = false
live_broker_authorized = false
```

CI is separate from local verification. If GitHub Actions has not run on the final commit, the only valid statement is `CI_NOT_RUN`.
