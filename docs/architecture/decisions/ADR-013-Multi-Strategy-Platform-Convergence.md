# ADR-013: Multi-Strategy Platform Convergence

> **Status:** HISTORICAL
> **Authority:** Approved implementation decision for the multi-strategy convergence slice
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `src/market_regime_alpha/strategies`, `src/market_regime_alpha/application/continuous_research`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

## Context

At the decision point, the repository already had one PostgreSQL-centered Continuous Research control plane, owner-resolved Candidate artifacts, multi-checkpoint T+1 Targets, Strategy Shadow, Portfolio Shadow, fill-derived physical Position, historical session/replay infrastructure, and fail-closed qualification owners. It lacked a canonical Strategy Contract/Version/Run identity, two independently scoped Strategy Families, strategy-scoped evidence, a cross-strategy Portfolio decision, physical-Fill allocation to strategy sleeves, and one operator query spanning those facts. Migration 085 and the shared runtime now implement that selected design; this paragraph records the pre-decision gap rather than current status.

Extending the existing T+1 `StrategyShadowPolicy` for every family would keep strategy identity, Candidate selection, Entry, holding policy, and simulation coupled. Creating a second multi-strategy runtime would duplicate scheduling, recovery, and authority. The selected path is therefore to add one deep Multi-Strategy module behind the existing Continuous and historical/replay seams.

## Decision

Add a canonical Strategy module with one public execution interface:

```text
StrategyRuntime.execute(StrategyRuntimeInput) -> MultiStrategyCycle
```

The input freezes the run origin, runtime authority mode, decision time, Candidate artifact, exact Target references, code/configuration identity, and strategy sleeve state. The cycle evaluates every active Strategy Version, persists one Strategy Run per version, records the complete Candidate-to-action funnel, emits Strategy Proposals, and passes all proposals to a simple cross-strategy Portfolio policy.

The first registered families are:

- `OVERNIGHT`: flat selected instruments may produce `ENTER`; an owned sleeve reaching the next-session horizon produces `EXIT`.
- `SWING_STATE`: explicit position state produces `ENTER`, `HOLD`, `ADD`, `REDUCE`, or `EXIT` under versioned rules. Missing required facts produce `NO_ACTION`, never implicit `HOLD`.

Both policies consume the same Candidate and Target contracts and run through the same Strategy Runtime interface. Historical, Replay, and Shadow differ only through frozen input origin/clock/data references; strategy policy code is shared.

## Business boundaries

The module preserves these chains:

```text
Eligibility -> Ranking -> Candidate -> Strategy Action -> Proposal
Proposal -> Cross-strategy Portfolio -> Risk/Execution boundary
Observed Fill -> Physical Position -> Fill Allocation -> Strategy Sleeve
Path Outcome -> Attribution -> Challenger -> Qualification Assessment
```

Candidate records remain attention/ranking evidence. A Strategy policy independently decides whether to act. Every upstream rejection and every policy rejection is counted and persisted, including empty and data-insufficient funnels.

A Strategy Proposal expresses desired exposure and utility. The simple Portfolio baseline owns accepted exposure and conflict netting. It supports Top-K Equal and Score weighting and enforces explicit gross/single-name/strategy budgets. It creates no Order, Fill, or physical Position.

Physical Position remains owned by the existing observed Fill ledger. A strategy sleeve is a read model derived from immutable allocations of those same Fill rows. Allocation is serialized per account and symbol, cannot exceed the physical Fill quantity, and cannot sell a sleeve below zero.

## Target and outcome design

The existing `TargetDefinition` remains the sole Target identity. Overnight uses the existing T+1 protocols. Swing freezes Close-path Target Definitions at 3, 5, 10, and 20 sessions. One deterministic path kernel calculates:

- MFE and MAE;
- target-before-stop with ambiguous same-bar ordering retained as not observable;
- time-to-MFE;
- trend continuation and failure under versioned thresholds;
- post-exit opportunity loss;
- avoided drawdown.

Market Path Outcome and Strategy Outcome remain distinct. Path outcomes bind Strategy Version, Strategy Run, Dataset/PIT/Universe/Decision Time, Target/Horizon, cost/evaluation protocol, and code/configuration identity before entering strategy-scoped evidence.

## Persistence and recovery

Forward migration 085 adds only business facts required by this slice:

- Strategy Version, Runtime Cycle, Strategy Run, gate attribution, and Strategy Proposal;
- cross-strategy Portfolio Decision and lines;
- strategy Fill Allocation;
- Strategy Path Outcome and typed feedback artifacts for attribution, challenger, evidence, and qualification.

Rows are content-addressed or idempotently keyed and immutable where historically meaningful. A replay reloads the original cycle payload and active Strategy Versions, re-runs the same pure policy/Portfolio kernels, and compares exact hashes. The Continuous child reference makes Strategy execution part of the existing tick fence and replay DAG; it does not introduce another scheduler or journal.

## Evidence and qualification ceiling

Evidence queries are keyed by exact Strategy Version, so Overnight evidence cannot qualify Swing or another version. Qualification is a set of dimensions rather than a single promotional state. Current free-data defaults remain:

```text
PIT_INCOMPLETE
FORMAL_OOS=false
CALIBRATED=false
ECONOMICALLY_SUPPORTED=false
PROSPECTIVE_PROVEN=false
PRODUCTION_AUTHORIZED=false
```

Engineering tests may establish deterministic execution, persistence, migration, recovery, replay, and query behavior only. They cannot raise these evidence dimensions.

## Runtime and operator integration

`CanonicalFreeDataResearchComposition` executes the Strategy child after the State/Controlled/Summary facts are available. The child registers/reloads the two canonical Strategy Versions and their Target protocols, reloads the exact Candidate owner row, executes one cycle, persists it under the active Continuous fence, and returns one child receipt.

Canonical runtime inspection and metrics add Strategy, Portfolio, funnel, and qualification projections. Operators can answer which Strategy Versions ran, how many instruments were eligible/ranked/candidates, why actions were rejected, what proposals were accepted, and which qualification dimensions remain missing.

## Alternatives rejected

1. Extend `StrategyShadowPolicy` per family. Rejected because it preserves a T+1 simulation aggregate as the platform Strategy identity and cannot cleanly represent cross-strategy evidence or physical Fill allocation.
2. Create a standalone Multi-Strategy scheduler/runtime. Rejected because it duplicates the sole production control plane and recovery authority.
3. Build a generic governance/registry framework before business execution. Rejected because Model/PIT/governance infrastructure already exists and the missing facts are Strategy business facts, not another framework.

## Acceptance proof

The implementation is accepted only when executable tests and PostgreSQL runtime proof show:

- Overnight and Swing run in the same cycle and share the same runtime/repository seams;
- Candidate and Entry/action are separately observable;
- rich path outcomes cover short and multi-session horizons;
- evidence queries cannot cross Strategy Version identity;
- multiple Strategy Proposals feed one simple Portfolio decision;
- Fill allocation reconciles strategy sleeves to the observed physical Fill ledger;
- Continuous and historical/replay paths invoke the same policy kernel;
- migration 001 through 085 passes fresh, upgrade, idempotency, and concurrency checks;
- runtime inspect/metrics expose strategy decisions and missing evidence;
- all unsupported Alpha, PIT, OOS, calibration, prospective, Production, and broker claims remain false.
