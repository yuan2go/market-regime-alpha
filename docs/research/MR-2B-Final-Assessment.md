# MR-2B Final Exploratory Assessment

> **Status:** COMPLETE — EXPLORATORY NEGATIVE PRIMARY RESULT
>
> **Run:** `mr2b-f2b-cfc48a658d50636610ac`
>
> **Authority:** EXPLORATORY; no Formal OOS Alpha, model winner, production Gate, or trading authority

## Inputs and frozen question

The final assessment consumes the semantically verified chain:

```text
Dataset prr-dataset-fa40337727427b2f1ff63548
→ MR-1 v4 mr1-c06821bf7db2dc787244
→ F2A v2 mr2b-f2a-99cd5a71a92fa5eb0366
→ F2B mr2b-f2b-cfc48a658d50636610ac
```

The Primary asks whether B1-E / 10:30 / BASE daily net lift over the model-population-matched
256-seed median is greater on exact-14:50 auxiliary-watchlist `UP` dates than on `DOWN` dates.
The alternative remained `UP_GREATER_THAN_DOWN` after the negative descriptive input was known.

## Facts

- Dates: 60; UP 27, DOWN 33, FLAT 0, unavailable 0.
- UP mean daily net lift: `0.0003037835251621835`.
- DOWN mean daily net lift: `0.000388258872814705`.
- Observed UP-minus-DOWN effect: `-0.0000844753476525215`.
- Main block bootstrap: 10,000/10,000 valid draws; 95% interval
  `[-0.002375137060807994, 0.0023412463545652395]`.
- Bootstrap probability of a positive effect: `0.4527`; probability of reaching the frozen
  `0.001` floor: `0.1808`.
- Exact one-sided circular-shift p-value: `0.5`.
- Count-preserving permutation robustness p-value: `0.5248475152484752`.
- First-half effect: `0.0021986296399911297`; second-half effect:
  `-0.0020667973571445947`.
- Rolling 20-date windows with positive effect: 14 of 41.
- Leave-one-out sign flips: 18; the effect ranged from `-0.0005647724192922178` to
  `0.0005958060565290064`.
- Largest contribution share: `0.08537164378666917`; top-three share:
  `0.19582532072854764`.
- Seed-panel effects: A `0.00004637052262392369`, B `-0.00021840924095072593`,
  C `-0.0002419741354554528`, D `0.00010110520241135026`.
- Secondary family: 108 total, 107 post-hoc; minimum raw p-value `0.03333333333333333`,
  minimum BH q-value `0.7835858585858586`, zero FDR candidates.

## Statistical inference

The frozen result is:

```text
PRIMARY_HYPOTHESIS_NOT_SUPPORTED
```

Failure reasons are:

```text
OPPOSITE_DIRECTION
BELOW_ECONOMIC_EFFECT_FLOOR
BOOTSTRAP_INTERVAL_INCLUDES_ZERO
RANDOMIZATION_NOT_SIGNIFICANT
TEMPORAL_DIRECTION_INCONSISTENT
COMPARATOR_PANEL_UNSTABLE
```

The old MR-2A `C1` interpretation is therefore not supported after population parity,
multi-seed comparison, and time-dependent uncertainty are enforced.

## Candidate ranking versus Context conditionality

The same Primary model has descriptive mean gross lift of `0.0004117985010719917` versus its
model-population all-Candidate comparator and mean net lift of `0.00035024496637107034` versus
the multi-seed matched-K median. These are positive full-sample descriptive increments.

They do not imply that the `UP` Context strengthens the ranking. The multi-seed conditional
effect is slightly negative. Seed 17 alone would have produced an UP-minus-DOWN net-lift
difference of `0.00187407621955345`, while the 256-seed median produces
`-0.0000844753476525215`. The earlier single-seed interpretation was therefore materially
sensitive to comparator selection.

## Competing-event diagnostic

`MORNING_UP_005_DOWN_005_V1` was available for all 300 B1-E Top-5 slots:

- B1-E UP_FIRST rate: `0.32666666666666666`.
- Model-population all-Candidate UP_FIRST rate: `0.3516666666666667`.
- Multi-seed matched-K median UP_FIRST rate: `0.35333333333333333`.
- B1-E DOWN_FIRST rate: `0.53`.
- All-Candidate DOWN_FIRST rate: `0.5258333333333334`.
- Multi-seed matched-K median DOWN_FIRST rate: `0.5266666666666666`.
- B1-E UP_FIRST lift versus multi-seed median: `-0.026666666666666672`.
- B1-E DOWN_FIRST reduction versus multi-seed median: `-0.0033333333333334103`.
- Opportunity recall: `0.23222748815165878`.

This secondary path diagnostic does not rescue the Primary and does not support a dynamic-exit
promotion from this sample.

## Answers to the closure questions

1. **Was MR-2A C1 supported?** No.
2. **Is there gross ranking lift versus all-Candidate?** Positive descriptively, not formally OOS.
3. **Is there net lift versus multi-seed matched-K?** Positive descriptively over all dates.
4. **Does UP Context enhance that lift?** No; the frozen directional effect is negative.
5. **Is the Context effect stable?** No; chronological halves disagree and two seed panels are negative.
6. **Is the result dominated by a few dates?** It passes the concentration limits, but this does not
   overcome the direction, interval, p-value, or temporal failures.
7. **Did seed 17 bias the old interpretation?** Yes, materially; its positive conditional effect does
   not survive the multi-seed median comparator.
8. **Do fixed 10:30 and competing-event results agree?** Both fail to support an UP-conditional
   advantage; competing-event opportunity lift is also negative.
9. **Continue, modify, or stop?** Preserve the transparent ranking as an exploratory baseline, stop
   the current auxiliary-watchlist conditionality hypothesis, and expand PIT validation before any
   promotion.

## Selected route

```text
Route C — preserve Candidate ranking, do not build a Market Regime Gate,
expand the PIT Dataset, and continue Feature ablation.
```

Suggested next branch:

```text
feat/mr2b-pit-expansion-validation
```

This route does not authorize B2/B3, Entry, Position Lifecycle, Exit, Portfolio, execution, or a
production `MarketContextSnapshot`.

## Risks and invalidation

Current evidence retains current-watchlist backfill bias, unverified historical PIT membership,
an auxiliary Context that is not the full market, a single Dataset, repeated exploratory sample
inspection, reference marks without fill proof, and fee assumptions requiring current verification.

The result is invalidated by an F2A semantic verification failure, Protocol identity mismatch,
insufficient slice coverage, bootstrap instability, comparator-panel instability, excessive result
concentration, future PIT replication failure, or an independent OOS sign reversal.

```text
NO TRADING AUTHORITY
NO PRODUCTION REGIME GATE
NO MODEL WINNER
FORMAL OOS ALPHA NOT ESTABLISHED
```
