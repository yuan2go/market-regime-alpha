# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA capability read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-27T11:05:01Z
> **Repository SHA:** `d0d1f3152a20f1a3f4f9b8a1d9c4383a49162fb7`
> **Schema Epoch:** `LEGACY_MIGRATIONS_001_106`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-02 repository audit v1`
> **Source Tree IDs:** source `13e8922bb42a0054a2f168eac5ce3ab61f5694ed`; migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; tests `7c525ee274be34d9cae7dbe1d76c700d9f21a54c`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

This view separates current capability from target convergence. It is invalid
after its source tree changes and cannot promote a capability or research claim.
The complete preservation contract remains the
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md).

| Capability | Current implementation truth | Approved target owner | Target convergence |
|---|---|---|---|
| Market | implemented across data/market/PIT/historical owners | Market & PIT | `NOT_STARTED` |
| Regime | current State System inference | Decision Support Context | `NOT_STARTED` |
| ETF | current instrument/reference and rotation paths | Market classification + Decision Context | `NOT_STARTED` |
| Theme | current reference/state/context paths | Market classification + Decision Context | `NOT_STARTED` |
| Capital | current derived public-proxy state | Decision Context `CAPITAL_PROXY` | `NOT_STARTED` |
| Universe | current Runtime Scope/free/historical owners | Universe & Eligibility | `NOT_STARTED` |
| Eligibility | current funnel/orderability rules across paths | Universe & Eligibility | `NOT_STARTED` |
| Candidate | current Candidate/State/daily/historical artifacts | Universe & Eligibility | `NOT_STARTED` |
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

`IMPLEMENTED` in the current column never means the target Authority exists.
`NOT_STARTED` refers only to target convergence, not loss of the current
capability. Evidence ceilings remain as declared by immutable reports; no row in
this matrix establishes Formal PIT, Formal OOS Alpha, Prospective value,
Production, or broker authority.

Future generation must derive current ownership and target acceptance gates
read-only. A manually changed label is not a promotion mechanism.
