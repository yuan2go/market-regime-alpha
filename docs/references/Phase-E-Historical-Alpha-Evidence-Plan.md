# Phase E Historical Alpha Evidence Production Plan

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Approved Design:** ADR-010
> **Base:** `origin/main@8cd363d6b203df5413d20369f5d48100620c4246`

## Execution status

Tasks 1-8 have completed for one representative real-data vertical slice. The
frozen corpus observes six liquid stocks across 667 Decision Sessions and 4,002
T+1 panel samples. Exact Raw/Normalized owners contain 213,738 source/normalized
rows, interruption recovery and replay are deterministic, and the five evidence
kinds are durable. The effective chain is net negative after assumed costs;
ETF/Capital/Candidate/Signal/Forecast lift is `NOT_ESTIMABLE`. Broader context,
cross-section and calibrated execution facts remain the next evidence work, not
an excuse to add infrastructure or tune this experiment.

## Goal

Produce a real, owner-resolved, resumable and deterministic exploratory A-share
historical corpus from frozen free data, then use existing canonical kernels to
measure component-level Alpha and Strategy Economics without weakening Formal
PIT/OOS gates.

## Global constraints

- PostgreSQL is the only business Authority; Artifact Root stores immutable bytes.
- All Artifact reads start from an exact PostgreSQL owner ID/hash/locator and
  verify the complete physical and logical identity.
- True provider retrieval times are preserved; retrospective data never claims
  historical availability or Formal PIT.
- Live and Historical share numerical Feature, State, Candidate, Signal and
  Forecast kernels. Authority/time adapters remain explicit and separate.
- Missing, excluded, suspended, ST, price-limit, provider-error and
  not-estimable states are durable evidence.
- One experiment has one frozen configuration and exact Dataset lineage; no
  date-only or latest-owner selection is allowed.
- Complete each dependency-coherent checkpoint with focused tests,
  `git diff --check`, a scoped review and a logical commit.

## Task 1: Architecture and executable storage contracts

**Create/modify:**

- `application/historical_corpus/contracts.py`
- `application/historical_corpus/artifacts.py`
- `application/historical_corpus/postgres_repository.py`
- migration `068`
- focused contract, artifact, corruption and PostgreSQL tests

Implement typed Raw Archive, Normalized Dataset, partition coverage and Corpus
owners. Reuse `artifact-root-v1`; add no locator discovery API. Implement staged
atomic publication, exact checksum coverage, idempotent recovery after atomic
install, owner registration/reload and corruption detection. Add foreign keys,
immutable conflict checks and indexes matching owner/session/partition replay.

## Task 2: Raw BaoStock acquisition and deterministic normalization

**Create/modify:**

- bounded BaoStock archive adapter under `application/historical_corpus`
- deterministic daily/5m normalization and sharded Parquet package
- provider, normalization, coverage and missingness tests

Freeze provider-returned fields/rows and exact request/retrieval metadata. Keep
library re-encoding explicit. Normalize canonical symbols, timezones, OHLCV,
amount, trade status, ST, adjustment basis, duplicate and parse failures. Write
annual daily and monthly 5m stable-symbol buckets; validate all row, date,
symbol, missingness and checksum projections before registration.

## Task 3: Historical Decision-Time adapter and kernel reuse

**Create/modify:**

- `application/historical_corpus/materialization.py`
- narrow pure-kernel seams in existing Feature/State/Candidate/Signal/Forecast
  modules where authority adapters currently prevent retrospective use
- materialization, no-future-input and canonical-kernel-equivalence tests

Build an exact Dataset-backed view for each DecisionTime with
`event_end <= DecisionTime`. Build Outcome views separately from canonical T+1
sessions. Reuse canonical numerical kernels and produce immutable historical
Feature, Market/ETF/Theme/Capital State, Dynamic Pool, Candidate, Signal and
Forecast components. Record complete input bar ranges and hashes so T+1
contamination is mechanically detectable.

## Task 4: Resumable corpus production and Historical Runner integration

**Create/modify:**

- `application/historical_corpus/producer.py`
- existing `application/historical_research` owner/runner composition
- CLI acquisition, produce, inspect, resume, verify and replay commands
- recovery, lease/fence, idempotency, determinism and CLI tests

Freeze a Corpus command and create partition/session claims in PostgreSQL.
Actively materialize missing Decision-Time owners, persist exact outputs and
then let the existing Historical Research session/replay boundary resolve them.
Prove interruption after each publication/registration boundary, same-process
retry, process restart, resume/uninterrupted equality and cross-experiment
isolation.

## Task 5: T+1 Outcomes, panel, ablation and Strategy Economics

**Create/modify:**

- owner-resolved Outcome and Research Panel builders
- existing Phase D ablation/economics callers and PostgreSQL Research Validation
  persistence
- performance/evidence registry integration
- metric, slice, fillability, ledger and negative-result tests

Produce T+1 Open/09:45/10:00/10:30/11:30/Close, MFE and MAE without exposing
them to Decision-Time computation. Execute the full nested ablation path and
Regime/Liquidity/Market Cap/Volatility/Theme/Industry slices. Execute Strategy
Economics with Entry/Holding/Exit, suspension, limit, lot, ADV, commission,
stamp duty, slippage and impact constraints. Persist all classifications and
prove `gross - cost = net` at trade, session and report levels.

## Task 6: Owner-resolved exploratory challenger

**Create/modify:**

- corpus-to-training-matrix owner loader
- existing Research Model PostgreSQL repository and CLI
- owner/hash/time/gate and deterministic model tests

Accept exact Corpus/Feature/Target/configuration references, reload owners and
derive the matrix internally. Publish only an exploratory regularized-linear
challenger. Reject caller matrices on the owner-derived path and keep
`PIT_INCOMPLETE`, `FORMAL_MODEL_QUALIFIED=false`, `FORMAL_OOS=false`, and
`CALIBRATED=false` fail-closed.

## Task 7: Real vertical slice and representative corpus

Use BaoStock raw-unadjusted Daily/5m history for a frozen, sufficiently liquid
representative A-share scope with market/ETF context. First run a small vertical
slice through every owner and replay. After correctness is demonstrated, expand
to approximately two to three years within practical provider/runtime bounds.

Persist and report:

- dates, sessions, symbols, raw/normalized rows and samples;
- coverage, missingness, provider/parse failures and exclusions;
- IC, RankIC, ICIR, TopK, spread, hit rate, MFE, MAE and incremental lift;
- turnover, gross, cost, net, drawdown and capacity;
- Regime/Liquidity/Market Cap/Volatility/Theme/Industry slices;
- positive, negative, inconclusive and not-estimable findings;
- exact replay/recovery identities and evidence ceilings.

## Task 8: Full qualification and delivery

Run on final exact branch HEAD with isolated PostgreSQL 16:

```bash
uv sync --frozen --extra dev --extra postgres
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
git diff --check
```

Also run fresh/067-to-068 upgrade/idempotency/concurrency, historical
replay/recovery, corruption and CLI integration tests. Review the full branch
diff for P1/P2 research-correctness blockers. Commit logical checkpoints, push
the branch and open a Draft PR. Report GitHub Actions as `CI_NOT_RUN` unless it
actually executes. Do not merge the PR.
