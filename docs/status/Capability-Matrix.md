# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-02 WP-14 exact-SHA engineering qualification reconciliation
> **Repository Implementation Checkpoint:** `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** merged WP-13 implementation `fc5993e5d9e05dbe2845659140108e1051cf3704` on `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-14 engineering qualification reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `c1198fa61e432d46a416e863d32a7b253abdf67e`; source `ccc42e2a732f0738c560d762ce3c61a1418c475e`; tests `4a2148ff361c057db68d4ee3e758266246b010dd`; Research Qualification tree `453e0f4f81d62a27ebd1e8237fae1627901c95b8`; Market tree `d0efafaa99e7cc575b619f1a3791112e432bb5f0`; Runtime tree `b01c45b9ca7009fe8ddc9cba227f2f656473c6c1`; target baseline blob `2b4f587da1f616ef6b0eeaf15621cbe1c116be50`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, [WP-14 canonical design](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Design.md), and [WP-14 immutable Verification](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md)

This view separates current capability from target convergence. It records the
integrated WP-14 Formal Research engineering readiness closure
at the exact checkpoint above. Independent exact-SHA engineering qualification
passed and is owned by the immutable Verification. This read model is invalid
after its source tree changes and cannot promote a capability or research
claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

Cross-cutting Foundation is `MERGED_MAIN / EXIT_GATE_PASS`. Market/PIT,
Selection Core, and Research Definition Core are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` on the current
implementation line. Research owns Dataset, DatasetSource, FeatureDefinition,
provider-neutral Target Definition, Research Partition, Experiment,
Evaluation, Evidence, Assessment, and Research Qualification in permanent
`market_regime_alpha.research_qualification`. Selection-owned Candidate and
Decision-Support-owned Decision Run/Target Commitment and Outcome-owned Market
Target Outcome are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER`. No state grants canonical
business Authority or creates dual write.

