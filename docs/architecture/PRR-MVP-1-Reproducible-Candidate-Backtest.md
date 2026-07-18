# PRR-MVP-1 Reproducible Candidate Backtest

> **Status:** approved implementation boundary
> **Data eligibility ceiling:** `EXPLORATORY`

## Reuse boundary

PRR-MVP-1 reuses the existing Tencent/local/BaoStock composite route:

```text
TencentCompositeAcquirer
→ merge_acquisition
→ prepare_composite_data
→ build_tencent_composite_dataset_contract
→ run_tencent_composite_candidate_experiment
```

The first four operations are extracted into one internal Tencent research-execution service. The
existing WP-3 Tencent backend calls that service unchanged in meaning, and PRR calls the same
service. PRR does not add a provider, quality gate, B0/B1 implementation, or Candidate feature
calculation.

## Artifact split

An acquisition evidence directory retains normalized provider responses when exact provider bytes
are unavailable, all source attempts, conflicts, partition metadata, and SHA-256 checksums. A
separate immutable Dataset directory stores normalized Parquet tables, a deterministic dataset
manifest, quality findings, limitations, and checksums. A Run directory references that Dataset and
contains replay outputs rather than duplicating the Dataset.

All three identities are content/configuration based and publication is non-overwriting through a
staging-directory rename. Normalized retained rows are explicitly labelled
`NORMALIZED_PROVIDER_RESPONSE_RETAINED`, never raw provider bytes.

## Replay time semantics

For each chronological Decision Date, the existing Candidate dataset supplies Features with
`as_of <= 14:55 Asia/Shanghai`. Rankings are built before any Target observation is read. The
simulation independently replays every fixed B0 control and B1-A through B1-E ranking for the
Close Return target only. A selected symbol receives a simulated research-mark entry at the
identified decision-session reference price and a simulated exit at the next session close.

Targets (Close Return, MFE, MAE) remain Candidate diagnostics. MFE/MAE never determine a fill or
portfolio return. A 14:55 reference is a research mark, not evidence of a historical executable
fill. Missing rank, reference, or exit data is recorded; rank 6 is never backfilled.

## Authority and exclusions

Tencent/BaoStock/local-cache inputs remain `EXPLORATORY`: historical PIT availability, membership,
buyability, bar finality, adjustment semantics, and order-book execution are not established.
The run reports this ceiling and its limitations. It does not implement an Entry Gate/model,
Position/Exit model, model winner selection, Xuntou runtime export, live order, Level-2 matching,
or any Portfolio approval.
