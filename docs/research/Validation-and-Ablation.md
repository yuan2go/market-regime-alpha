# Validation and Ablation

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Current model-evaluation and experiment discipline  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/07-Validation-Constitution.md, Negative-and-Inconclusive-Results.md  
> **Code Evidence:** research/mr2b_*, PIT replication readers/verifiers

## Comparable lane

Direct model comparison requires the same Universe, Decision Time, Target, horizon, cost model, split protocol, evaluation window and population accounting.

## Required stages

```text
Development
→ chronological walk-forward
→ validation access under budget
→ sealed test when predeclared
→ shadow observation
→ live-observed evidence
```

## Required comparators

- simple B0/B1 baselines;
- same-population matched-K random panels;
- parent model for every challenger;
- fixed entry/exit baselines when evaluating timing;
- benchmark/universe-relative returns.

## Ablation

One primary change per challenger. Preserve Feature, model, Target, Universe, cost and code identities. Report negative and unavailable diagnostics explicitly.

## Multiple testing

Track experiment/parameter/Target/validation access budgets. Use family-wise/FDR or deflated performance controls when selecting among many models. A leaderboard winner after unrestricted search is not an OOS winner.
