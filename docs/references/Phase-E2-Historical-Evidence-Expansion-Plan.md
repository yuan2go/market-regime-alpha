# Phase E2 Historical Evidence Expansion Plan

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Branch Base:** `origin/main@e586521676b5b26b98285421023334a43a019ebd`
> **Architecture Decision:** [ADR-011](../architecture/decisions/ADR-011-Phase-E2-Selective-Historical-Evidence-Runtime.md)

## Outcome

Extend the Phase E Pilot Corpus into a real, frozen, multi-symbol A-share
Historical Evidence Runtime while preserving ADR-010 identities and every
Formal PIT / Locked OOS gate.

## Workstream 1: selective Artifact Root reads

- Add an immutable package index that validates PostgreSQL owner/partition
  projections without decoding every Parquet row.
- Add a canonical read query with timeframe, inclusive date range, optional
  symbols and an enforced maximum row count.
- Select partitions through PostgreSQL by exact owner, timeframe, overlapping
  date range and stable symbol buckets.
- Verify selected file checksums and use Parquet predicate pushdown, explicit
  columns and bounded Arrow batches.
- Revalidate record ID/hash/projections, sort deterministically and expose read
  metrics.
- Keep the full verifier for registration, corpus audit and compatibility.

## Workstream 2: bounded Decision-Time materialization

- Replace the materializer's full package object graph with daily selective
  history and a bounded minute-session LRU.
- Preserve full daily history required by frozen EMA/MACD kernels; do not
  silently shorten feature lookback.
- Read only previous/current sessions for Decision and T+1 for Outcome.
- Persist selective-read metrics and exact source partitions in component and
  evidence lineage.
- Prove selected reads equal full reads and resume/replay equals uninterrupted
  execution.

## Workstream 3: historical universe and facts

- Extend the free Research Universe owner with a frozen historical constituent
  basis and exact provider source reference.
- Build the corpus from a real historical CSI 300 constituent response, not a
  current-master retrospective projection or hand-written watchlist.
- Keep listing/delisting facts with provider retrieval lineage.
- Resolve historical ST and suspension from decision-date bars.
- Admit share/market-cap facts only when provider publication time is no later
  than Decision time.
- Persist industry/classification as unknown when only a current snapshot is
  available; never backfill it into prior sessions.
- Remove the Phase E WATCHLIST-only materializer restriction without weakening
  canonical Runtime Scope eligibility.

## Workstream 4: real broader corpus and evidence

- Acquire daily feature warm-up plus bounded 5-minute Decision/Outcome history
  for the frozen constituent set, a real broad-market index and a real ETF.
- Register Raw and Normalized packages under PostgreSQL Authority and record
  exact owner IDs, hashes, locators and physical checksums.
- Run Price -> Volume -> Market Regime -> ETF -> Theme -> Capital -> Dynamic
  Pool -> Candidate -> Signal -> Forecast with unchanged frozen methodology.
- Produce the full ablation chain and T+1 multi-checkpoint Strategy Economics.
- Persist `NEGATIVE`, `INCONCLUSIVE` and `NOT_ESTIMABLE` findings alongside any
  positive result.

## Workstream 5: correctness and delivery gates

- Test future cutoff, T+1 separation, frozen membership, missing-data exclusion,
  ST/suspension, partition corruption, bounded reads and deterministic ordering.
- Test fresh migration plus upgrade from migration 068.
- Run focused and full PostgreSQL suites, pytest, replay/recovery and CLI smoke.
- Run docs links, Ruff, mypy, build and `git diff --check`.
- Review current branch against ADR-011 and this plan, repair P1/P2 correctness
  findings, then commit, push and open a Draft PR.

## Evidence ceiling

Successful engineering and local PostgreSQL validation establishes only
Historical Research engineering evidence. Free data remains `EXPLORATORY`,
`PIT_INCOMPLETE`, `FORMAL_OOS=false`, `CALIBRATED=false`, and cannot authorize
production models, risk changes, broker execution or unattended trading.
