# Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Current capability/evidence matrix  
> **Repository Baseline:** `main@5a441746ada08eb08310b12e34d9e0f56f56a952`
> **Strongest Research Evidence Revision:** `bcee87a7d79f1028667a5874b7273a10fdcaacfa` (Golden Loop V2)
> **Last Updated:** 2026-08-20
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
| Factor Catalog / Extraction | `IMPLEMENTED_AND_WIRED` | Shared exact-rational tie-aware rank kernel feeds canonical evaluation consumers | V2 exploratory evidence is negative; identity-broken V1 lifts are methodology-invalidated | De-dup, ablation and incremental-lift program | P0 |
| Market Regime | `IMPLEMENTED_AND_WIRED` | State owner + strategy/research consumers | V2 adds zero boundary or economic increment in the tested longitudinal scope | Must earn incremental value in a new frozen Experiment | P0 |
| ETF Context | `IMPLEMENTED_AND_WIRED` | Context role exists | Historical coverage is a material weakness in longitudinal campaign | Traceable context coverage; ablation | P0/P2 |
| Theme Context | `IMPLEMENTED_AND_WIRED` | State/context owner exists | V2 constant-factor diagnostics and boundary exposure show zero increment in the tested scope | Redesign/simplify only if new evidence supports it | P0 |
| Capital State / Proxy | `IMPLEMENTED_AND_WIRED` | Derived state exists | Not a validated capital-flow fact; evidence thin/not estimable in key runs | Preserve Fact vs Proxy distinction; prove incremental value | P0 |
| StateSeries / Dynamic Pool | `IMPLEMENTED_AND_WIRED` | Canonical state/pool owners | Only 3/126 sessions are non-constant; V2 changes RankIC slightly but not boundary exposure or economics | Gate/coverage/ablation before further abstraction | P0 |
| Candidate Discovery | `IMPLEMENTED_AND_WIRED` | Strategy runtime records gates/rejections and Candidate lineage | V2 rejects 37,800/37,800 rows; Candidate owners retain first-failure reasons but current Panel/Evidence drops them | Run pre-registered hard/soft/no-predictive Gate contrasts without weakening integrity gates | P0 |
| Signal | `IMPLEMENTED_AND_WIRED` | Distinct artifact and consumers exist | V2 coverage is 0/37,800 because no Candidate is selected | Prove distinct lift/policy value or merge/simplify | P0/P1 |
| Path Forecast | `IMPLEMENTED_AND_WIRED` | Research/Shadow path is fail-closed when unestimable | V2 coverage is 0/37,800; `NOT_ESTIMABLE`, not a probability or zero lift | Estimator/sample diagnostics; no probability claim without calibration | P0/P2 |
| Transparent Factor/Gate Baseline | `IMPLEMENTED_NOT_PROVEN` | Golden V2 freezes correct tie-aware ranking, but Panel consumes only `return_3` and `amount_ratio_5` from a much richer Feature owner | Both V2 variants are negative; multi-K, quantiles, registered Feature families and Gate contrasts remain absent | Complete `WP-ALPHA-RESEARCH-01` before downstream Forecast/Strategy work | P0 |
| Cross-sectional Evaluation | `IMPLEMENTED_AND_WIRED` | One shared tie-aware kernel and precomputed canonical Evaluation owner feed Evidence | Real V2 RankIC/Top-10/MFE/MAE/economic evidence; symbol-renaming and constant-factor metamorphic proof | Add IC stability, quantiles and multi-K diagnostics in the baseline WP | P0 |
| Statistical Validity / Multiple Testing | `ENGINEERING_ONLY` | Formal protocol/family mechanics exist | No qualified Locked-OOS result | Apply to surviving hypotheses after qualified data exists | P2 |
| Calibration | `BLOCKED_BY_EVIDENCE` | Owner/mechanics exist | `CALIBRATED=false` | Qualified disjoint evidence required | P2 |
| Strategy Registry / Runtime | `IMPLEMENTED_AND_WIRED` | `OVERNIGHT` and `SWING_STATE` share one bounded runtime | Engineering/runtime semantics exist; economic value unproven | Use one Golden Slice first; keep multi-strategy contract | P0/P1 |
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
