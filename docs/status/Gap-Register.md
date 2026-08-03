# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-03
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Capability-Matrix.md, ../audit/H4-Risk-Route-Delivery.md, ../audit/Current-Main-Code-Audit-2026-08-01.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** `b91e57d7ca52864a56b5e592bb4496b546b7b6fc`
> **Ordering Rule:** Fix current-baseline correctness before adding capabilities. Engineering mechanics, operating evidence, model validation and production admission are separate exit conditions.

## 1. Immediate P0 gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Reproducible dependency set | P0 | Dependencies use lower bounds and no confirmed lockfile is present | Select one package workflow | Clean Python 3.12 environment installs from a committed lock and reproduces the full gate |
| CI enforcement | P1 | Workflow now covers Python 3.12 install, docs, pytest, Ruff, configured mypy and package build on push/PR; no remote branch result or required-check policy was observed in this delivery | Push branch and maintain repository settings | Draft PR checks pass and protected branches require the complete workflow |

## 2. Pre-Shadow hardening gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| H5 Artifact-derived Thesis health | P1 | Holding/Exit callers can provide signal/theme/capital support state instead of deriving it from verified source artifacts | Green H4 baseline and explicit health configuration | Builder accepts only verified artifact references/config, derives health deterministically and reproduces the same identity on replay |
| H6 composite operational evidence | P1 | Operational bridge combines a Daily SourceManifest with supplemental evidence but records historical evidence kind and flat lineage; no composite owner exposes both source authorities cleanly | H5 input requirements and current bridge contracts | Composite manifest/index preserves both original manifests, per-field authority and DecisionTime without eligibility inflation |
| H4.5 reducing-decision execution bridge | P1 | H4 persists a permitted decision but intentionally does not create ManualTrade or Fill | H4, H6 and explicit execution authorization design | ManualTrade references a fresh permitted decision, rechecks latest sellability/position version, records authenticated confirmation and preserves partial/cancel/redecision history without broker authority |
| H7 durable Holding/Exit operations | P1 | Holding/Exit assessments are computed in one-shot review flows; no append-only schedule, blocked state, acknowledgement or durable projection | H5 health builder and H6 evidence | Repository supports CAS, idempotency, restart, rebuild, due/blocked/acknowledged state and migration isolation |
| H8 recoverable ShadowRun | P1 | Daily research, operational research, Signal/Path, Decision, Risk, Fill and Review are separate CLIs; no whole-lifecycle run owner exists | H4–H7 | ShadowRun has stage receipts, retries, resume, deadlines, operator acknowledgement, metrics, alerts and deterministic replay |
| H9 Signal/Path validation infrastructure | P1 | Signal and PathForecast mechanics exist with explicit assumptions, but no formal incremental-value, calibration or locked OOS infrastructure | Qualified historical data and H8 artifact production | Purged walk-forward, embargo, controls, calibration, sensitivity and frozen OOS protocols pass leakage checks |
| Runtime governance integration | P1 | Persistent Model/Experiment repositories exist, but DailyLoop creates a local in-memory `ModelRegistry` for B0/B1 | Green baseline and repository ownership decision | Runtime loads approved immutable model/config references from governance authority and cannot bypass transitions/access budgets |
| PostgreSQL repository parity | P1 | Lifecycle persistence is SQLite local/test authority | Stable Repository protocols and contract suite | PostgreSQL adapters pass the same concurrency, idempotency, reconstruction and migration contract tests |

## 3. Data and operational evidence gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Controlled 14:55 public runtime | P0-EXTERNAL | Public acquisition stages exist; latest real run was outside the historical DecisionTime and correctly became `DATA_BLOCKED` | Controlled scheduling and provider availability | Sustained exact-window archives reach `OUTCOME_PENDING` and replay with stable hashes |
| Qualified Xuntou V4 input | P0-EXTERNAL | Adapter/preflight/evidence contracts exist; no qualified real XtQuant bundle has passed | Windows XtQuant exporter and source inventory | Real bundle passes qualification and same-pipeline comparison without authority promotion |
| Operational stock Universe | P1 | Runtime uses a fixed 20-symbol smoke pool | Successful provider archive and approved PIT membership/liquidity source | Versioned 100–300 symbol Universe accounts for every inclusion/exclusion and replays identically |
| Canonical ETF Universe | P1 | ETF observations/mappings are supplemental only; no ETF Universe, tracking-index identity or primary/alternative policy | ETF reference data and PIT mapping | Separate immutable ETF Universe and eligibility artifact supports replay and delisting/duplication rules |
| PIT theme membership | P1 | Bridge requires full membership coverage, but no qualified daily producer exists | Theme taxonomy and effective-dated source | Every symbol’s primary/supporting membership is available by DecisionTime and versioned |
| Theme/ETF mapping | P1 | Supplemental contract requires exact mapping coverage; no operational producer exists | ETF Universe and theme taxonomy | Every proxy mapping has effective time, source lineage and deterministic Reader |
| Theme and Capital observations | P1 | V0 models run from typed fixtures/supplemental artifacts | Qualified market/ETF/symbol history | Daily materializer produces complete decision-time observations with missingness and coverage reports |
| External account authority | P1 | H1 snapshots and H3 positions are based on explicit/manual evidence | Broker statement/import boundary | Complete cash/position statement is authenticated, versioned and reconciled before Risk |
| Fill reconciliation | P1 | Fill is append-only human-recorded evidence, not broker truth | External execution statement and operator roles | Every manual Fill is matched, disputed or corrected through an append-only reconciliation workflow |

