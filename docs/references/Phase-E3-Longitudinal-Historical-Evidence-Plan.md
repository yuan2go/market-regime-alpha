# Phase E3 Longitudinal Historical Evidence Plan

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Branch Base:** `origin/main@796b868c55bc9a3e58e427cbbfbba101a5936606`
> **Architecture Decision:** [ADR-012](../architecture/decisions/ADR-012-Phase-E3-Longitudinal-Historical-Evidence-Runtime.md)

## Goal

Run the unchanged Phase E chain on at least six months of real, effective-dated
CSI 300 history while keeping membership, business facts, Decision/Outcome
time, owner lineage and aggregation deterministic and bounded.

## Workstream 1: effective-dated cohorts

- Extend the historical-universe acquisition command with an inclusive range
  mode that scans real trading sessions, preserves every raw Provider response
  and publishes the distinct effective-date cohort owners.
- Publish one exact-range Historical Constituent Timeline mapping every queried
  session to an effective cohort; incomplete cohort bindings fail closed.
- Accept an exact sorted set of cohort snapshot IDs in corpus acquisition and
  acquire their included-symbol union plus explicit index/ETF context.
- Resolve multiple `FREE_RESEARCH_UNIVERSE` references in the materializer and
  select exactly one active cohort per Decision Session.
- Test boundary-day switching, pre-first-cohort failure, duplicate effective
  dates, listing/delisting projection and uninterrupted/replay identity.

## Workstream 2: historical Security Facts

- Add migrations 071–075 for immutable facts, keyset component streaming,
  exact constituent timelines and projected symbol/target Outcome labels.
- Add canonical contracts and one PostgreSQL repository for Industry,
  published total/liquid shares, adjustment events and dividend/split/rights
  facts.
- Acquire BaoStock `query_stock_industry`, `query_profit_data`,
  `query_adjust_factor` and `query_dividend_data` responses without Provider
  fallback; archive exact responses under Artifact Root and use
  content-verified per-query recovery checkpoints.
- Bind the fact owner to the Historical Command and materialize Industry,
  market-cap and corporate-action coverage only from effective/published rows.
- Reject corporate-action-contaminated raw labels and Economics explicitly.

## Workstream 3: bounded longitudinal execution

- Replace whole-owner Daily retention with a declared rolling lookback and
  bounded LRU that still covers every frozen canonical feature requirement.
- Add deterministic keyset component iteration and symbol/time-cutoff Outcome
  reads to `PostgresHistoricalMaterializationRepository`.
- Refactor the canonical Ablation kernel around one incremental accumulator;
  keep the existing tuple API as a compatibility wrapper over the same code.
- Stream Panel batches through Ablation, Strategy metric, corpus summary and
  Challenger construction without a whole-run component or observation tuple.
- Record deterministic component-batch/session-cross-section bounds in Corpus
  Summary Evidence. Record host-dependent peak RSS and wall time in the durable
  execution report beside exact owner/run IDs so they cannot perturb canonical
  replay identity.

## Workstream 4: real execution and correctness proof

- Acquire daily warm-up plus at least six months of five-minute observations
  for the cohort union and real `000300.SH`/`510300.SH` context.
- Run one interrupted/resumed corpus, one independent uninterrupted corpus and
  exact replay; compare ordered runs, sessions, stage receipts, components,
  bindings, evidence, metrics and fact/cohort references.
- Audit Decision source cutoffs, T+1 separation, cohort membership, missing
  target preservation, corporate actions, Forecast samples, Signal states,
  period/regime slices and ranking-versus-executable economics.
- Persist every positive, negative, inconclusive and not-estimable finding.

## Workstream 5: qualification and publication

- Run migrations 071–075 fresh, upgrade, idempotency and concurrency tests plus
  corruption/adversarial, CLI, PostgreSQL, full pytest, docs, Ruff, mypy, build
  and `git diff --check` gates.
- Update the sole current docs, capability/gap/roadmap and research result
  registry with exact evidence IDs and explicit non-claims.
- Perform Standards and Spec review, repair all P1/P2 findings, commit, push and
  open a Draft PR. Record `CI_NOT_RUN` until Actions is observed.

## Non-negotiable frozen semantics

- Forecast `minimum_usable_samples=20` and Signal thresholds are unchanged.
- Current classifications never fill historical facts.
- Raw Provider retrieval time is never rewritten to historical availability.
- Formal PIT, Locked OOS, Calibration, Production Admission and trading gates
  remain closed.
