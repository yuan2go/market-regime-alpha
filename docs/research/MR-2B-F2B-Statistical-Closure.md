# MR-2B F2B Directional Statistical Closure

> **Status:** IMPLEMENTED / LOCALLY VERIFIED
>
> **Authority ceiling:** EXPLORATORY
>
> **Input:** semantically verified MR-2B F2A v2 evidence

## Research question

Does the pre-existing B1-E ranking have greater daily net lift over the model-specific,
multi-seed matched-K median on auxiliary-watchlist `UP` dates than on `DOWN` dates?

This is a directional question. A large negative difference cannot be promoted by taking
its absolute value.

## Frozen Primary

```text
Hypothesis: mr2b-primary-b1e-1030-base-up-greater-than-down-v1
Model: prr-mvp-1-b1-e-v1
Exit: 10:30
Cost: BASE
Context: mr2b-accepted-watchlist-exact-1450-context-v2
Metric: daily net lift versus multi-seed matched-K median
Effect: mean(metric | UP) - mean(metric | DOWN)
Alternative: UP_GREATER_THAN_DOWN
Minimum slice size: 15
Economic effect floor: 0.001 daily return
```

## Frozen uncertainty protocol

- Primary circular moving-block bootstrap: 10,000 draws, block length 5, seed 20260718.
- Sensitivity block lengths: 3 and 10; neither may replace the Primary length.
- Interval: 95% percentile interval using deterministic R7 quantiles.
- Primary label randomization: every non-zero circular shift, one-sided.
- Auxiliary robustness: 10,000 count-preserving label permutations, seed 20260719.
- Time diagnostics: chronological halves, rolling 20-date windows, and leave-one-date-out.
- Concentration limits: largest absolute contribution at most 0.50; top three at most 0.75.
- Comparator panels: fixed `seed % 4` panels A–D; all four effects must be positive.

## Secondary family

The frozen inventory is 9 models × 4 exits × 3 cost scenarios = 108 comparisons.
The Primary is reported separately. The remaining 107 comparisons use the same
directional metric and circular-shift p-value, with 2,000-draw block-length-5 bootstrap
intervals. Benjamini–Hochberg q-values disclose multiple testing. Secondary results
cannot replace or promote the Primary and cannot select a model winner.

## Path diagnostic

The existing `MORNING_UP_005_DOWN_005_V1` complete-morning-path outcome is retained as
a secondary diagnostic with distinct `UP_FIRST`, `DOWN_FIRST`, `TIMEOUT`, and
`AMBIGUOUS` outcomes. It cannot alter the fixed-return Primary assessment.

## Gate authority

The only outcomes are:

```text
PRIMARY_HYPOTHESIS_SUPPORTED_EXPLORATORY
PRIMARY_HYPOTHESIS_NOT_SUPPORTED
INSUFFICIENT_EVIDENCE
```

Even a fully passing result does not establish Formal OOS Alpha, a model winner, a
production Market Regime Gate, or trading authority.

## Actual run

Run `mr2b-f2b-cfc48a658d50636610ac` consumed Dataset
`prr-dataset-fa40337727427b2f1ff63548`, MR-1 v4
`mr1-c06821bf7db2dc787244`, and F2A v2
`mr2b-f2a-99cd5a71a92fa5eb0366` under Protocol
`sha256:310d32daa26314f7d81896d3357bfbce0fd3b722ee8779111eb1c954ede87f80`.

The Primary result is `PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. The observed directional effect was
`-0.0000844753476525215`; its block-length-5 interval was
`[-0.002375137060807994, 0.0023412463545652395]`, and the exact one-sided circular-shift
p-value was `0.5`. This negative result was retained without changing the direction, model,
endpoint, cost scenario, effect floor, block length, or random seeds.

The semantic reader re-executed the complete Protocol and matched every stored statistical table.
See `MR-2B-Final-Assessment.md` for interpretation and the selected next route.
