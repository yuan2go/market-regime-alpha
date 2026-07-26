# Entry Research

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Current Entry Timing research design  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, ../specs/EntryAssessment.md, ../specs/Entry-Path-Target-V1.md  
> **Code Evidence:** src/market_regime_alpha/strategies/entry/**

## Separation

Candidate asks “which opportunities rank higher?” Entry asks “is opening now preferable to waiting or rejecting?” Entry does not change Candidate historical quality.

## Current main evidence

Entry Path Target contracts/materialization and temporal price-lineage controls are implemented and tested. They are target infrastructure, not an Entry model, Entry Gate or EntryAssessment production service.

## V1 actions

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
NO_ACTION
```

## Evaluation

An Entry model adds value only when it lowers MAE or adverse-first probability while retaining MFE/opportunity capture and improving cost-adjusted returns. Reduced trade count alone is not success.

## Research comparisons

- Candidate baseline with fixed Decision Price entry;
- ENTER/WAIT/REJECT strata;
- fixed delay and pullback rules;
- price-location/volume/context additions one at a time;
- path metrics and missed-opportunity cost.
