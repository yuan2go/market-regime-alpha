# Failure Attribution

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Canonical failure-analysis framework  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../specs/FailureReasonTaxonomy.md, ../specs/DailyReviewReport.md  
> **Code Evidence:** DESIGNED_ONLY; some MR2 diagnostics exist

Failure attribution separates observation from causal hypothesis.

```text
FACT
INFERENCE
HYPOTHESIS
COUNTER_EVIDENCE
EXPERIMENT
EXPECTED_RESULT
INVALIDATION_CONDITION
CONFIDENCE
```

Daily failures are classified into data, calendar, universe, eligibility, context, Feature, Candidate, Entry, position state, Exit, risk, manual execution deviation, regime shift and unclassified categories.

Codex consumes an immutable evidence pack and writes a proposal. It cannot alter the frozen run, Active model, validation budget or account action.
