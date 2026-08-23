# TEMPORAL_VALIDATION_V1 Contamination Audit

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Classification:** FACT / LIMITATION
> **Repository Baseline:** `main@091324c7e28a2b6a3b89f894d18afc7380486d13`
> **Audit Result:** PASS
> **Audited At:** 2026-08-21

## Question

Was the real population beginning on `2025-07-15` used to choose Factors,
directions, filters, Candidate policy, Top-K, thresholds, costs,
hyperparameters, models or positive results before
`TEMPORAL_VALIDATION_V1` was frozen?

## Audited surfaces

The audit inspected the current code/import tree, Git history, research
protocols and reports, scripts and notebook-like files, WP-ALPHA-RESEARCH-01,
Golden Loop V2, the prior exploratory challenger and the local PostgreSQL
Historical Research/Evidence/Experiment/Research Model owners that contain the
recorded Alpha campaigns.

Owner-derived findings:

- all recorded Historical Research Decision sessions range from `2025-01-02`
  through `2025-07-11`;
- the discovery corpus ends at `2025-07-14`, which supplies the final discovery
  T+1 Target;
- Research Model training samples are empty in the audited campaign databases;
- no Historical Evidence payload, Research Validation payload, governed
  Experiment protocol, Historical run command or Research Model payload contains
  a real external-window observation date;
- repository research reports and executable campaign scripts contain no real
  run over the proposed external population;
- no notebook file exists in the repository.

## Date-shaped fixtures that are not contamination

Repository search finds dates inside the proposed interval in synthetic unit
fixtures, sample CSV data and legacy `dividend_t` tests. One synthetic MACD
ablation fixture names `2025-07-01` through `2025-12-31` as a test range. These
records do not load BaoStock observations for the frozen three intraday Factors,
do not share the WP-ALPHA-RESEARCH-01 Dataset/Panel/Outcome owners, and were not
used for its Factor, direction, Candidate, Top-K, threshold, cost or model
selection. They are therefore date-label overlap, not population access.

This distinction is narrow. It does not assert that arbitrary future research
outside the recorded owners is uncontaminated.

## Conclusion

`PASS`: the proposed 126-session population has not been used for a recorded
research choice governing the frozen three-factor hypothesis. The window may be
frozen before results are read.

Invalidation condition: discovery of any unreviewed artifact or owner showing
that real observations from the window influenced a frozen research choice.
Such evidence must record contamination and block this Experiment identity; it
must not trigger result-driven window shopping.
