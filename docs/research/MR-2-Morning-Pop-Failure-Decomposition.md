# MR-2 Morning-Pop Failure Decomposition

MR-2 is a bounded `EXPLORATORY` diagnosis of the fixed B0/B1 morning-pop replay. It does not
create a model, select a winner, or authorize an Entry, Position, Exit, Portfolio, or execution
change.

## Corrected MR-1 conventions

- Decision Time is 14:55 Asia/Shanghai; the entry reference is the latest completed five-minute
  bar at or before 14:50. It is a research mark, not an exact 14:55 or historical fill claim.
- Every Top-K slot begins at `1 / top_k`. Missing exit evidence remains a zero-return cash or
  unresolved slot; completed slots are not reweighted.
- Candidate gross and net baselines are separate. The net baseline uses the same declared cost
  mechanics but remains a non-tradable cross-sectional diagnostic.
- Cost ratio divides actual transaction cost by actual completed entry notional.
- 10:30 MFE/MAE and path Targets require the complete 09:35–10:30 five-minute grid.

## Path Targets

MR-2 retains endpoint returns and adds next-session opening-gap return, complete-morning MFE/MAE,
time of MFE, MFE-capture ratios at 09:35/10:00/10:30, and three competing-event Target variants.
Competing events use only the next-session 09:35–10:30 path. Same-bar dual barrier touches are
`AMBIGUOUS`; missing any required path bar is `UNAVAILABLE / INCOMPLETE_MORNING_PATH`.

## Current run

The corrected MR-1 input was
`data/processed/mr1_morning_pop_runs/mr1-f3938fc682d853c8e974/`, derived from immutable Dataset
`prr-dataset-fa40337727427b2f1ff63548`. The resulting MR-2 run is
`data/processed/mr2_failure_decomposition_runs/mr2-c6080d9999caff4f8840/`.

Its aggregate absolute morning Spearman IC was approximately 0.0455. Model failure rows show a
mixture of `NO_GROSS_SIGNAL`, `NO_CROSS_SECTIONAL_ALPHA`, `COST_FRAGILE`, `DRAWDOWN_FAILED`, and
limited `REGIME_UNSTABLE` evidence. The explicitly available composite-data slices show sign
splits in Top-5 excess, while ETF/sector context remains `UNAVAILABLE` rather than inferred.

The evidence-led conclusion is:

```text
C. SIGNAL_EXISTS_ONLY_IN_SPECIFIC_REGIMES
```

This remains a small auxiliary-data finding, not confirmation that a production regime gate
should be built. Any next regime work requires broader history, historical PIT validation, and
walk-forward confirmation before it can change Candidate research direction.