WP-14 qualification passes 19 focused, 604 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,644 repository tests plus clean bootstrap and
exact-OID recreate, real concurrency/failure/recovery/replay, representative
plans, Ruff, mypy, documentation, architecture/import, build, and diff gates.
The PostgreSQL 16 catalog records 129 tables, four views, 2,819 catalog objects,
and catalog checksum
`1d58cbace3120fb0c7048900bb5e162df8dfc40c2b4a26337b2e562093f03714`.
Exact commands and ceilings are recorded in the linked immutable WP-14
Verification.
Remote CI remains
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` because repository Actions are
disabled. Nothing here supplies Provider qualification, Formal PIT, Alpha,
broker, Production, or trading evidence.

| Capability | Current implementation truth | Approved target owner | Target convergence |
|---|---|---|---|
| Market | legacy owners remain canonical; isolated target capture/revision/gap/as-of owner is implemented test-only | Market & PIT | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Provider qualification | Market owns immutable purpose-specific Protocol/requirements/finality/Decision/Capture/Result rosters and source-specific qualified visibility; engineering rehearsals cannot admit and no real Provider is qualified | Market & PIT | `MECHANICS_READY / WP14_EXIT_GATE_PASS / PROVIDER_QUALIFIED_NO` |
| Formal PIT/Dataset | exact Campaign-bound admitted recorded-provider Decision plus typed cutoff-visible sources are mandatory; no current/latest, caller assertion, or reconstruction path exists | Market & PIT + Research & Qualification | `MECHANICS_READY / FORMAL_PIT_NOT_PROVEN / NOT_CUT_OVER` |
| Regime | current State System inference remains canonical; target implements PIT `MARKET_REGIME` Context policy/assessment/metric/source rosters | Decision Support Context | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| ETF | current instrument/reference and rotation paths remain canonical; target implements PIT `ETF_ROTATION` Context over exact Market lineage | Market classification + Decision Context | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Theme | current reference/state/context paths remain canonical; target implements PIT `THEME_ROTATION` Context over exact classification/Market lineage | Market classification + Decision Context | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Capital | current derived public-proxy state remains canonical; target implements explicit `CAPITAL_BREADTH` Context without hidden-intent claims | Decision Context | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Universe | current Runtime Scope/free/historical owners remain canonical; target explicit immutable scope/revision/member owner is implemented test-only | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Eligibility | current funnel/orderability rules across paths remain canonical; target typed policy/rule/assessment/reason owner is implemented test-only | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Candidate | current Legacy Candidate/State/daily/historical paths remain canonical until cutover; the isolated target implements five Selection-owned Candidate relations, deterministic ranking, complete typed score matrix, independent UoW, Infrastructure Research adapter, and funnel/dossier queries | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Target Definition | legacy evaluation Target shapes remain historical/current implementation only; the target draft implements provider-neutral immutable Target/Checkpoint/Metric/Dependency versions, exact Artifact identities, Target-owned relational closure, append-only supersession, independent registration UoW, exact replay, all five Outcome-compatible dependency shapes, and at least one required metric | Research & Qualification | `IMPLEMENTED_DRAFT / WP11_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Decision Run/Commitment | legacy paths remain canonical until cutover; permanent target adds an explicit complete zero-or-more exact later-generation Research Qualification roster to the already complete Candidate × Target commitments and Decision-visible references | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Signal | current Signal artifacts/consumers remain canonical; target writes one explicit immutable Signal per Candidate with exact Context/Strategy bindings and no-signal/wait/unknown/not-estimable states | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Forecast | current path/conditional/model estimates remain canonical; target writes complete rule-based Target/commitment/checkpoint Forecast/Estimate rosters with explicit uncalibrated semantics and no Model prerequisite | Decision Support; definitions in Research | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Opportunity | current Strategy Opportunity/pre-Strategy-risk-era paths remain canonical; target binds the complete Forecast roster plus exact Candidate/Signal/Context/Strategy/Target facts without Risk circularity | Decision Support, without pre-Strategy Risk authority | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Thesis | current thesis/health paths remain canonical; target implements append-only Thesis revisions and complete typed independently falsifiable conditions | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Strategy | current registry/runtime/shadow paths remain canonical; target implements immutable Strategy Versions with complete Context, Signal, and Forecast rules plus code/config/provenance | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Portfolio | current decision/research/shadow portfolios remain canonical; target writes one complete explicit line per Opportunity with Decimal allocation and included/excluded/not-estimable states | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Risk | current risk paths remain canonical; target is the sole post-Portfolio Decision Support Risk owner, evaluates every global/rule × line input, preserves rejected/unknown/no-action, and has no Execution authority | Decision Support | `IMPLEMENTED_DRAFT / WP13_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Execution | manual Intent/Fill and risk-reduction paths | Execution & Account | `NOT_STARTED` |
| Position | current Fill-derived projections plus account observations | derived Execution & Account query | `NOT_STARTED` |
| Outcome | historical/shadow/daily/strategy settlements remain canonical until cutover; permanent target `market_regime_alpha.outcome` implements one root per Decision Target Commitment, append-only full revisions, exact dual-cutoff source/observation/metric/dependency/reason rosters, a pure Decimal kernel, fenced settlement, exact replay/reconciliation and a narrow read-only port | Outcome & Attribution | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Attribution | current performance/evaluation diagnostics | Outcome & Attribution | `NOT_STARTED` |
| Research Definition | many legacy dataset/feature/research owners remain canonical; isolated target Decision-input Dataset/DatasetSource/FeatureDefinition plus provider-neutral Outcome-compatible Target Definition Authority is implemented | Research & Qualification | `IMPLEMENTED_DRAFT / PRIOR_EXIT_GATES_PASS / NOT_CUT_OVER` |
| Research Evaluation | legacy experiment/campaign/evaluation owners remain canonical until cutover; the target draft is present in sole composition and implements three narrow UoWs, explicit single-exchange Partition calendars, session-based purge/embargo, atomic complete ordered Experiment binding rosters, PIT-safe exact revision acquisition, global first-access ordinals, complete observations and metric-member rosters, and read-only reconciliation | Research & Qualification | `IMPLEMENTED_DRAFT / WP11_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Qualification | current legacy model/PIT/provider/OOS/calibration owners remain canonical until cutover; target Evidence binds exact terminal Evaluations and immutable Artifacts in a validated DAG, Assessment derives complete Experiment Evaluation/Evidence rosters with negative/inconclusive/not-estimable preservation, and purpose-specific Policies/Decisions explicitly evaluate every floor with exact Evidence bindings and strict later-generation reads | Research & Qualification | `IMPLEMENTED_DRAFT / WP12_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Formal Research Campaign | immutable Target/hypothesis/baseline/Provider/FIT/VALIDATION/LOCKED_OOS/Evaluation/Qualification/cost predeclaration; actual complete Partition/Experiment binding; exact Decision and Due Runtime profiles; protected PostgreSQL-time zero-access opening; read-only inspection/reconciliation | Research & Qualification using existing Runtime/owners | `FORMAL_RESEARCH_ENGINEERING_READY / WP14_EXIT_GATE_PASS / NO_EMPIRICAL_PROMOTION` |
| Prospective | target requires canonical live-clock eligibility, commitment before earliest Outcome event, exact Due Proof Runtime profile, database-clock due states, and protected zero-access opening; Historical/Replay fixture masquerade is rejected; no real future campaign or sustained value proof exists | ordinary Runtime + Decision/Outcome/Research | `MECHANICS_READY / WP14_EXIT_GATE_PASS / PROSPECTIVE_PROVEN_NO` |

`IMPLEMENTED` in the current column never means the target Authority is cut
over. `NOT_STARTED` refers only to target convergence, not loss of the current
capability. Evidence ceilings remain as declared by immutable reports; no row
in this matrix establishes Formal PIT, qualified Provider data, Formal OOS
Alpha, Prospective value, Production, or broker authority.

This exact-SHA implementation matrix does not restate or select future work.
Post-Candidate dependency order is owned only by the current
[Roadmap](Roadmap.md); changing design order does not make an absent capability
implemented.

Future generation must derive current ownership and target acceptance gates
read-only. A manually changed label is not a promotion mechanism.
