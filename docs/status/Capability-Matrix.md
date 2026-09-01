# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-01 WP-11 focused implementation reconciliation
> **Repository Implementation Checkpoint:** `59ac3a35c46d60d179d62898de054c608831f54c`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** WP-10 at `56812c58ce7b6e601366ffd0a5cfb52fec573227`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-11 implementation/status reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `3701b9ec527096cce13d3000d7d7bc2b56e74677`; source `2dd5e31479a6da637ffcf21b248a4ad45c5b4aad`; tests `59de085bf3d87617b68491161e0d7f37f8883397`; Research & Qualification tree `79ef8c310f663bf698d97faa555b67c7d811e197`; target baseline blob `cdec4ef409e4da625f41cca46174f722053c8fc1`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, [WP-11 canonical design](../references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Design.md), and [WP-11 implementation status](../references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Implementation-Status.md)

This view separates current capability from target convergence. It records the
integrated WP-11 Target/Outcome, Partition, Experiment, and Evaluation draft at
the exact checkpoint above. Focused validation passed; independent engineering
qualification did not run, so this is not a WP-11 exit-gate result. It is invalid after
its source tree changes and cannot promote a capability or research claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

Cross-cutting Foundation is `MERGED_MAIN / EXIT_GATE_PASS`. Market/PIT,
Selection Core, and Research Definition Core are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` on the current
implementation line. Research owns Dataset, DatasetSource, FeatureDefinition,
provider-neutral Target Definition, Research Partition, Experiment, and
Evaluation in permanent
`market_regime_alpha.research_qualification`. Selection-owned Candidate and
Decision-Support-owned Decision Run/Target Commitment and Outcome-owned Market
Target Outcome are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER`. No state grants canonical
business Authority or creates dual write.

WP-11 focused validation passes 111 directly affected tests, changed-scope Ruff
and mypy, documentation links, and diff checks. The focused clean PostgreSQL 16
catalog records 68 tables, four views, 1,604 catalog objects, and catalog
checksum
`0737ad5a29cd8a3d3847d2b2f20dbb81bd5510e44916d6e08f8a9f150995bda6`.
Full PostgreSQL concurrency/recovery/replay, complete regression, build, and
engineering qualification are `NOT_RUN_BY_SCOPE`; exact commands and ceilings
are recorded in the linked WP-11 implementation status. The immutable WP-10
Verification remains the latest engineering exit-gate proof.
Remote CI remains
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` because repository Actions are
disabled. Nothing here supplies Provider qualification, Formal PIT, Alpha,
broker, Production, or trading evidence.

| Capability | Current implementation truth | Approved target owner | Target convergence |
|---|---|---|---|
| Market | legacy owners remain canonical; isolated target capture/revision/gap/as-of owner is implemented test-only | Market & PIT | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Regime | current State System inference | Decision Support Context | `NOT_STARTED` |
| ETF | current instrument/reference and rotation paths; target instrument/classification facts implemented, rotation Context absent | Market classification + Decision Context | `PARTIAL_MARKET_SLICE / NOT_CUT_OVER` |
| Theme | current reference/state/context paths; target taxonomy/membership facts implemented, Theme Context absent | Market classification + Decision Context | `PARTIAL_MARKET_SLICE / NOT_CUT_OVER` |
| Capital | current derived public-proxy state | Decision Context `CAPITAL_PROXY` | `NOT_STARTED` |
| Universe | current Runtime Scope/free/historical owners remain canonical; target explicit immutable scope/revision/member owner is implemented test-only | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Eligibility | current funnel/orderability rules across paths remain canonical; target typed policy/rule/assessment/reason owner is implemented test-only | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Candidate | current Legacy Candidate/State/daily/historical paths remain canonical until cutover; the isolated target implements five Selection-owned Candidate relations, deterministic ranking, complete typed score matrix, independent UoW, Infrastructure Research adapter, and funnel/dossier queries | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Target Definition | legacy evaluation Target shapes remain historical/current implementation only; the target draft implements provider-neutral immutable Target/Checkpoint/Metric/Dependency versions, exact Artifact identities, Target-owned relational closure, append-only supersession, independent registration UoW, exact replay, all five Outcome-compatible dependency shapes, and at least one required metric | Research & Qualification | `IMPLEMENTED_DRAFT / PRIOR_EXIT_GATE_PASS / WP11_PARITY_FOCUSED_VALIDATION_PASS / NOT_CUT_OVER` |
| Decision Run/Commitment | legacy decision paths remain canonical until cutover; permanent target Decision Support implements one Run per Candidate Set, ordered non-empty requested Target roster, complete Candidate-disposition × Target commitments, exact Market revision/SourceGap references, fenced atomic open, and read-only replay/reconciliation | Decision Support | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Signal | current Signal artifacts and consumers | Decision Support | `NOT_STARTED` |
| Forecast | current path/conditional/model estimates | Decision Support; definitions in Research | `NOT_STARTED` |
| Opportunity | current Strategy Opportunity and pre-Strategy risk-era persistence | Decision Support, without pre-Strategy Risk authority | `NOT_STARTED` |
| Thesis | current thesis/health paths | Decision Support | `NOT_STARTED` |
| Strategy | current registry/runtime/shadow paths | Decision Support | `NOT_STARTED` |
| Portfolio | current decision/research/shadow portfolios | Decision Support | `NOT_STARTED` |
| Risk | several current pre/post-strategy and account routes | sole post-Portfolio Decision Support Risk owner | `NOT_STARTED` |
| Execution | manual Intent/Fill and risk-reduction paths | Execution & Account | `NOT_STARTED` |
| Position | current Fill-derived projections plus account observations | derived Execution & Account query | `NOT_STARTED` |
| Outcome | historical/shadow/daily/strategy settlements remain canonical until cutover; permanent target `market_regime_alpha.outcome` implements one root per Decision Target Commitment, append-only full revisions, exact dual-cutoff source/observation/metric/dependency/reason rosters, a pure Decimal kernel, fenced settlement, exact replay/reconciliation and a narrow read-only port | Outcome & Attribution | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Attribution | current performance/evaluation diagnostics | Outcome & Attribution | `NOT_STARTED` |
| Research Definition | many legacy dataset/feature/research owners remain canonical; isolated target Decision-input Dataset/DatasetSource/FeatureDefinition plus provider-neutral Outcome-compatible Target Definition Authority is implemented | Research & Qualification | `IMPLEMENTED_DRAFT / PRIOR_EXIT_GATES_PASS / NOT_CUT_OVER` |
| Research Evaluation | legacy experiment/campaign/evaluation owners remain canonical until cutover; the target draft implements database-derived immutable Partition/member rosters, session-based purpose-specific purge/embargo/overlap, pre-access Experiment/Run and Protocol, Evaluation Run lifecycle, PIT-safe exact revision acquisition with global first-access ordinals, complete observations, and full metric-member rosters through three narrow UoWs | Research & Qualification | `WP11_IMPLEMENTED_DRAFT / FOCUSED_VALIDATION_PASS / ENGINEERING_QUALIFICATION_PENDING / NOT_CUT_OVER` |
| Qualification | current model/PIT/provider/OOS/calibration owners | Research & Qualification | `NOT_STARTED` |
| Prospective | target WP-11 implements declared-purpose eligibility from canonical live-clock lineage, rejects Historical/Replay, and requires commitment before earliest Outcome event; no formal campaign, operator evidence, promotion, or sustained value proof exists | ordinary Runtime + Decision/Outcome/Research | `PARTIAL_MECHANICS / ENGINEERING_QUALIFICATION_PENDING / NO_PROMOTION` |

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
