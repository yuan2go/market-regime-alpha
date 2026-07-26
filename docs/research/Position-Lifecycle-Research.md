# Position Lifecycle Research

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Current position-state and continuation research design  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, ../specs/PositionSnapshot.md, ../specs/HoldingAssessment.md  
> **Code Evidence:** Canonical implementation NOT_STARTED; Legacy PositionState exists

## Authority

Position state is derived from actual manual/broker records. A recommendation cannot create a position. The canonical object records entry/fills, holding age, MFE/MAE, original/current thesis, Candidate/context/risk status and invalidation state.

## V1 actions

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
NO_ACTION
```

`NO_ACTION` means no authoritative action was produced. It is not equivalent to affirmatively continuing a position.

## Research questions

- Does current thesis/context persistence predict favorable continuation?
- Does Candidate rank decay add value after controlling for price path?
- When does ADD improve expected return rather than increase correlated risk?
- Can REDUCE preserve right-tail gains while reducing drawdown?

## Current state

Legacy dividend_t has PositionState/risk/position-sizing behavior and characterization tests. It remains `LEGACY_ONLY` until extracted behind canonical contracts.
