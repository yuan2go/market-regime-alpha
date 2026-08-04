# Legacy Migration

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical Strangler migration plan for dividend_t and adjacent assets  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-04
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 12-Canonical-Runtime-and-Legacy-Migration.md, ../constitution/08-Roadmap.md, ../archive/legacy/README.md
> **Code Evidence:** `src/market_regime_alpha/dividend_t/**`; `src/market_regime_alpha/legacy/**`; `src/market_regime_alpha/migration/**`; `src/market_regime_alpha/features/technical/moving_average.py`; `tests/architecture/test_legacy_import_boundary.py`; `tests/migration/**`

## Policy

```text
Legacy Freeze
→ Characterize Existing Behavior
→ Compatibility Boundary
→ Extract Reusable Components
→ Move New Work to Canonical Contracts
→ Retire Only After Replacement Evidence
```

Legacy output is comparison evidence, not canonical authority. A new model is
not accepted merely because its output resembles Legacy, and it must not copy a
known Legacy defect merely to obtain an exact match.

## Dependency rule

```text
canonical core ─X→ market_regime_alpha.dividend_t
migration.legacy adapters → market_regime_alpha.dividend_t
migration.comparison → isolated Legacy adapter + canonical model
```

The AST architecture test enforces this rule across the Python source tree.
Direct imports are restricted to the Legacy package, the isolated migration
adapter package, the existing `legacy` compatibility package and the explicitly
Legacy FastAPI compatibility module. A new domain model, Repository,
Application Service or canonical Reader cannot import `dividend_t` directly.

## Asset classification

| Legacy asset | Original behavior | New owner | Migration status |
|---|---|---|---|
| simple moving average in `indicators` | trailing OHLCV transform | Feature domain | first Decimal Feature/Adapter/Differential/Replay slice implemented on development branch |
| remaining moving average/MACD/force ratio | OHLCV transforms | Feature domain | WP-MIG-01 required |
| volume structure | volume-price observable | Feature domain | WP-MIG-01 required |
| Chan/Tuishen modules | structural/volume-price proxies | Theory/Observable/Feature | split and formalization required under WP-MIG-01 |
| CoscoTimingEngine/strategy | combined single-stock decision God Object | split Candidate/Entry/Lifecycle/Exit | LEGACY_ONLY |
| PositionState/risk/position_sizing | position/risk state | Lifecycle/Portfolio | characterization only |
| backtest.py | broad Legacy simulator | lane-specific simulators | LEGACY_ONLY |
| web/dividend_t_app | operational Dashboard | QuantDesk/Application | read-only migration later |
| scheduler/notifications | local delivery | Operations/Application | reusable only after canonical outputs |
| brokers QMT/PTrade | Legacy/safe-fail interfaces | future Execution domain | isolated, paused and outside current authority |

## Extraction requirement

Every extraction records source path, original behavior, new owner, new
contract, compatibility adapter, characterization test and replacement
evidence. No call site is migrated merely because a new class exists.

An isolated adapter may only:

- normalize one standard, content-addressed input dataset into the exact Legacy
  input shape;
- invoke the narrow Legacy calculation;
- normalize output and expose float/lossy behavior;
- report missing data, exceptions and Legacy limitations;
- supply a baseline to differential verification.

It may not receive a canonical Repository or Broker, write a canonical
Artifact directly, create Signal/Decision/ManualTrade/Fill/Position objects,
or use a static fallback as market data.

## Role-specific target contracts

Migration targets use independent `FeatureComputer`, `ResearchModel`,
`SignalModel` and `DecisionModel` Protocols. There is no universal Model base
class:

- Features are side-effect-free observables with explicit as-of time,
  availability, configuration version/hash and missingness.
- Research models describe Market, Theme, Capital or Candidate inference.
- Signals describe typed market/stock observations, not final trade commands.
- Decisions stop at `REJECT`, `WAIT`, `READY_FOR_MANUAL_CONFIRMATION`,
  `REDUCE` or `EXIT` and never imply automatic execution.

## Differential replacement evidence

`DifferentialTestHarness` evaluates the same normalized dataset through the
Legacy adapter and canonical model under a content-addressed comparison policy.
The report supports `EXACT_MATCH`, `NUMERIC_TOLERANCE`,
`EXPECTED_SEMANTIC_CHANGE`, `LEGACY_DEFECT_FIXED`, `CANONICAL_REGRESSION`,
`INSUFFICIENT_DATA` and `NOT_COMPARABLE`.

Field-specific tolerances, independently defined canonical invariants and
explicit Legacy defect IDs prevent an unreviewed difference from being hidden.
Both Feature and ModelComparison Artifacts have verified Readers and replay.

## Migration order

The next program is **WP-MIG-01 Technical Observable Migration**:

1. MACD;
2. Moving Average beyond the simple example;
3. Volume Structure;
4. Force Ratio;
5. Chan Features;
6. Tuishen Volume-Price Features.

Complete Legacy buy/sell points, risk, position sizing, COSCO special strategy,
web orchestration and Broker paths are not part of this extraction wave.

The evidence ceiling remains:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```
