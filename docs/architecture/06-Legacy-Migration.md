# Legacy Migration

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical Strangler migration plan for dividend_t and adjacent assets  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/08-Roadmap.md, ../archive/legacy/README.md  
> **Code Evidence:** src/market_regime_alpha/dividend_t/**, src/market_regime_alpha/legacy/**

## Policy

```text
Legacy Freeze
→ Characterize Existing Behavior
→ Compatibility Boundary
→ Extract Reusable Components
→ Move New Work to Canonical Contracts
→ Retire Only After Replacement Evidence
```

## Asset classification

| Legacy asset | Original behavior | New owner | Migration status |
|---|---|---|---|
| indicators/MACD/force ratio | OHLCV transforms | Feature domain | partial adapters/tests |
| Chan/Tuishen modules | structural/volume-price proxies | Theory/Observable/Feature | formalization required |
| CoscoTimingEngine/strategy | combined single-stock decision God Object | split Candidate/Entry/Lifecycle/Exit | LEGACY_ONLY |
| PositionState/risk/position_sizing | position/risk state | Lifecycle/Portfolio | characterization only |
| backtest.py | broad Legacy simulator | lane-specific simulators | LEGACY_ONLY |
| web/dividend_t_app | operational Dashboard | QuantDesk/Application | read-only migration later |
| scheduler/notifications | local delivery | Operations/Application | reusable after canonical outputs |
| brokers QMT/PTrade | safe interfaces | future Execution domain | paused/non-goal |

## Extraction requirement

Every extraction records source path, original behavior, new owner, new contract, compatibility adapter, characterization test and replacement evidence. No call site is migrated merely because a new class exists.
