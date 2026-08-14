# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Sole current implementation-status document
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations`, `tests`

## Implemented engineering boundary

The system is a PostgreSQL-only modular monolith with one Continuous Research Runtime. It has durable source freeze, Dataset/Feature materialization, Model Governance selection, State/StateSeries/Pool/Candidate, controlled minute/Signal/Forecast work, Research Summary, Canonical Lifecycle mechanics, manual-account Decision support, Research Shadow, prospective outcomes, Panel V2 and Research Validation harnesses. Free-data operation includes an automatic retrospective BaoStock decision/outcome/sample pipeline, a PostgreSQL Historical Registry Reader in the Research/Shadow Forecast composition, a full-A-share exploratory Security Master/Research Universe snapshot, explicit Proxy/Derived/Declared reference semantics, T+1 settlement/enrichment and factor lineage/de-duplication evidence. Research Summary and settlement bind the same Feature Bundle V2 identity used by Signal and Panel enrichment; the legacy static bundle remains its immutable Controlled-package wrapper, not a competing feature Authority.

Phase B engineering also includes daily cross-sectional evaluation science, tie-aware RankIC, label-aware purging/embargo, explicit `NOT_ESTIMABLE`, calibration method harnesses and a PostgreSQL Portfolio Shadow ledger. The legacy multi-session PathForecast still cannot be reused as a T+1 Target Forecast, so that mismatch remains truthfully `NOT_ESTIMABLE`. Phase D adds explicit confidence-interval versus null-test semantics, deterministic statistical simulations, and Target-bound Forecast kernels without changing that identity. Every probability result remains `calibrated=false`. Portfolio Shadow records per-value provenance for market facts and assumptions alongside Cash, Order Intent, Shadow Fill, Shadow Position, NAV, exposure, turnover, cost, capacity, drawdown and attribution while enforcing A-share T+1, 100-share lots, suspension, price-limit and continuous-auction constraints. Append-only Principal/Role/Approval/Audit governance serializes bootstrap and last-Admin invariants; every Continuous CLI invocation is resource-bound and audited, and non-Admin Shadow/recovery mutation requires an exact independent approval. Production-mode mutation is rejected before Journal writes. A recovery audit is available through the same CLI. External authentication is not bound, so the caller-supplied Principal ID is not an authenticated identity proof.

Actual positions derive only from observed manual fills. The system creates no broker order and does not automatically mutate actual positions.

Migration 085 closes the first executable multi-strategy business slice. One
stable registry supplies `OVERNIGHT` and `SWING_STATE` Strategy Versions to a
shared `MultiStrategyRuntime`. The same policy kernel is invoked by one
`STRATEGY_RUNTIME` child of Continuous Research and by the existing Historical
Session Kernel; Replay keeps its origin explicit and recomputes the same action
semantics. Every cycle persists Strategy Runs, complete gate/rejection
attribution, proposals and one simple cross-strategy Portfolio decision. A new
strategy therefore supplies a Strategy Version and policy implementation, not a
new scheduler, database, Candidate owner or Production control plane.

Candidate no longer carries Entry semantics in this path. Overnight emits
short-horizon `ENTER`/`HOLD`/`EXIT`; Swing consumes explicit sleeve state and can
emit `ENTER`/`HOLD`/`ADD`/`REDUCE`/`EXIT`. A model-blocked empty CandidateSet is
persisted and produces `DATA_INSUFFICIENT` runs for both families rather than a
silently missing sample. The cross-strategy Portfolio supports deterministic
Top-K equal/score baselines, budgets, gross/single-name limits and opposing-intent
attribution; it creates no Order, Fill or physical Position.

Strategy sleeves are derived only from immutable allocations of already
persisted observed manual Fills and reconcile to physical quantity. The
multi-horizon Path Outcome kernel and PostgreSQL owner record MFE, MAE,
target-before-stop, time-to-MFE, continuation/failure, post-exit opportunity loss
and avoided drawdown. The executable Outcome→Attribution→Challenger→Qualification
service is scoped by exact Strategy Version, never mutates a Champion and remains
fail-closed. Its write path reloads Proposal/Run/Dataset/Target and feedback
source lineage by exact owner ID/hash/version, rejects caller-asserted positive
qualification flags, and uses a fixed Decimal context for replay-stable
identities. Automatic longitudinal path materialization and feedback scheduling
are not yet part of the historical operator.

Migration 086 completes the account-bound stateful lifecycle on the same
Continuous Strategy child and existing Strategy Shadow owner. Before each
decision, PostgreSQL rebuilds open Strategy sleeve state from effective Fill
allocations, exact Proposal actions and available manual account observations;
it does not reset session age, peak price, add/reduce counters or lineage on
composition restart. Overnight can therefore ENTER, restore and EXIT, while
Swing can ENTER, HOLD, ADD, HOLD, REDUCE and EXIT across sessions. The final
observed EXIT settles one immutable fill-derived realized Strategy Outcome;
retries and concurrent settlement reload the same identity. The older T+1
Shadow Entry path consumes the canonical Overnight Proposal when present and
no longer independently re-decides Entry from Candidate in that scope.

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
The Model reference is resolved by Model Governance into a content-addressed
freeze receipt containing the current lifecycle, Registry version and exact
Registry/Lineage governance actions. `SUSPENDED` or `RETIRED` models fail closed,
and a later terminal transition invalidates downstream owner replay.

Migration 057 freezes one content-addressed multi-target Hypothesis Family per
Formal Protocol. One raw subject/decision-session/outcome-session path can be
unlocked only once across Model, Forecast, Protocol, Dataset, Universe, Target
and Label revisions, while every pre-registered Target may consume its own
observation during that first family unlock. Family evaluation corrects all
Target × metric × observed slice × sensitivity × fold hypotheses together and
retains every predeclared empty fold as `NOT_ESTIMABLE` in the multiplicity
denominator. Typed operator commands, PostgreSQL-clock audit, idempotency and
RBAC expose owner freeze, Protocol freeze, Formal Forecast compute and family
evaluation without a generic artifact registrar. The command actor must equal
the authorized RBAC principal. C4 requires estimable Train and Validation floor
metrics for every Target/fold/sensitivity before evaluating Locked OOS; its C3
record-set comparison filters exactly the frozen Locked-OOS windows. These writers can
persist `REJECTED`, `NOT_ESTIMABLE`, `BLOCKED` and `ACCUMULATING` as first-class
results. They do not automatically promote or authorize anything.

Phase D engineering extends the same owners with an immutable Experiment
Definition inside Formal Protocol V2 and one Target Definition V2 identity from
Forecast through Outcome, Evaluation and Calibration. Inference freezes its
null, benchmark, alternative and method per hypothesis; moving-block sampling
intervals are not reused as null distributions. A deterministic research-model
trainer/executor supports unconditional, linear, raw-logit and
regime-conditioned measure heads. Each measure is independently `AVAILABLE` or
`NOT_ESTIMABLE`; uncalibrated classifier output remains a raw logit. The
mathematical executor can run over exploratory inputs, while the Formal
Forecast writer still requires owner-resolved Formal PIT.

The new Historical Research Runner is resumable/replayable through a PostgreSQL
lease/fence/stage journal and binds Runtime Scope, Experiment and Target
identities. Historical Strategy, Portfolio, Outcome and Performance resolution
follows the exact experiment/session/policy/owner chain; trading date is never
used as owner identity. Full-A Scope remains an exploratory population, not an
Operational Universe bypass. Strategy/Portfolio observations reload exact
owners by ID and hash, bind the factual Outcome session, and persist their
receipt and source bindings into Strategy and Portfolio replay lineage.
Pre-migration-067 Portfolio rows remain readable but `LEGACY_UNBOUND`; they are
not inferred or upgraded into typed evidence. Multi-period performance reports
gross, cost, net, turnover, drawdown, capacity and structured attribution.
Factor coverage, cumulative ablation,
regime/liquidity/market-cap/volatility/theme/industry slices, Strategy Economics,
Portfolio Risk and diagnostic Feedback are content-addressed exploratory
research artifacts. They do not qualify a model or establish economic value.

The Phase D engineering correctness closure is complete:
`PHASE_D_ENGINEERING_COMPLETE`. This marker covers temporal binding, exact
Historical lineage, owner ID/hash integrity, durable Observation lineage,
ordered/variant-specific metrics, separated Strategy execution semantics,
deterministic replay and truthful Runtime boundaries. It is an engineering
status only and does not establish Alpha, Formal PIT, Formal OOS, Strategy
proof, Production readiness or trading authority.

The Phase E Pilot established one real representative historical-evidence
vertical slice.
PostgreSQL remains the sole business Authority for exact owner identity, logical
and physical hashes, Artifact Root locator, schema/version, provenance,
coverage, availability metadata, sessions, experiments and results. The
content-addressed Artifact Root stores immutable Raw and Normalized Parquet
packages only. Reads start from an exact PostgreSQL owner and verify every
manifest, checksum and physical package hash; there is no directory scan,
latest-file selection or implicit fallback. Publication is staging, validation,
logical hashing, atomic installation, owner registration and exact reload.
Raw partition schema v2 preserves full provider request intervals while v1
owners remain immutable and replayable.

The frozen BaoStock corpus requested raw-unadjusted Daily and 5-minute history
for seven symbols over 2023-01-01 through 2025-12-31. Six liquid A-share stocks
were observed; all six annual/timeframe requests for `510300.SH` returned an
empty Provider result. The corrected Raw owner contains 42 successful Provider
requests and 213,738 source rows. Its exact Normalized child contains 4,362
Daily and 209,376 5-minute rows. Listing status is absent for all 213,738 rows;
minute ST status is absent for 209,376 rows. Retrieval time remains the true
2026 archive time; historical trading dates are only retrospective event time.
Every artifact and result remains `EXPLORATORY` and `PIT_INCOMPLETE`.

The Pilot run actively materializes 667 historical Decision Sessions
from 2023-04-03 through 2025-12-30 and uses 2025-12-31 only for T+1 Outcome. It
persists 667 exact owners for each of 13 Feature/State/Pool/Candidate/Signal/
Forecast/Strategy/Portfolio/Outcome/Panel kinds, producing 4,002 panel samples
with zero missing T+1 10:30 targets. Decision components have zero post-decision
source-time violations; Outcome owners have zero non-T+1 time violations;
component source bindings have zero cross-run contamination. A real interrupted
seven-receipt process resumed to the same terminal corpus, and exact replay is
deterministic.

The frozen cumulative ablation does not establish general Alpha. Price-only
RankIC is -0.01652 and net return is -0.001165 after an average 0.002100
engineering-assumption cost. Adding Volume and Market Regime improves net by
0.000070 and 0.000196 respectively, but both remain negative. Theme reduces net
by 0.000350 and Dynamic Pool reduces it by another 0.000228. The resulting full
effective chain has RankIC 0.00252, gross 0.000623, cost 0.002100, net -0.001477,
turnover 0.2057 and maximum drawdown -0.7309. ETF and Capital have zero observed
factor values. Canonical Theme/Capital gates reject all 4,002 Candidate rows, so
Candidate, Signal and Forecast also have zero observed factor values. Their
incremental lifts are durably `NOT_ESTIMABLE`, never represented as zero.

All six T+1 execution checkpoints are net negative. Mean checkpoint net ranges
from OPEN -0.001936 to 11:30 -0.000693; 19,953 of 24,012 symbol/checkpoint
economics rows are estimable and all estimable rows reconcile `gross - cost =
net`. The average capacity ceiling is approximately CNY 352.6 million, but
cost, fillability, impact and capacity are engineering assumptions rather than
empirically calibrated execution facts. Diagnostic slices are positive in
`RISK_ON` and High Volatility and negative in `RISK_OFF`, Low and Normal
Volatility; the one-session `EXTREME_RISK` slice is inconclusive. All names are
High Liquidity, Theme is one global exploratory proxy, and Market Cap/Industry
slices are `NOT_ESTIMABLE`.

The owner-resolved fixed-ridge challenger reloads Feature and Target owners
without a caller matrix. It uses 3,198 earlier training and 804 later validation
samples. Validation MSE 0.00024454 is slightly below the mean-baseline MSE
0.00024591 and validation RankIC is 0.05842, so its exploratory registry result
is `POSITIVE`. This is not a Formal OOS, calibrated, model-qualified or economic
value claim. Negative, inconclusive and not-estimable findings are persisted in
the same PostgreSQL Research Evidence registry.

Phase E2 now adds an expanded frozen CSI 300 cross-section without changing the
Pilot identities or qualification ceiling. One real effective-dated historical
constituent owner supplies 300 equities; `000300.SH` and `510300.SH` supply real
index/ETF context. A PostgreSQL partition access index resolves only exact
timeframe/date/symbol-bucket Parquet partitions. Selected files are checksum
verified, predicates and a seven-column projection are pushed into Arrow, and
bounded batches reconstruct and revalidate exact record identities. Decision
materialization retains one Daily projection and an LRU of previous/current/T+1
minute windows instead of loading the entire package object graph.

The Phase E2 corpus contains 110,845 Daily and 302,928 5-minute records across
302 instruments and 256 normalized partitions. Its 19 Decision Sessions persist
5,700 Panel rows; ten T+1 10:30 targets remain explicitly missing and 5,690 are
estimable. Historical listing date/status, listing age, ST and trading status
are resolved for all 300 equities. Delisting is projected by effective date and
tested, although no member of this live cohort has a delisting fact. Industry
remains `UNKNOWN` and market cap `NOT_ESTIMABLE`; current classification and
synthetic share facts are never projected backwards. The frozen Runtime Scope
is correctly an `INDEX` selector, not `FULL_A`.

The expanded run consumes `000300.SH` in Market Regime and `510300.SH` in Theme;
Capital records existing price/volume model inference for 300 symbols without
claiming hidden institutional intent. Candidate observations cover all 5,700
rows and Canonical Signal/Forecast observations occur on the unchanged frozen
methodology. Exact ablation and economics findings are recorded in the
[Phase E2 report](../references/Phase-E2-Historical-Evidence-Expansion-Report.md).
An interrupted public CLI run resumed to 19/19 sessions and 114/114 stage
receipts with zero swap, and exact replay matches. A separate uninterrupted
PostgreSQL execution produces identical ordered Session, Receipt, Component,
source-binding, Evidence and metric hash sets. All Phase E2 facts remain
`EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_OOS=false` and `CALIBRATED=false`.

Phase E3 now adds real longitudinal engineering evidence without rewriting E2.
One exact-range Timeline maps 127 queried trading sessions to 29 distinct CSI
300 constituent owners. Each Decision uses the active 300-member cohort; the
308-stock union changes by one member on 2025-03-10 and seven members on
2025-06-16. A delisted member is excluded at its lifecycle effective date even
before the next Provider cohort removes it. Current membership and current
classification are never projected backwards.

The normalized corpus contains 1,954,644 real Daily/5-minute observations for
309 of 310 expected instruments from 2024-06-03 through 2025-07-14. The sole
unobserved instrument is the frozen `510300.SH` ETF: all BaoStock requests
succeeded but returned no rows. The 126-session Decision run is complete with
756 receipts and 1,638 exact components. Decision materialization peaks at
1,412,218,880 bytes RSS with zero swap. Streaming Evidence processes four
components and at most 299 observations at a time, completing in 66.40 seconds
at 378,732,544 bytes peak RSS. Corpus acquisition still peaks at
5,396,152,320 bytes and remains the most important scale-engineering gap.

The consumed Historical Security Facts owner contains 8,909 Industry, 921
published share-capital, 229 adjustment and 609 dividend/split/rights rows.
Industry is present on all 37,800 Panel rows; Decision-time market-cap buckets
cover 19,022 rows and remain `NOT_ESTIMABLE` on the rest. One conflicting
dividend response is a durable interval gap. The frozen raw-return experiment
excludes 2,082 six-checkpoint labels crossing a known action or that gap instead
of calculating contaminated returns.

The long-window result does not establish Alpha. ETF has zero observations,
Capital is `DATA_INSUFFICIENT` in all sessions, all 37,800 Candidates are
rejected, and Signal/canonical Forecast are never emitted. The unchanged
Forecast sample floor is not reached because there is no upstream Signal, not
because it was lowered. Price, Volume, Regime, Theme and Dynamic Pool are
estimable, but Volume, Theme and Dynamic Pool have negative incremental lift;
Regime has a small positive lift while the chain remains net negative. All six
Strategy checkpoints are gross-positive but net-negative after the versioned
engineering-assumption cost. The full ranking path is also negative, with net
-0.003781 and maximum drawdown -0.39964.

The owner-resolved fixed-ridge challenger is independently estimable on 29,729
earlier training and 7,646 later validation observations. Its small MSE
improvement and 0.015405 validation RankIC are exploratory temporal evidence,
not canonical Forecast, Formal OOS, Calibration or model qualification. Exact
owners, missingness, period/regime slices, economics and current recovery proof
are recorded in the
[Phase E3 report](../references/Phase-E3-Longitudinal-Historical-Evidence-Report.md).
The interrupted/resumed and independently uninterrupted executions have
identical ordered Run, Session, receipt, component, component-binding, Evidence,
metric and Evidence-binding digests; exact replay independently recomputes all
126 sessions with zero mismatch.

Canonical source acquisition is exposed through `SourceFreezeService`; the
DailyLoop is retained only as its identity-compatible adapter. Controlled
package recovery and Feature recovery use exact PostgreSQL/receipt locators and
hash verification rather than directory scanning. Migration 065 requires new
Controlled package rows to use the global `artifact-root-v1` locator contract;
legacy un-namespaced rows remain immutable and fail closed. Lifecycle stages
are explicitly partitioned into composed Research Decision Support, composed
Manual Account Observation and contract-only Position Review stages.

The 2026-08-11 isolated working-schema evidence resolution applied migrations
001–057 and evaluated ten declared free-data Provider×Contract×Fact scopes:
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

Migrations 047–084 add free retrospective evidence, exploratory Research Universe,
Portfolio Shadow, exact Locked-OOS/PIT lineage, Phase C owners, Phase D research
journals and the longitudinal Historical Corpus owners. Migration 085 adds the
multi-strategy business closure; migration 086 adds its observed-Fill state and
realized-Outcome closure. They do not alter migration
046, which removes reference-only
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
| Python source files | 658 | broad modular monolith; size alone is not a defect |
| Python test files | 481 | strong contract/replay coverage, with some fixture-heavy history |
| Canonical all-day Runtime | 1 | `CONTINUOUS_RESEARCH` |
| Installed CLI entry points | 6 | one scheduler/operator surface plus five bounded owner/admin tools |
| PostgreSQL migrations | 86 | contiguous, checksummed, forward-only; 046 remains closed while later owner writers fail closed on missing evidence |
| PostgreSQL Authority-schema tables | 270 | exact `EXPECTED_AUTHORITY_TABLES` catalog; includes owners, journals and projections, not 270 independent business Authorities |
| PostgreSQL owner/repository/journal classes | 34 | bounded owners; not competing global Authorities |
| Repository/journal named classes | 49 | includes Protocols, in-memory research stores and compatibility types |
| Artifact/Receipt class names | 84 | immutable contracts across bounded contexts |
| Policy class names | 38 | time, risk, provider, state and research rules |
| Protocol/Port class names | 16 | external/composition seams |
| Qualification-named class types | 14 | contracts and statuses; Phase C owner writers persist fail-closed decisions, while current real Formal qualification evidence remains absent |
| Current canonical docs | 11 | index, four architecture, four status, one runbook and one research registry |
| Normative Constitution docs | 10 | unchanged `00` through `09` |
| Current research registries | 1 | negative/inconclusive results |
| Historical/superseded/archive docs | 1 | archive boundary index only; detailed plans and superseded status snapshots live in Git |
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
research_model_runtime_available = true
phase_d_engineering_complete = true
phase_e_representative_corpus_complete = true
historical_corpus_replay_verified = true
multi_strategy_runtime_engineering_complete = true
overnight_and_swing_shared_semantics_verified = true
multi_horizon_path_kernel_engineering_complete = true
automatic_longitudinal_path_materialization = false
exploratory_alpha_established = false
strategy_economic_value_established = false
formal_model_qualified = false
formal_oos = false
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
