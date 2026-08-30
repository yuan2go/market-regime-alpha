# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-30 WP-07 Candidate Closure exit reconciliation
> **Repository Implementation Checkpoint:** `029c26928af436d7788da1cce3a53c94b96377bf`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** WP-06 at `22a5ec692fcc261182197c2953a0a860d7cd6f94`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-07 Candidate Closure exit reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `d77c8540eaae24e5acdc7e85e1c0ef983614d1ed`; source `314b9df317e056196b6ab7962fe6cf36ec308b99`; tests `715b9bccb0618926842ec859fffd9b5e695ab55a`; target baseline blob `f86f5f8623aad758ed6df533fd3b706c09a69b96`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, and [WP-07 Candidate Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md)

This view separates current capability from target convergence. It records
Candidate engineering implementation at the exact checkpoint above and its local
WP-07 exit-gate result. It is invalid after its source tree changes and cannot
promote a capability or research claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

Cross-cutting Foundation is `MERGED_MAIN / EXIT_GATE_PASS`. Market/PIT,
Selection Core, and Research Definition Core are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` on the current
implementation line. Research owns only Dataset, DatasetSource, and
FeatureDefinition in permanent `market_regime_alpha.research_qualification`.
Selection-owned Candidate is `IMPLEMENTED_DRAFT /
EXIT_GATE_PASS / NOT_CUT_OVER`. No state grants canonical business
Authority or creates dual write.

The repository Python gates remain bound to the frozen `uv run` environment. At
WP-07 implementation checkpoint `029c269`, 82 Candidate-focused tests and the
complete 3,330-node legacy-plus-target collection pass, together with clean
target bootstrap/verify/exact-OID recreate, concurrency/recovery/replay,
representative plans, architecture dependencies, documentation, Ruff, mypy,
build, and diff gates. Exact commands, non-final failures, catalog/checksums, and
proof ceilings are owned by the linked WP-07 Verification. The clean PostgreSQL
16.14 proof records 40 tables, four views, 892 catalog objects, and catalog
checksum
`527570a3d0d1e00ec242e57060baa1eb47998a493aa2dd94a2d60841841da6ca`.
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
| Candidate | current Legacy Candidate/State/daily/historical paths remain canonical until cutover; the isolated target implements five Selection-owned Candidate relations, deterministic ranking, complete typed score matrix, independent UoW, Infrastructure Research adapter, and funnel/dossier queries; local WP-07 engineering exit gate passes at `029c269` | Selection | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Signal | current Signal artifacts and consumers | Decision Support | `NOT_STARTED` |
| Forecast | current path/conditional/model estimates | Decision Support; definitions in Research | `NOT_STARTED` |
| Opportunity | current Strategy Opportunity and pre-Strategy risk-era persistence | Decision Support, without pre-Strategy Risk authority | `NOT_STARTED` |
| Thesis | current thesis/health paths | Decision Support | `NOT_STARTED` |
| Strategy | current registry/runtime/shadow paths | Decision Support | `NOT_STARTED` |
| Portfolio | current decision/research/shadow portfolios | Decision Support | `NOT_STARTED` |
| Risk | several current pre/post-strategy and account routes | sole post-Portfolio Decision Support Risk owner | `NOT_STARTED` |
| Execution | manual Intent/Fill and risk-reduction paths | Execution & Account | `NOT_STARTED` |
| Position | current Fill-derived projections plus account observations | derived Execution & Account query | `NOT_STARTED` |
| Outcome | historical/shadow/daily/strategy settlements | Outcome & Attribution | `NOT_STARTED` |
| Attribution | current performance/evaluation diagnostics | Outcome & Attribution | `NOT_STARTED` |
| Research Definition | many legacy dataset/feature/research owners remain canonical; isolated target Decision-input Dataset/DatasetSource/FeatureDefinition Authority is implemented and engineering-verified | Research & Qualification | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
| Research Evaluation | current experiment/campaign/evaluation owners; target implementation remains absent | Research & Qualification | `NOT_STARTED` |
| Qualification | current model/PIT/provider/OOS/calibration owners | Research & Qualification | `NOT_STARTED` |
| Prospective | current freeze/settlement/attestation mechanics; no sustained proof | ordinary Runtime + Decision/Evidence/Outcome | `NOT_STARTED` |

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
