# PIT Candidate Replication Charter

> **Status:** FROZEN FOUNDATION — EXTERNAL XUNTOU INPUT REQUIRED
>
> **Experiment:** `pit-b1e-unconditional-candidate-lift-replication-v1`
>
> **Authority ceiling:** `REHEARSAL_NOT_FORMAL_OOS`

## Research question

Does the already frozen B1-E ranking produce stable daily net lift over a model-population,
same-K, same-cost, 256-seed matched-K median in an expanded historical point-in-time Universe?
This replication is unconditional: the rejected auxiliary-watchlist UP/DOWN hypothesis is not
part of the protocol.

## Frozen model and comparator

```text
Candidate model       prr-mvp-1-b1-e-v1
Ranking source Target target-r5-decision-reference-to-next-session-close-return-v1
Evaluation exit       10:30
Cost scenario         BASE
Top-K                 5
Primary metric        daily-net-lift-vs-model-population-multiseed-median-v1
Matched-K algorithm   mr1-matched-k-sha256-rank-blind-v1
Seeds                 0..255
Context               NONE
```

B1-E components, directions, normalized weights, complete-case rejection, Top-K, exit, cost,
liquidity threshold, and seed family are frozen before opening the validation partition. No model
winner or Feature tuning may be selected on that partition.

## Partition roles

```text
Existing 60-date Tencent/BaoStock evidence
    DEVELOPMENT_EXPLORATORY_CURRENT_60_V1

First untouched expanded Xuntou PIT partition
    REPLICATION_VALIDATION_FUTURE_XUNTOU_PIT_V1

Later separately sealed evidence
    OOS_TEST (not assigned yet)
```

Partition identities may not overlap. The current watchlist backfill is not historical membership
and cannot be relabelled as validation data.

## Provider and PIT evidence

Xuntou normalized native bundle v3 is the only accepted provider input. The preflight is bound to
content bytes and does not fall back to Tencent. The existing Trading Calendar, Historical PIT
Universe, Historical Trading Eligibility, provider-rehearsal artifact, provider router, and WP-3
Candidate seams remain authoritative; this work does not create a second Universe system.

The Candidate Population is:

```text
Historical PIT Universe membership
INTERSECT
exact-Decision-Time ELIGIBLE and explicitly BUYABLE instruments
```

Missing listing date, ST, suspension, liquidity, availability/finality, or buyability evidence is
fail-closed. `UNKNOWN` is never treated as `ELIGIBLE` or `BUYABLE`.

## Quality and minimum evidence

The protocol requires at least 250 Decision Dates, average population size 100, and symbol coverage
0.95. Quality evidence must retain provider retrieval and availability times, bar finality, calendar
and Universe identities, membership source, listing/ST/suspension/liquidity/buyability evidence,
Target availability, and Decision-Time cutoff.

## Current execution state

No real normalized Xuntou bundle is available in the repository environment. The application
therefore publishes an immutable `BLOCKED_EXTERNAL_PROVIDER_INPUT` Artifact containing protocol,
preflight, blocker reason, limitations, report, and full checksums. It produces no replication
metrics and does not substitute Tencent or synthetic provider data.

## Feature-ablation boundary

The typed `CandidateFeatureExperiment` contract reserves future development-only ablations. It does
not execute or select VWAP, late-session, price-location, industry, ETF, or flow Features on the
validation partition. Any future ablation must have a separate development partition and cannot
change this frozen replication.

## Authority

Allowed future result states are `PIT_REPLICATION_SUPPORTED_EXPLORATORY`,
`PIT_REPLICATION_NOT_SUPPORTED`, `INSUFFICIENT_PIT_EVIDENCE`, and
`BLOCKED_EXTERNAL_PROVIDER_INPUT`.

```text
FORMAL OOS ALPHA NOT ESTABLISHED
MODEL WINNER NOT SELECTED
NO MARKET REGIME GATE
NO ENTRY / PORTFOLIO / EXECUTION AUTHORITY
```
