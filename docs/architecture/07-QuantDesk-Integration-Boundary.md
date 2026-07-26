# QuantDesk Integration Boundary

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Design boundary for a future Application/UI/Research Workbench integration  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 00-System-Context.md, ../specs/README.md  
> **Code Evidence:** NOT_STARTED in this repository

QuantDesk may provide:

- daily snapshot and context views;
- ETF/theme/Candidate exploration;
- Entry/Holding/Exit display;
- research artifact and backtest comparison;
- experiment initiation and approval workflows;
- manual trade and deviation capture.

QuantDesk must not own:

- Feature/model implementation or model lifecycle truth;
- research Artifact identity;
- canonical data calculation;
- provider or broker account truth;
- automatic trade execution.

## Integration contracts

Read APIs expose immutable artifacts and projections. Write APIs create commands such as `RecordManualDecision`, `ApproveExperiment` or `ApproveModelPromotion`; they do not modify existing artifacts.

The UI displays evidence level, data quality, Decision Time, model/version and uncertainty on every recommendation. It must display `NO_PREDICTION`, `NO_TRADE`, `DATA_BLOCKED` and model disagreement as first-class outcomes.
