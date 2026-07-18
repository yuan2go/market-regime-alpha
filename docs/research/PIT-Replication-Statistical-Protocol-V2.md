# PIT Replication Statistical Protocol V2

The frozen question is unconditional: does `prr-mvp-1-b1-e-v1` Top-5 produce positive daily net
lift over the same model population's 256-seed matched-K median at exact next-session 10:30?

The Protocol fixes B1-E model-spec hash, ranking Target, 10:30 evaluation mark, BASE primary cost,
LOW/BASE/HIGH cost robustness, Top-K 5, seeds 0–255, minimum 250 dates, average population 100,
minimum symbol coverage 0.95, economic floor 0.001, circular moving-block bootstrap, 10,000 draws,
block length 5, seed 20260718, and 95% percentile interval.

Assessment also records first/second half, rolling 20-date windows, leave-one-date-out bounds,
largest and top-three absolute contribution shares, four deterministic seed panels, and cost
robustness. These diagnostics are predeclared and cannot be used to select a favorable time slice,
seed panel, or cost assumption.

Allowed formal states are:

```text
PIT_REPLICATION_SUPPORTED_REHEARSAL
PIT_REPLICATION_NOT_SUPPORTED
INSUFFICIENT_PIT_EVIDENCE
INVALID_PIT_EVIDENCE
BLOCKED_EXTERNAL_PROVIDER_INPUT
PARTITION_SPEC_REQUIRED
```

None establishes Formal OOS Alpha, a model winner, production readiness, or trading authority.

