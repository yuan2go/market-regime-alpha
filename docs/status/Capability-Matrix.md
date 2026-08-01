# Current Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical implementation-status matrix  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Gap-Register.md, ../audit/Current-Main-Code-Audit-2026-08-01.md, ../architecture/09-Platform-Architecture-V2.md, ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md  
> **Code Evidence:** `main@e183fdac285786ed448c835e65c99dc67189c2b9`  
> **Status Rule:** `IMPLEMENTED` describes code mechanics. `VERIFIED_CURRENT_HEAD` requires observed checks on the exact current commit. Historical checkpoint PASS records are not current-HEAD verification.

| Capability | Status | Code evidence | Verification evidence | Runtime/evidence ceiling | Primary blocker | Next action |
|---|---|---|---|---|---|---|
| Core identity and semantic time | IMPLEMENTED | `core/identity.py`, `core/time.py`, `core/status.py` | Historical unit/static gates | Engineering contracts only | Current HEAD full gate absent | Preserve and include in current CI |
| Artifact canonicalization and envelope | IMPLEMENTED_AND_HISTORICALLY_VERIFIED | `evidence/**` | Reader, checksum and tamper tests on prior checkpoints | Content integrity, not source authenticity | No signatures/trusted runtime identity | Add signed artifact/operator identity for production |
| SourceManifest and data quality | IMPLEMENTED_EXPLORATORY | `data/source_manifest.py`, `data/daily_quality.py` | Historical quality and missingness tests | Public-source exploratory authority | Qualified availability/PIT evidence absent | Establish controlled provider evidence |
| Trading calendar and PIT contracts | IMPLEMENTED_CONTRACTS | `data/trading_calendar.py`, `universe/**` | Historical calendar/PIT contract tests | Formal provider PIT not established | Qualified provider inventory | Validate against formal historical source |
| Public composite provider | IMPLEMENTED_EXPLORATORY | `data/providers/public_composite/**` | Archive/replay/stage tests on prior checkpoints | Real off-window run reached `DATA_BLOCKED` | 14:55 controlled runtime unavailable | Execute sustained controlled-window runs |
| Xuntou provider path | IMPLEMENTED_ADAPTER_BLOCKED_EXTERNAL | `research/xuntou_pit_v4_*`, `tools/xuntou/**` | Contract/preflight tests | No qualified real bundle | XtQuant runtime and exported bundle | Produce and qualify real V4 evidence |
| Operational stock Universe | PARTIAL_SMOKE_ONLY | `universe/daily_exploratory.py` | 20-symbol smoke tests | Not a 100–300 symbol operating pool | Approved PIT membership/liquidity source | Build versioned operational Universe artifact |
| ETF Universe | NOT_IMPLEMENTED_CANONICAL | No canonical ETF Universe owner | None | ETF observations only appear as supplemental evidence | ETF identity, mapping and PIT membership | Implement separate ETF Universe and selection policy |
| Feature materialization | IMPLEMENTED_BASELINE | `features/**` | Historical feature/materialization tests | Baseline features only | Qualified observations and expansion | Add validated features through registered definitions |
| B0 Candidate baseline | IMPLEMENTED_AND_HISTORICALLY_VERIFIED | `candidates/baselines.py`, Prediction adapters | Prior equivalence and replay tests | Baseline rank, not probability | Formal OOS absent | Preserve frozen baseline and evaluate formally |
| B1 Candidate baseline | IMPLEMENTED_AND_HISTORICALLY_VERIFIED | `candidates/composite_baseline.py`, Prediction adapters | Prior equivalence and replay tests | Baseline rank, not probability | Formal OOS/model winner absent | Preserve frozen baseline and evaluate formally |
| Daily Runtime Journal | IMPLEMENTED_SQLITE | `application/daily_loop/**` | Prior restart/idempotency tests | Single-machine recoverability | No distributed leases/Saga | Integrate into ShadowRun control plane |
| Exploratory Daily Loop | IMPLEMENTED_EXPLORATORY | `application/daily_loop/runner.py`, daily CLI | Prior single/ten-session replay evidence | Smoke pool and exploratory providers | Real 14:55 successful archive absent | Run controlled daily shadow schedule |
| Daily Decision Artifact | IMPLEMENTED | `daily_decision/artifact.py`, Readers | Prior exact-file/checksum/replay tests | Research decision artifact only | Current HEAD full gate absent | Include in exact-commit CI |
| Candidate Recommendation | IMPLEMENTED_PRESENTATION_ONLY | `daily_decision/recommendation.py` | Prior projection tests | Not trading authority | No validated Entry Model | Keep separate from Entry and orders |
| Entry plumbing | IMPLEMENTED_NON_ENTRY | `daily_decision/entry.py` | Gate tests on prior checkpoints | Emits `REJECT` or `WAIT_CONFIRMATION`, never `ENTER` | Entry model not validated | Define and validate independent Entry protocol |
| Outcome settlement and DailyReview | IMPLEMENTED_EXPLORATORY | `daily_decision/outcome*.py` | Prior settlement/replay tests | MR1 next-session 10:30 research outcome | Qualified runtime sample absent | Accumulate immutable real shadow outcomes |
| Market Regime V0 | IMPLEMENTED_EXPLORATORY | `research/market_regime/**` | Deterministic fixture tests | Explicit unvalidated thresholds | Historical qualified market observations | Build walk-forward validation protocol |
| Theme Rotation V0 | IMPLEMENTED_EXPLORATORY | `research/theme_rotation/**` | Deterministic fixture tests | Direct daily classification, not validated lifecycle state | PIT theme mappings/history absent | Add lifecycle/hysteresis research and validation |
| Capital Evolution V0 | IMPLEMENTED_INFERRED_EXPLORATORY | `research/capital_evolution/**` | Deterministic fixture tests | Observable-proxy inference, not hidden intent fact | Qualified Theme/ETF/capital evidence absent | Build historical proxy evidence and ablations |
| Candidate Discovery V2 | IMPLEMENTED_EXPLORATORY | `research/candidate_discovery/**` | Gate/rank/reconciliation tests on prior checkpoints | CandidateSet is not Recommendation | Qualified Theme/Capital inputs | Evaluate incremental value over B0/B1 |
| Research Layer Artifact and replay | IMPLEMENTED_EXPLORATORY | `research/platform_v2/**`, `application/research_layer/**` | Prior exact-file/Reader/replay tests | Fixture/archive research authority | Current operating input bundle unavailable | Run from qualified operational evidence |
| Operational Research Bridge | IMPLEMENTED_FAIL_CLOSED | `application/operational_research/**` | Prior lineage/missingness/idempotency tests | Requires complete Daily and supplemental artifacts | No qualified supplemental producer | Implement H6 composite evidence and producers |
| Signal Engine V1 | IMPLEMENTED_EXPLORATORY | `signals/**` | Prior factor/time/checksum/replay tests | Confirmation score, not Entry | Parameters not validated | Add incremental-value and OOS validation |
| Multi-horizon PathForecast | IMPLEMENTED_UNCALIBRATED | `forecasting/**`, `strategies/entry/**` | Prior path/ambiguity/quantile tests | No calibrated probability | Qualified historical path sample absent | Implement H9 validation/calibration infrastructure |
| Model Registry domain | IMPLEMENTED | `platform/model_registry.py` | Historical domain tests | In-memory validator available | DailyLoop creates local registry | Route runtime through governed repository |
| Model/Experiment SQLite governance | IMPLEMENTED_SQLITE | `platform` repositories/migrations | Prior CAS/idempotency/restore tests | Local/test operational authority | PostgreSQL parity and runtime integration | Integrate DailyLoop and add repository contract suite |
| TradingOpportunity lifecycle | IMPLEMENTED_SQLITE_EXPLORATORY | `decision/opportunity.py`, repositories | Prior lifecycle/CAS/restore tests | Human decision support | Auth/operating policy absent | Add authenticated operator workflow |
| TradingThesis lifecycle | IMPLEMENTED_SQLITE_EXPLORATORY | `decision/thesis.py`, repositories | Prior lifecycle/CAS/restore tests | Human-approved thesis only | Artifact-derived health absent | Implement H5 Thesis-health builder |
| Portfolio/Risk V1 | COMPATIBILITY_ONLY | `portfolio/lifecycle.py`, `services.py` | Historical tests | Allocation-local and caller-input compatibility path | Not complete-account authority | Retain Reader compatibility only |
| H1 complete-account Portfolio/Risk | IMPLEMENTED_SQLITE_EXPLORATORY | `portfolio/account_authority.py`, `sqlite_account_authority.py`, migration 005 | Prior H1 focused/full records | Synthetic/manual account evidence | Validated limits and external account authority | Use H3 position-authoritative entry for new work |
| H2 Thesis-to-Outcome trace | IMPLEMENTED_SQLITE_EXPLORATORY | `execution/position_book.py`, traceability repositories, `evaluation/traceability.py`, migration 006 | Prior H2 focused/full records | Manual Fill trace, not broker truth | Multi-sleeve and external reconciliation absent | Preserve book identity and add reconciliation |
| H3 A-share T+1 Position authority | IMPLEMENTED_FILL_CALENDAR_DERIVED | `position/authority.py`, position-authoritative risk service | Prior H3 focused/full records | Human Fill plus synthetic/typed calendar/status | Qualified statement/status evidence absent | Integrate real account/status reconciliation |
| H4 increasing/reducing risk separation | PARTIAL_BROKEN_CURRENT_MAIN | `portfolio/risk_routes.py`, migration 007, H4 test file | No current passing evidence; static missing imports/modules | Domain gate exists, durable application route incomplete | Missing `sqlite_risk_routes.py`, Repository, Service, exports | Complete integration and rerun full gate |
| Manual execution ledger | IMPLEMENTED_SQLITE_MANUAL_ONLY | `execution/manual.py`, `sqlite_repository.py`, migration 004 | Prior append-only/correction/restart tests | Human-recorded evidence only | Authentication and broker reconciliation | Add authenticated recording and statement matching |
| Fill append-only authority | IMPLEMENTED_LOCAL | `manual_fills`, SQL triggers | Prior mutation/correction tests | Immutable local ledger, not broker Fill | External source authority absent | Add external receipt and reconciliation evidence |
| Position projection | IMPLEMENTED_FILL_DERIVED | `position/authority.py` | Prior FIFO/correction/replay tests | Projection of recorded Fill | External statement reconciliation absent | Add reconciliation state machine and operator workflow |
| Holding and Exit models | IMPLEMENTED_EXPLORATORY_ONE_SHOT | `position/lifecycle.py`, assessment models | Prior assessment/replay tests | Configurations unvalidated; not durably scheduled | H5 and H7 absent | Derive health, then persist operations |
| TradeOutcome and attribution | IMPLEMENTED_DIAGNOSTIC | `evaluation/**` | Prior outcome/trace/review tests | Diagnostic, not causal Alpha proof | Qualified closed-trade sample absent | Accumulate shadow sample under frozen protocol |
| Rolling scorecard | IMPLEMENTED_DIAGNOSTIC | `evaluation` scorecard/review | Prior deterministic tests | Cannot auto-promote models | No approved evaluation sample | Keep promotion separated and governed |
| Legacy Dividend-T strategy | LEGACY_OPERATIONAL_DEMO | `dividend_t/**` | Legacy tests and local behavior | Separate authority model | Mixed responsibilities and mutable inputs | Do not promote into canonical lifecycle |
| Legacy FastAPI Dashboard | LEGACY_ONLY | `web/dividend_t_app.py` | No production security evidence | Can use static fallback; not Reader-backed | Auth and canonical read model absent | Replace with QuantDesk over verified artifacts |
| APScheduler jobs | LEGACY_ONLY | `dividend_t/scheduler.py` | Minimal factory behavior | No durable job receipts/recovery | H8 ShadowRun absent | Build recoverable scheduler/control plane |
| QMT/PTrade adapters | PLACEHOLDER_SAFE_FAIL | `dividend_t/brokers.py` | Explicit unavailable behavior | Refuses live account/order operations | Vendor runtime and separate authorization | Defer until sustained shadow evidence |
| Authentication and RBAC | NOT_IMPLEMENTED_PRODUCTION | No confirmed canonical owner | None | `actor` is a string, not authenticated identity | Role/permission model absent | Design operator, approver and reconciliation roles |
| Metrics, tracing and alerts | NOT_IMPLEMENTED_PRODUCTION | Reason codes/artifacts only | None | No operational observability stack | H8 absent | Add stage metrics, trace IDs and alerts |
| PostgreSQL lifecycle parity | NOT_IMPLEMENTED | Optional dependency only | None | SQLite local/test authority | Repository parity and deployment | Implement contract-tested PostgreSQL adapters |
| Shadow Operations | NOT_IMPLEMENTED | No `ShadowRun` owner | None | No sustained run claim | H4–H7 and control plane | Implement H8 after dependency closure |
| Formal PIT/OOS Alpha | NOT_ESTABLISHED | Research protocols and negative results only | No current formal winning run | No return promise or model authority | Qualified future data and locked protocol | Implement H9 and run formal studies |
| Live broker execution | NOT_AUTHORIZED_NOT_IMPLEMENTED | Placeholder adapters reject orders | Safe-fail behavior only | No trading authority | Security, reconciliation, kill switch and approval | Separate future architecture decision |

## Current-head verification summary

```text
CURRENT_HEAD = e183fdac285786ed448c835e65c99dc67189c2b9
HISTORICAL_CHECKPOINT_GATES = AVAILABLE
CURRENT_HEAD_GITHUB_ACTIONS = NOT_OBSERVED
CURRENT_HEAD_COMMIT_STATUS = NOT_OBSERVED
CURRENT_HEAD_INDEPENDENT_FULL_TEST = NOT_RUN_IN_AUDIT_ENVIRONMENT
CURRENT_HEAD_STATIC_COLLECTION_BLOCKER = H4_MISSING_IMPORTS_AND_MODULE
```

The first engineering priority is to restore a green current baseline. No later capability may use historical checkpoint test counts as evidence for current HEAD.