## 4. Research and model gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Real Entry Model | P1 | Canonical Entry emits only `REJECT` or `WAIT_CONFIRMATION`; `ENTER` is intentionally absent | Qualified Candidate/Signal/path evidence and validation protocol | Independent Entry model has frozen inputs, thresholds, target, cost assumptions, calibration and OOS result |
| Entry authority namespace convergence | P1 | Canonical `daily_decision` Entry cannot emit `ENTER`, while older `daily_research.EntryState` still defines an ENTER-capable contract | Reader/producer inventory and compatibility decision | Legacy ENTER-capable artifacts are explicitly historical/isolated or migrated; no runtime can confuse them with canonical Entry authority |
| Market Regime validation | P1 | Deterministic weighted gate with explicit thresholds | Qualified historical observations | Walk-forward comparison proves usefulness for exposure/gating versus simpler controls |
| Theme lifecycle semantics | P1 | Theme Rotation V0 is direct per-day classification | PIT history and transition protocol | Versioned state machine includes persistence, duration, hysteresis and validated decay behavior |
| Capital Evolution validation | P1 | Observable-proxy inference exists | Theme/ETF/symbol historical observations | Ablation and incremental-value tests show what the inferred score contributes beyond price/volume baselines |
| Candidate incremental value | P1 | Market/Theme/Capital gates feed Candidate Discovery over B0/B1 factors | Qualified historical archive | Frozen comparison reports hit rate, return, drawdown, turnover and overlap versus B0/B1 controls |
| PathForecast calibration | P1 | MFE/MAE, barriers and quantiles exist without validated profile or event probability | H9 and qualified samples | Horizon/barrier profile is selected only from training data and evaluated on locked OOS |
| Risk parameter validation | P1 | Risk constraints are explicit engineering fixtures | Shadow account/position/outcome sample | Limits are approved through a versioned protocol with sensitivity and incident review |
| Holding/Exit parameter validation | P1 | Actions and contracts exist with synthetic profiles | H5/H7/H8 and closed shadow trades | Frozen configurations are evaluated by regime/theme/liquidity slices without causal overclaim |
| Formal PIT/OOS Alpha | P0-RESEARCH | No model has current formal winning evidence | Qualified data, H9 and locked protocol | Formal study publishes immutable protocol, access history, results and negative outcomes; no data reuse violation |

## 5. Product, security and operations gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Authentication and RBAC | P1 | Domain `actor` is a string, not an authenticated principal | Operator/API architecture | Roles govern approval, risk, Fill, reconciliation, model transition and incident actions |
| Artifact signatures | P2 | SHA-256 proves content consistency but not trusted producer identity | Key management and authenticated runtime | Artifacts carry verifiable producer/operator signatures and rotation/revocation rules |
| Metrics, tracing and alerts | P1 | Reason codes and artifacts exist; no production telemetry stack | H8 | Stage latency/failure/data-quality/risk/reconciliation metrics, trace IDs and actionable alerts are operational |
| Backup and recovery | P1 | Append-only histories and artifacts are reconstructible, but no production recovery evidence exists | PostgreSQL/filesystem deployment | Point-in-time restore, artifact restore and reconciliation drills are documented and tested |
| QuantDesk read model | P2 | Canonical lifecycle is CLI-driven; Legacy FastAPI is not Reader-backed | Stable H8 commands/queries | UI reads verified artifacts and durable projections without recomputing decisions |
| Legacy Dashboard isolation | P1 | `web/dividend_t_app.py` can use static fallback and Legacy strategy/risk paths | QuantDesk replacement or explicit isolation | Legacy endpoint is local-only/clearly labelled and cannot be confused with canonical authority |
| Broker adapter architecture | DEFERRED | QMT/PTrade adapters safely reject live operations | Sustained shadow evidence, security review and separate approval | Versioned intent port, external receipts, reconciliation, permissions and kill switch pass dedicated admission |

## 6. Delivered engineering mechanics retained

The following are not open implementation gaps, although their operating/model evidence remains limited:

- immutable content-addressed artifacts and semantic Readers;
- SourceManifest and fail-closed DataQuality;
- B0/B1 PredictionRuns and candidate baselines;
- recoverable exploratory DailyLoop;
- Market/Theme/Capital/Candidate research mechanics;
- Signal and uncalibrated PathForecast mechanics;
- SQLite Opportunity/Thesis lifecycle;
- H1 complete-account Portfolio/Risk;
- H2 Thesis-scoped authority trace;
- H3 Fill/calendar-derived T+1 Position;
- H4 reducing-risk domain, SQLite persistence, idempotency, strict restoration and decision-only CLI;
- append-only manual Fill ledger;
- exploratory Holding/Exit, TradeOutcome and rolling diagnostics.

Delivered mechanics must not be upgraded to production, Alpha or trading-authority claims without the separate exit conditions above.

## 7. Required implementation order

```text
P0 lockfile and remote CI enforcement
→ H5 Artifact-derived Thesis health
→ H6 composite operational evidence
→ H4.5 reducing-decision/manual-execution bridge
→ H7 durable Holding/Exit
→ H8 recoverable ShadowRun
→ qualified 14:55/Universe/Theme/Capital/account evidence
→ H9 formal validation infrastructure
→ sustained shadow evidence
→ security/PostgreSQL/observability/QuantDesk
→ separately approved broker architecture
```

Do not start production UI or live broker integration while the ShadowRun/evidence/validation layers remain incomplete. H4 completion does not authorize order creation.
