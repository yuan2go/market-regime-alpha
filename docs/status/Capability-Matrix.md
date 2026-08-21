# Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Current capability/evidence matrix  
> **Repository Baseline:** `main@fc373696990ccdffe5e46a39778fdfedac3e0308`
> **Strongest Research Evidence Revision:** `0d1a5a8` (WP-ALPHA-RESEARCH-01)
> **Last Updated:** 2026-08-21
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

## Status vocabulary

| Status | Meaning |
|---|---|
| `PROVEN` | The declared capability/claim has direct applicable runtime or empirical proof at the stated scope. |
| `IMPLEMENTED_AND_WIRED` | Code exists and is part of the canonical execution path, but the broader business/research claim may remain unproven. |
| `IMPLEMENTED_NOT_PROVEN` | Code/owner exists, but applicable runtime or empirical proof is insufficient. |
| `IMPLEMENTED_NOT_WIRED` | Capability exists but is not part of the canonical path. |
| `ENGINEERING_ONLY` | Correctness/infrastructure mechanics exist; no empirical Alpha/qualification claim follows. |
| `SCAFFOLDING` | Deliberate incomplete foundation with no claim of completion. |
| `BLOCKED_BY_EVIDENCE` | Engineering can proceed or is ready, but the required external/prospective/formal evidence does not exist. |
| `LEGACY` | Retained only for compatibility/replay/migration consumers. |
| `MISSING` | Required target capability is absent. |
| `DEFERRED` | Deliberately outside the current Alpha Proof program. |

## Current capability map

