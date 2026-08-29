# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA capability read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-29T02:51:45Z
> **Repository SHA:** `44caf94aac86c51bb0e69968aadc4dc47ff84907`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-05 Selection Core implementation audit`
> **Source Tree IDs:** source `d9f5ff8ac1b6eb736cc0f14f8dc2b8ed1d6d577c`; legacy migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; target baseline `f514b18d29f48e730d0bce6c243df774bd2fceeb`; tests `280a3cc898e00bab91d5f7c92acd3f3f9b3a0e4a`
> **Code Evidence:** target and legacy source/migration packages plus `tests`

This view separates current capability from target convergence. It is invalid
after its source tree changes and cannot promote a capability or research claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

Cross-cutting Foundation is `MERGED_MAIN / EXIT_GATE_PASS`. Market/PIT and
Selection Core are `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` on the
current implementation line. No state grants canonical business Authority or
creates dual write.

The repository Python gates remain bound to the frozen `uv run` environment.
At this snapshot all 3,195 collected tests pass against an explicitly recreated
PostgreSQL 16 database, including 155 target refoundation tests. This refresh
advances only the test-only Universe and Eligibility convergence rows. It
supplies no Candidate, Research, Provider qualification, Formal PIT, Alpha,
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
| Candidate | current Candidate/State/daily/historical artifacts; no target Candidate owner or tables | Candidate after minimal Research Definition substrate | `DEFERRED / NO-GO` |
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
| Research | many dataset/experiment/campaign/evaluation owners | Research & Qualification | `NOT_STARTED` |
| Qualification | current model/PIT/provider/OOS/calibration owners | Research & Qualification | `NOT_STARTED` |
| Prospective | current freeze/settlement/attestation mechanics; no sustained proof | ordinary Runtime + Decision/Evidence/Outcome | `NOT_STARTED` |

`IMPLEMENTED` in the current column never means the target Authority is cut
over. `NOT_STARTED` refers only to target convergence, not loss of the current
capability. Evidence ceilings remain as declared by immutable reports; no row
in this matrix establishes Formal PIT, qualified Provider data, Formal OOS
Alpha, Prospective value, Production, or broker authority.

Future generation must derive current ownership and target acceptance gates
read-only. A manually changed label is not a promotion mechanism.
