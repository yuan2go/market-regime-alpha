# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-31 WP-10 Market Target Outcome exit reconciliation
> **Repository Implementation Checkpoint:** `56812c58ce7b6e601366ffd0a5cfb52fec573227`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** WP-09 at `9a21d5d5384ace9ace987055a131d010e54daf0f`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-10 exit reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `15f3adc2b5a424a81cfa1224dfee4b04b6b422fa`; source `1ad379e67be0960a45d7c1d8f11fb953fd11480e`; tests `b03577799a3b76585b1ec3fe023c2adb3a8ceff3`; Outcome tree `d984bcc66246be0f68d530c46fe3a1c85294a16a`; target baseline blob `37522c256e5bfe0c28d43a48256dfd5aac7f2068`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, and [WP-10 Market Target Outcome Verification](../references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md)

This view separates current capability from target convergence. It records
Target Definition, Decision Run commitment, and Market Target Outcome
engineering implementation at the exact checkpoint above and its local WP-10
exit-gate result. It is invalid after
its source tree changes and cannot
promote a capability or research claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

Cross-cutting Foundation is `MERGED_MAIN / EXIT_GATE_PASS`. Market/PIT,
Selection Core, and Research Definition Core are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` on the current
implementation line. Research owns Dataset, DatasetSource, FeatureDefinition,
and provider-neutral Target Definition in permanent
`market_regime_alpha.research_qualification`. Selection-owned Candidate and
Decision-Support-owned Decision Run/Target Commitment and Outcome-owned Market
Target Outcome are
`IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER`. No state grants canonical
business Authority or creates dual write.

The repository Python gates remain bound to the frozen `uv run` environment. At
WP-10 implementation checkpoint `56812c58`, 43 WP-10-focused tests, 392
refoundation tests, 33 platform tests, 286 PostgreSQL persistence tests, and the
complete 3,432-node legacy-plus-target collection
pass, together with clean
target bootstrap/verify/exact-OID recreate, concurrency/recovery/replay,
representative plans, architecture dependencies, documentation, Ruff, mypy,
build, and diff gates. Exact commands, non-final failures, catalog/checksums, and
proof ceilings are owned by the linked WP-10 Verification. The clean PostgreSQL
16.14 proof records 56 tables, four views, 1,339 catalog objects, and catalog
checksum
`6c3e2732024ae28875df111ad3ef97cd8c8520f40adc168b0ac8951048335888`.
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
| Target Definition | legacy evaluation Target shapes remain historical/current implementation only; the target draft implements provider-neutral immutable Target/Checkpoint/Metric/Dependency versions, exact Artifact identities, Target-owned relational closure, append-only supersession, independent registration UoW, and exact replay | Research & Qualification | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
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
| Research Definition | many legacy dataset/feature/research owners remain canonical; isolated target Decision-input Dataset/DatasetSource/FeatureDefinition plus provider-neutral Target Definition Authority is implemented and engineering-verified | Research & Qualification | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` |
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
