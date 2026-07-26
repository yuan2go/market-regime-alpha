# Current Research Program

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Single current research-program entry point  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** Daily-Quant-Selection-and-Manual-Trading-Research-Program.md; Entry-Position-Lifecycle-Exit-Research-Program.md for current navigation  
> **Superseded By:** None  
> **Related Documents:** Candidate-Research.md, Entry-Research.md, Position-Lifecycle-Research.md, Exit-Research.md, ../roadmap/Phase-D-Work-Packages.md  
> **Code Evidence:** See capability matrix

## Research objective

Build and validate a daily A-share research loop that separates opportunity selection, timing, position continuation, exit, portfolio risk and manual execution effects.

## Ordered program

```text
P0 Platform and evidence contracts
P1 Daily stock/ETF universes and mappings
P1E Tencent exploratory vertical slice using canonical contracts and an EXPLORATORY ceiling
P2 Market/ETF/theme/capital context
P3 Multi-model Candidate predictions and recommendations
P4 Entry assessments
P5 canonical position state, Holding and Exit
P6 outcome matching, daily review and manual attribution
P7 rolling validation, Codex evidence pack and controlled experiments
P8 portfolio/execution simulation
P9 qualified Xuntou PIT replication and shadow observation
```

## Current research question

Can fixed, transparent Candidate models improve the cost-adjusted next-session outcome distribution over matched comparators under reproducible PIT scopes, and can Entry/Exit layers add incremental economic value without hiding Candidate quality?

## Current implementation gate

Before new Alpha, Entry or Exit work, the program must reconcile the
post-consolidation facts, freeze the implemented non-canonical `daily_research`
V1 compatibility semantics, and complete WP-D0 governance hardening. Historical
V1 daily contracts are implementation evidence, not current Phase D authority.

## Frozen discipline

- one primary hypothesis per experiment;
- declared Universe, Decision Time, Target, costs and comparator;
- complete population accounting and explicit missingness;
- chronological/OOS validation;
- negative results retained;
- no automatic mutation or promotion by Codex;
- no real order authority.

## Daily vs slow feedback

Daily: data quality, frozen predictions, outcomes, anomalies and hypotheses.  
20-day: drift and provisional diagnostics.  
60/120-day: promotion, suspension, parameter/Feature changes and strategy allocation decisions.

## Early vertical slice

After platform identity, source manifests and daily universe contracts exist, [WP-D2E](../roadmap/work-packages/WP-D2E-Tencent-Exploratory-Daily-Loop.md) runs the minimal daily B0/B1 prediction → next-session outcome → review loop. It must not tune model weights or acquire formal evidence authority.
