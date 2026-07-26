# Candidate Research

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Current Candidate Discovery research design  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, Validation-and-Ablation.md, ../specs/CandidateRecommendation.md  
> **Code Evidence:** src/market_regime_alpha/candidates/**, src/market_regime_alpha/platform/multi_model_slice.py, tests/platform/test_platform_kernel.py, research/wp3_*, PIT replication

## Goal

Rank a complete eligible cross-section so Top-K has a better cost-adjusted outcome distribution than declared comparators. Candidate is a prediction/ranking layer, not a buy action.

## Current main evidence

- B0 deterministic single-Feature rank: implemented and tested.
- B1 transparent composite percentile rank: implemented and tested.
- complete Candidate Population accounting and explicit rejections: implemented.
- directional accuracy and path diagnostics: implemented.
- provider routing and immutable WP3 artifacts: implemented.
- MR-2B context-conditioned primary hypothesis: not supported in exploratory evidence.
- formal Xuntou PIT replication: success path implemented; actual external input blocked.
- the model currently identified as `platform-b2-volume-momentum-v1` is a fixed-weight transparent composite and therefore a B1 Challenger prototype, not a regularized statistical B2;
- B2 regularized statistical baseline: not implemented on main.

## Primary metrics

- Top-K cost-adjusted benchmark-relative return;
- matched-K excess;
- Rank IC and monotonicity;
- coverage, turnover, concentration;
- MFE/MAE and path order;
- temporal/parameter/seed stability.

## Failure conditions

No matched-K excess, no monotonicity, benefit disappears after costs, concentration in a few dates/themes, unstable under small parameter perturbations or insufficient PIT evidence.
