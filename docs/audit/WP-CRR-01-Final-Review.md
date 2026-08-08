# WP-CRR-01 Final Review

> **Status:** CURRENT_STATUS
> **Authority:** Merge-preparation review of `origin/main...4e67def4fb3af9b40c5caebbb138b39d3c8c6a92`
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../roadmap/work-packages/WP-CRR-01-Continuous-Research-Runtime.md, ../evidence/WP-CRR-01-Acceptance.md

## Baseline evidence

- Worktree: `/Users/yuan/projects/market-regime-alpha-worktrees/continuous-research-runtime`
- Branch: `feat/continuous-research-runtime`
- Start commit: `4e67def4fb3af9b40c5caebbb138b39d3c8c6a92`
- Baseline: `origin/main@8de820cd149278bfebbaf18f150a90f36380176d`
- Python: 3.12.2
- uv: 0.11.7
- PostgreSQL: 16.14, isolated loopback database, UTF8/C/C
- Baseline migrations: 001 through 020
- Baseline test collection: 2351 tests in 314 modules
- Baseline full suite: 2351 passed, 0 failed, 0 skipped, 6 warnings,
  8 subtests passed in 238.60 seconds
- Documentation, Ruff, mypy (355 source files), build and diff checks: PASS

## Standards-axis findings

1. `continuous-research` exposed prepare/admit/resume/report/replay but no durable
   due-tick scheduling contract. This contradicted the requested continuous
   control model even though the bounded Tick Runner itself was recoverable.
2. The CLI accepted a caller-supplied session phase rather than deriving it from
   the content-addressed policy and Tick time.
3. `RuntimeTickCommand` compared the UTC calendar date to Trading Date. A
   pre-market Shanghai observation before 08:00 local therefore failed even
   though its market-local Trading Date was correct.
4. child execution carried lineage but no active Claim/Lease/fencing data that a
   child repository could validate at final commit.
5. the existing four-delegate composition could be read as four independent
   writers. Production adapters must expose one existing root operation and
   descendant receipts, not independently recreate Dataset/Feature/Controlled/
   Canonical work.

## Specification-axis findings

1. `AvailableAt > AsOfTime` was accepted by both validated provider payload and
   Evidence Commit contracts. Such Evidence could be consumed by a past Tick.
2. exceptions thrown by a Provider left a STARTED Attempt until Lease recovery;
   invalid temporal Evidence was not immediately recorded as INVALID_RESPONSE.
3. migration 020 allowed more than one Continuous parent run for one Trading
   Date.
4. the original acceptance report correctly disclosed that production
   scheduling and real Provider evidence were absent, but its “sole all-day
   owner” PASS was stronger than the executable CLI/composition evidence.
5. no real free-data multi-Tick rehearsal had established live change/no-change
   behavior. Fixture results cannot close this evidence gap.

## Corrections in this review

- session phase is derived from the selected versioned policy;
- Trading Date is checked in the policy timezone, not against UTC date;
- future Evidence and complete daily bars in the Decision Window fail closed;
- Provider exceptions and invalid Evidence become terminal failed Attempts;
- migration 021 adds one parent per Trading Date and a durable schedule row;
- due Tick reservation, next-Tick projection, non-trading-day stop, concurrent
  reservation and restart recovery are PostgreSQL-authoritative;
- child requests carry Claim, fencing token, version and Lease expiry, while
  idempotency deliberately excludes those ephemeral recovery values;
- the Runner heartbeats around external child work and exposes a final-write
  fence check for child repositories.

## Authority graph

```text
ContinuousResearchSchedule (PostgreSQL projection)
  -> ContinuousResearchRun (one per Trading Date)
    -> RuntimeTick (Claim + Lease + fence + CAS)
      -> ProviderAttempt (operational fact)
        -> EvidenceCommit (validated research input only)
          -> ChangeDecision
            -> existing root research operation
              -> Dataset receipt
              -> Feature receipt
              -> State/Pool/Candidate/Signal/Forecast receipt
              -> Controlled receipt
              -> Canonical receipt
            -> RuntimeTickReceipt
```

Historical Readers and fixed-14:55 Target/TargetId/Replay retain their meaning.
Standalone historical compatibility commands are not a second all-day scheduler.
New continuous writes must carry the parent Tick fence.

## Review verdict

The pre-fix checkpoint is **WP-CRR-01 NO-GO**. After migration 021 and the
focused temporal, recovery, concurrency, PostgreSQL and SQLite gates, the code
review verdict is **WP-CRR-01 GO** for a local engineering checkpoint.

The real free-data rehearsal used the existing `TencentCurrentQuoteClient` with
the exact two-symbol scope `510300.SH` and `600000.SH` at
`2026-08-06T09:37:56+08:00`. The TLS handshake timed out at the three-second
provider deadline before one valid response was received. Result:
`EXTERNAL_PROVIDER_BLOCKED`. No Fixture is presented as live Evidence, and live
change/no-change/last-valid Evidence behavior remains unproven. The exact final
branch HEAD gate is recorded after WP-STATE-01; it does not weaken this GO's
engineering-only evidence ceiling.
