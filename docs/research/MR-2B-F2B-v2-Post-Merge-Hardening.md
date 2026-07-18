# MR-2B F2B v2 — Post-Merge Statistical and Contract Hardening

> Status: IMPLEMENTED / LOCALLY VERIFIED
> Authority: EXPLORATORY

F2B v2 preserves the frozen B1-E / 10:30 / BASE `UP_GREATER_THAN_DOWN` research question. It
does not reopen model, endpoint, metric, or direction selection.

## Corrections

The v2 protocol is the sole source for statistical thresholds, draw counts, interval level,
chronological windows, concentration limits, seed-panel requirements, Secondary settings, and
multiple-testing alpha. Before any inference, a typed coverage assessment records UP, DOWN, FLAT,
and unavailable counts. Insufficient slices now publish a valid immutable
`INSUFFICIENT_EVIDENCE` Artifact with fixed-schema empty statistical tables instead of failing in
bootstrap execution.

Artifact semantic verification is no longer an input to the statistical gate. Publication records
verification as pending; the versioned semantic reader separately establishes
`VERIFIED_EXPLORATORY_STATISTICAL_ASSESSMENT`.

Competing-event coverage is now scoped separately for B1-E Top-5, the model population,
multi-seed matched-K, and the global Target table. A global unavailable Target can no longer
inflate the Top-5 missing count.

## Version compatibility

The verifier registry routes `mr-2b-f2b-run-v1` to the unchanged v1 semantic reader and
`mr-2b-f2b-run-v2` to the v2 reader. Historical run `mr2b-f2b-cfc48a658d50636610ac` remains
verifiable; it is not rewritten.

## Actual v2 run

- Dataset: `prr-dataset-fa40337727427b2f1ff63548`
- MR-1: `mr1-c06821bf7db2dc787244`
- F2A: `mr2b-f2a-99cd5a71a92fa5eb0366`
- F2B v2: `mr2b-f2b-v2-3bc505b9e92138ffa2f8`
- Protocol: `sha256:b162725f417f9dcf80aa5e706dba4d88066cd373d1ccd3cb2df43f65bc973cba`

The actual 60-date evidence remains complete: 27 UP, 33 DOWN, no FLAT, and no unavailable dates.
The effect remains `-0.0000844753476525215`; the primary 95% bootstrap interval is
`[-0.002375137060807993, 0.0023412463545652395]`; the one-sided circular-shift p-value remains
`0.5`. The frozen assessment remains `PRIMARY_HYPOTHESIS_NOT_SUPPORTED`.

All 300 Top-5 requests, all 1,200 population requests, and the median 300 matched-K requests had
available competing-event Targets. Global unavailable Target count was zero. The correction
therefore changes generic denominator semantics, not this run's numerical conclusion.

```text
FORMAL OOS ALPHA NOT ESTABLISHED
MODEL WINNER NOT SELECTED
PRODUCTION MARKET REGIME GATE NOT AUTHORIZED
NO TRADING AUTHORITY
```