| Domain | Current state | Canonical runtime/owner state | Evidence state | Target / gap | Priority |
|---|---|---|---|---|---|
| Market Data / Source Evidence | `IMPLEMENTED_AND_WIRED` | Public-provider evidence, source freeze and historical corpus are canonical inputs | Real historical public data exists; source qualification absent | Improve coverage/quality where Alpha Proof exposes need | P0/P2 |
| Trading Calendar / Security Lifecycle | `IMPLEMENTED_AND_WIRED` | Canonical historical/effective-dated owners exist | Exploratory historical evidence; Formal PIT incomplete | Complete qualified facts for formal claims | P2 |
| Formal PIT | `ENGINEERING_ONLY` | PIT owners/qualification/as-of mechanics exist | Current free Provider scopes do not establish qualified Formal PIT | Qualified Provider/fact evidence | P2 / external |
| Tradable Universe / Runtime Scope | `IMPLEMENTED_AND_WIRED` | Frozen scope and eligibility flow exist | Historical exploratory scope proven operationally | Improve decision-time coverage and gate diagnostics | P0 |
| Dataset Manifest / Historical Corpus | `IMPLEMENTED_AND_WIRED` | PostgreSQL identity/lineage + immutable artifact packages | Historical replay evidence exists | Stable research base; formal qualification later | P0/P2 |
| Feature Materialization | `IMPLEMENTED_AND_WIRED` | Canonical Feature owners are consumed downstream | Engineering/replay evidence | Establish transparent Alpha baseline and coverage diagnostics | P0 |
| Factor Catalog / Extraction | `IMPLEMENTED_AND_WIRED` | Panel v2 projects all 70 canonical outputs; 49 numeric hypotheses use the shared exact-rational tie-aware kernel | WP-01 finds three positive intraday factors and 25 significant negative-direction factors under exploratory BH-FDR; no external validation | Freeze exact surviving family for WP-02; no post-hoc direction flips | P0/P1 |
| Alpha Correctness / Independent Reproduction | `IMPLEMENTED_AND_WIRED` | Historical correctness checker recomputes three intraday Factors and T+1 10:30 Target from normalized bars; Panel persists normalized source lineage; mismatch fails closed | Focused synthetic/unit proof only; physical package unavailable, so `PHYSICAL_REPRODUCTION_NOT_ESTABLISHED`; Alpha not proven | Reopen physical package and run the frozen proof before admitting a real hypothesis | P0 / external data |
| External Validation | `IMPLEMENTED_NOT_PROVEN` | Canonical `ResearchExperimentDefinition` freezes exact hypothesis/thresholds and exactly one Temporal, Universe or Provider change; evaluator emits coverage, IC/inference, bucket, Top-K economics, turnover/drawdown/capacity/retention | No new external dataset executed; `EMPIRICALLY_EXECUTED=false`, `EXTERNALLY_VALIDATED=false`, `FORMAL_OOS=false` | Execute only after real `CORRECTNESS_SUPPORTED` evidence | P1 / evidence |
| Context Conditional Research | `IMPLEMENTED_NOT_PROVEN` | Typed evaluator enforces session-level across-session conditioning versus genuine cross-sectional interaction and `NOT_ESTIMABLE` | Synthetic/unit proof; Market/Theme are current session selectors and Capital is a public proxy | Run only for a correctness/external-supported Alpha; no trading authority | P1 / evidence |
| Market Regime | `IMPLEMENTED_AND_WIRED` | State owner + strategy/research consumers | WP-01: 76 pass-all and 50 reject-all sessions, zero within-session mixed populations; hard lift `NOT_ESTIMABLE`, disposition `RETEST` | External/alternative policy test before keeping or retiring as predictive Gate | P1 |
| ETF Context | `IMPLEMENTED_AND_WIRED` | Context role exists | Historical coverage is a material weakness in longitudinal campaign | Traceable context coverage; ablation | P0/P2 |
| Theme Context | `IMPLEMENTED_AND_WIRED` | State/context owner exists and Panel preserves its diagnostics | WP-01: 80 pass-all and 46 reject-all sessions, zero within-session mixed populations; disposition `RETEST` | Test valid conditional-policy semantics externally; do not claim entity-level lift | P1 |
| Capital State / Proxy | `IMPLEMENTED_AND_WIRED` | Derived state exists and public-proxy limitation is explicit | WP-01 rejects all 126 sessions; hard/soft predictive effect `NOT_ESTIMABLE`, disposition `RETEST` | Preserve Fact vs Proxy distinction; acquire valid observations before retest | P1/P2 |
| StateSeries / Dynamic Pool | `IMPLEMENTED_AND_WIRED` | Canonical state/pool owners | WP-01 post-integrity population passes 126/126 sessions; effect is integrity-confounded, disposition `RETEST` | Separate predictive membership from integrity before retest | P1 |
| Candidate Discovery | `IMPLEMENTED_AND_WIRED` | Panel v2 preserves status/rank/score/all reasons and isolated Gate diagnostics | Current Hard Chain selects 0/37,319; pre-registered hard-integrity Price/Return challenger is exploratory positive (RankIC 0.090809, Top-5 net 0.014807) | External validation of exact challenger; no Signal/Forecast promotion yet | P0/P1 |
| Layered Candidate Policy | `IMPLEMENTED_AND_WIRED` | Panel Universal Integrity is separated from incumbent factor availability; content-addressed Incumbent/Challenger evaluator exposes hard failures, factor values/contributions, Context adjustment, rank and selection; same-dataset comparison is frozen | Synthetic/unit proof; real Challenger remains dormant until correctness and external validation support it | Execute comparison only on a frozen admissible dataset; never retune from validation | P1 / evidence |
| Signal | `IMPLEMENTED_AND_WIRED` | Distinct artifact and consumers exist | V2 coverage is 0/37,800 because no Candidate is selected | Prove distinct lift/policy value or merge/simplify | P0/P1 |
| Path Forecast | `IMPLEMENTED_AND_WIRED` | Research/Shadow path is fail-closed when unestimable | V2 coverage is 0/37,800; `NOT_ESTIMABLE`, not a probability or zero lift | Estimator/sample diagnostics; no probability claim without calibration | P0/P2 |
| Conditional Prediction / Strategy Input | `IMPLEMENTED_AND_WIRED` | Empirical baseline and frozen regularized challenger expose uncertainty/minimum-sample/model comparison; Strategy Contract V2 explicitly requires or declines Forecast and required inputs bind Signal/Forecast/Context/Risk/Model lineage | Focused engineering tests only; raw barrier scores are not probabilities; no Strategy economics or calibration proof | Real Candidate survivor and separate economic/calibration validation | P2 / evidence |
| Transparent Factor/Gate Baseline | `IMPLEMENTED_NOT_PROVEN` | WP-01 binds full Panel, common multi-K/quintile/stability/economics diagnostics and matched-session Gate contrasts to Golden V2 ranking | Price/Return challenger is exploratory positive; all Gates `RETEST`; PIT/OOS/Production floors remain false | WP-02 external validation of exact survivor | P0/P1 |
| Cross-sectional Evaluation | `IMPLEMENTED_AND_WIRED` | One shared tie-aware kernel and canonical Evaluation owner feed Evidence | WP-01 adds 49-factor, 12-Gate, five-policy IC stability, tie-aware quintiles, Top-1/3/5/10, turnover, drawdown and conditional diagnostics; exact replay passes | Preserve contract through external validation | KEEP/P1 |
| Statistical Validity / Multiple Testing | `ENGINEERING_ONLY` | Existing framework applies BH-FDR and now exposes its moving-block mean interval to correctness/external diagnostics with block-length sensitivity | 28/49 numeric Factors significant (3 positive, 25 negative) only in discovery; no qualified Locked-OOS result | Re-freeze family for disjoint WP-02 validation | P1/P2 |
| Calibration | `BLOCKED_BY_EVIDENCE` | Owner/mechanics exist | `CALIBRATED=false` | Qualified disjoint evidence required | P2 |
| Strategy Registry / Runtime | `IMPLEMENTED_AND_WIRED` | `OVERNIGHT`, `SWING_STATE` and dormant `CONDITIONAL_PREDICTION` share one bounded runtime; Forecast-required lineage fails closed | Engineering/runtime semantics exist; economic value unproven | Activate conditional family only after upstream evidence; keep one runtime | P0/P1 |
| Entry / Hold / Add / Reduce / Exit | `IMPLEMENTED_AND_WIRED` | Strategy policy and Shadow/manual paths exist | Engineering evidence; no qualified strategy edge | Strategy economics under realistic execution | P1 |
| Cross-strategy Portfolio | `IMPLEMENTED_AND_WIRED` | Simple Top-K/budget/exposure logic is canonical | Engineering correctness, not Portfolio Alpha | Keep simple; deepen only from empirical risk need | P1 |
| Cost / Slippage / Fillability / Capacity | `IMPLEMENTED_NOT_PROVEN` | Strategy/portfolio research carries assumptions/provenance | Existing inputs are not fully empirically calibrated | Empirical inputs and sensitivity before economic qualification | P1/P2 |
| Manual Execution Intent | `IMPLEMENTED_AND_WIRED` | Accepted Portfolio lines enter one manual ledger | Engineering correctness | Preserve; not a broker-authority project | KEEP |
| Observed Fill / Physical Position | `IMPLEMENTED_AND_WIRED` | Fill-derived physical truth | Engineering/runtime path exists | Keep single Authority | KEEP |
| Strategy Sleeve / Fill Allocation | `IMPLEMENTED_AND_WIRED` | Derived from observed effective Fill allocations | Engineering/runtime path exists | Keep for attribution/reconciliation | KEEP |
| Market Outcome | `IMPLEMENTED_AND_WIRED` | Historical/Shadow outcome owners exist | Real exploratory T+1 outcomes exist | Extend exact Golden Slice outcomes as needed | P0 |
| Strategy Outcome | `IMPLEMENTED_AND_WIRED` | Simulated/manual fill-derived strategy outcome path exists | V2 canonical path has 126 `NO_ACTION` sessions, so Strategy economics are `NOT_ESTIMABLE` | Gross→cost→net evidence only after a credible ranking/gated action exists | P1 |
| Multi-horizon Path Outcome | `IMPLEMENTED_NOT_PROVEN` | Kernel and owner exist | Automatic longitudinal production not complete | Materialize windows only when relevant to active Strategy | P1 |
| Attribution | `IMPLEMENTED_AND_WIRED` | Performance/diagnostic consumers exist | Mostly exploratory/non-causal | Make Data→Cost diagnosis part of Golden Loop | P0/P1 |
| Research Feedback | `IMPLEMENTED_NOT_PROVEN` | Outcome→feedback/challenger mechanics exist | No mature empirical closed-loop proof | Drive next Experiment without automatic Champion mutation | P1 |
| Historical Research Runtime | `PROVEN` for engineering scope | Bounded journal reuses canonical business semantics and writes V2 canonical Evaluation | Real 126-session resume, PostgreSQL owner binding and exact replay evidence exist | Keep; no second backtest architecture | KEEP |
| Prospective Shadow | `BLOCKED_BY_EVIDENCE` | Freeze/settle/attestation mechanics exist | Sustained live-origin sample absent | Start/continue immutable prospective clock | P0 / time-dependent |
| Model Governance | `IMPLEMENTED_AND_WIRED` | PostgreSQL owner/selection exists | Model qualification remains false | Freeze new abstraction; consume real research evidence | KEEP |
| Strategy Qualification | `BLOCKED_BY_EVIDENCE` | Fail-closed owner path exists | Formal PIT/OOS/economic/prospective floors missing | Evidence-driven qualification only | P2 |
| Production Admission | `BLOCKED_BY_EVIDENCE` | Persisted blocker/projection exists | Not Production-qualified | Keep blocked until independent floors pass | P3 |
| Runtime Recovery / Replay | `IMPLEMENTED_AND_WIRED` | Journals, leases/fences and replay boundaries exist | Exact executable-SHA V2 resume/replay proof exists in the isolated migrated Phase E3 database | Maintain and re-prove when modified | KEEP |
| Observability / Query | `IMPLEMENTED_AND_WIRED` | Runtime/strategy inspection and metrics exist | Engineering evidence | Prioritize business diagnostics over new infrastructure metrics | P0/P1 |
| RBAC / Approval / Audit | `ENGINEERING_ONLY` | PostgreSQL owners exist | External authentication not bound | No further governance expansion unless needed | P2 |
| External Authentication | `MISSING` | No trusted external-subject binding | None | Required before operational production permissions depend on identity | P3 / external |
| Broker Integration | `DEFERRED` | No broker writer/authority | None | Future controlled execution only after Alpha/Strategy proof | P3 |

## Interpretation

The matrix shows a deliberate asymmetry:

- **Engineering platform maturity is high.**
- **Empirical Alpha/Strategy maturity is low.**
- **Formal and prospective qualification remains evidence-blocked.**

The next phase is therefore not another infrastructure-completeness program. It is an Alpha Proof campaign that uses the existing platform to discover, reject, simplify and validate quantitative models and strategies.
