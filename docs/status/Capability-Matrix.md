# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-02 WP-12 exact-SHA engineering qualification reconciliation
> **Repository Implementation Checkpoint:** `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** merged WP-11 at `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-12 engineering qualification reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `b81e4c2ae29ff0f6b26c15333004b849ebc56431`; source `baa201bfdd4540ad0a63dc4f0f3274eed2199db1`; tests `906f0e59aea13218bfb461ffb967685fe57bb64e`; Research & Qualification tree `94b0c082a8db37ba3e1734834aa4154e3df3fff0`; target baseline blob `b7fe5192a1df0c5733842c632a70e2d88db80d91`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, [WP-12 canonical design](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Design.md), and [WP-12 immutable Verification](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md)

This view separates current capability from target convergence. It records the
integrated WP-12 Evidence, Assessment, and Research Qualification closure
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

WP-12 qualification passes 216 focused, 545 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,585 repository tests plus clean bootstrap and
exact-OID recreate, real concurrency/failure/recovery/replay, representative
plans, Ruff, mypy, documentation, architecture/import, build, and diff gates.
The PostgreSQL 16 catalog records 78 tables, four views, 1,835 catalog objects,
and catalog checksum
`5fa66be6a0b6019032217e201ed547cfd9217fa109ef3b9122d3f0d6dc48ee72`.
Exact commands and ceilings are recorded in the linked immutable WP-12
Verification.
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
| Target Definition | legacy evaluation Target shapes remain historical/current implementation only; the target draft implements provider-neutral immutable Target/Checkpoint/Metric/Dependency versions, exact Artifact identities, Target-owned relational closure, append-only supersession, independent registration UoW, exact replay, all five Outcome-compatible dependency shapes, and at least one required metric | Research & Qualification | `IMPLEMENTED_DRAFT / WP11_EXIT_GATE_PASS / NOT_CUT_OVER` |
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
| Research Evaluation | legacy experiment/campaign/evaluation owners remain canonical until cutover; the target draft is present in sole composition and implements three narrow UoWs, explicit single-exchange Partition calendars, session-based purge/embargo, atomic complete ordered Experiment binding rosters, PIT-safe exact revision acquisition, global first-access ordinals, complete observations and metric-member rosters, and read-only reconciliation | Research & Qualification | `IMPLEMENTED_DRAFT / WP11_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Qualification | current legacy model/PIT/provider/OOS/calibration owners remain canonical until cutover; target Evidence binds exact terminal Evaluations and immutable Artifacts in a validated DAG, Assessment derives complete Experiment Evaluation/Evidence rosters with negative/inconclusive/not-estimable preservation, and purpose-specific Policies/Decisions explicitly evaluate every floor with exact Evidence bindings and strict later-generation reads | Research & Qualification | `IMPLEMENTED_DRAFT / WP12_EXIT_GATE_PASS / NOT_CUT_OVER` |
| Prospective | target WP-11 implements engineering-qualified declared-purpose eligibility from canonical live-clock lineage, rejects Historical/Replay, and requires commitment before earliest Outcome event; no formal campaign, operator evidence, promotion, or sustained value proof exists | ordinary Runtime + Decision/Outcome/Research | `PARTIAL_MECHANICS / ENGINEERING_QUALIFIED / NO_PROMOTION` |

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
