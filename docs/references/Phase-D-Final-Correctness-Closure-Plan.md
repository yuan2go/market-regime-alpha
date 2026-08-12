# Phase D Final Correctness Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Status:** CURRENT_RESEARCH_PROGRAM

**Goal:** Make the merged Phase D Alpha Proof Foundation deterministically replayable, temporally correct, experiment-isolated, owner-resolved, and truthfully bounded so it can be evaluated for `PHASE_D_ENGINEERING_COMPLETE`.

**Architecture:** Reuse the existing PostgreSQL owners and add a typed lineage spine through existing Strategy, Portfolio, Outcome, Observation Receipt, Historical, Model, and Performance boundaries. Apply forward-only schema correction in migration 067 after public application contracts are tested, while leaving non-consumed Economics, Risk, Attribution, and Ablation kernels explicitly exploratory.

**Tech Stack:** Python 3.12, dataclasses, PostgreSQL 16, psycopg, SQL migrations, pytest, Ruff, mypy, uv, build.

## Global Constraints

- Base every change on `origin/main@383f2430d6879257dae640978a599a1e56f45558`; recheck `origin/main` before publication.
- Do not modify migrations 060-066; schema correction is migration 067.
- Never modify, stage, overwrite, stash, or commit `.idea/modules.xml`.
- PostgreSQL owner identity is `artifact_id + content_hash`; ID-only validation is invalid.
- Derived time cannot precede any required input availability or recorded time.
- Preserve the Modular Monolith and `CONTINUOUS_RESEARCH` as the sole all-day Runtime.
- Do not establish Formal PIT, Formal OOS, Alpha proof, Strategy proof, Production Admission, broker, or trading authority.
- Implement vertical red-green slices through public operator, repository/replay, migration, CLI, and pure-kernel seams.
- Finish each logical task with `git diff --check`, scoped status review, and a dependency-coherent commit.

---

### Task 1: Gate 0 Phase C/D Baseline Recovery

**Files:**
- Modify: `src/market_regime_alpha/application/research_validation/postgres_formal_protocol.py`
- Test: `tests/persistence/postgres/test_formal_protocol_registry.py`
- Test: affected full-suite collection

**Interfaces:**
- Consumes: the existing `FormalProtocolPreOOSOwner` and formal-protocol tables.
- Produces: `load_formal_protocol_pre_oos_owner(connection, artifact_reference)` with fail-before-read identity checks expected by `postgres_qualification.py`.

- [ ] **Step 1: Add a regression test for the missing owner loader**

  Seed the existing formal protocol bundle, call the public loader with its exact
  reference, assert the reconstructed pre-OOS owner, and assert that a mutated
  content hash raises the repository's identity error before dependent reads.

- [ ] **Step 2: Verify the baseline regression is red and collection still fails**

  Run:

  ```bash
  .venv/bin/python -m pytest -q tests/persistence/postgres/test_formal_protocol_registry.py
  .venv/bin/python -m pytest --collect-only -q
  ```

  Expected before implementation: import/attribute failure for
  `load_formal_protocol_pre_oos_owner`.

- [ ] **Step 3: Restore the merged fail-before-read loader contract**

  Port the current Phase C implementation semantics: require a pre-OOS reference,
  load the root owner, compare the exact hash, validate the canonical component
  references, then reconstruct `FormalProtocolPreOOSOwner`. Do not reintroduce a
  generic reference resolver.

- [ ] **Step 4: Verify normal collection and focused Phase C tests**

  Run:

  ```bash
  .venv/bin/python -m pytest --collect-only -q
  .venv/bin/python -m pytest -q tests/persistence/postgres/test_formal_protocol_registry.py tests/persistence/postgres/test_research_qualification.py
  ```

  Expected: collection succeeds; focused tests pass with the isolated PostgreSQL
  URL configured.

- [ ] **Step 5: Commit Gate 0 independently**

  ```bash
  git add src/market_regime_alpha/application/research_validation/postgres_formal_protocol.py tests/persistence/postgres/test_formal_protocol_registry.py
  git diff --cached --check
  git commit -m "fix(phase-c): restore formal protocol owner loading"
  ```

### Task 2: Model Owner-Resolved Training and Inference Integrity

**Files:**
- Modify: `src/market_regime_alpha/application/research_validation/research_model.py`
- Modify: `src/market_regime_alpha/application/research_validation/postgres_research_model.py`
- Modify: `src/market_regime_alpha/cli/research_shadow.py`
- Test: `tests/application/research_validation/test_research_model.py`
- Test: `tests/application/research_validation/test_postgres_research_model.py`
- Test: `tests/cli/test_research_shadow_cli.py`

**Interfaces:**
- Consumes: frozen feature/panel, Target/Outcome, dataset/sample, and configuration owner references supported by existing PostgreSQL owners.
- Produces: an owner-resolved training request whose samples are materialized by the repository; `publish_inference` requires an exact model reference.

- [ ] **Step 1: Write adversarial public-repository tests**

  Add tests proving that a correct model ID with a false hash is rejected, a
  caller-authored sample cannot be published as owner-derived training evidence,
  a source-owner hash mismatch is rejected, and `trained_at` earlier than the
  latest input availability is rejected.

- [ ] **Step 2: Run the model slices and confirm red behavior**

  ```bash
  .venv/bin/python -m pytest -q tests/application/research_validation/test_research_model.py tests/application/research_validation/test_postgres_research_model.py tests/cli/test_research_shadow_cli.py
  ```

  Expected: new false-hash, caller-payload, and time-order tests fail.

- [ ] **Step 3: Separate exploratory payload training from PostgreSQL owner training**

  Keep the pure exploratory kernel explicit in `research_model.py`. Change the
  PostgreSQL path to accept frozen owner references, reload supported owners,
  compare full references and feature/target/configuration identity, derive the
  matrix from owner values, and record the resolved references and maximum input
  availability. Unsupported owner kinds fail closed.

- [ ] **Step 4: Enforce inference identity and temporal monotonicity**

  In `publish_inference`, compare the loaded model reference with the requested
  `artifact_id + content_hash`; require inference generation at or after model and
  input availability. Make CLI input/output describe whether provenance is
  `OWNER_DERIVED` or `EXPLORATORY_CALLER_PAYLOAD`.

- [ ] **Step 5: Run focused model and CLI tests, then commit**

  ```bash
  .venv/bin/python -m pytest -q tests/application/research_validation/test_research_model.py tests/application/research_validation/test_postgres_research_model.py tests/cli/test_research_shadow_cli.py
  git add src/market_regime_alpha/application/research_validation/research_model.py src/market_regime_alpha/application/research_validation/postgres_research_model.py src/market_regime_alpha/cli/research_shadow.py tests/application/research_validation/test_research_model.py tests/application/research_validation/test_postgres_research_model.py tests/cli/test_research_shadow_cli.py
  git diff --cached --check
  git commit -m "fix(phase-d): resolve model training inputs from owners"
  ```

### Task 3: Typed Automatic Observation and Strategy/Portfolio Lineage

**Files:**
- Modify: `src/market_regime_alpha/application/strategy_shadow/observation_builder.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/postgres_observations.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/operator.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/portfolio.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/portfolio_operator.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/postgres_portfolio.py`
- Test: `tests/persistence/postgres/test_shadow_observations.py`
- Test: `tests/application/strategy_shadow/test_observation_builder.py`
- Test: `tests/application/strategy_shadow/test_strategy_shadow_runtime.py`
- Test: `tests/application/strategy_shadow/test_portfolio_operator.py`
- Test: `tests/application/strategy_shadow/test_postgres_portfolio.py`

**Interfaces:**
- Consumes: explicit Decision, settled panel, candidate enrichment, experiment, Target, Outcome, policy, and receipt references.
- Produces: typed automatic-operation context and durable Strategy/Portfolio source lineage with exact owner hashes.

- [ ] **Step 1: Add temporal and multi-experiment adversarial tests**

  Cover T+1 Outcome rejection when asked to write a T-day Portfolio state, two
  same-day Top1/Top3 experiments resolving independently, wrong Decision/Outcome
  hash rejection, and absence of date-only/unique-object fallback.

- [ ] **Step 2: Add durable receipt replay tests**

  Through public repositories, publish an automatic receipt, run Strategy and
  Portfolio, reload/replay their state, and assert the exact receipt, Target,
  Outcome, availability, and source-owner references survive. Mutating any hash
  must fail replay.

- [ ] **Step 3: Introduce a narrow typed lineage context**

  Define one immutable context representing the existing owner chain. Operators
  accept this context or exact root references and ask repositories to reload it;
  they never scan by date. Require Portfolio observation date to equal the
  Outcome's canonical `next_session_date` and require Strategy Entry date to
  remain the Decision session.

- [ ] **Step 4: Persist receipt and source relationships through existing artifacts**

  Add the Observation Receipt, Target/Outcome, experiment, policies, and Strategy
  predecessor references to Strategy/Portfolio durable lineage. Repository
  writers compare every owner ID/hash and all required timestamps before insert;
  replay performs the same checks.

- [ ] **Step 5: Verify and commit the application contract**

  ```bash
  .venv/bin/python -m pytest -q tests/persistence/postgres/test_shadow_observations.py tests/application/strategy_shadow/test_observation_builder.py tests/application/strategy_shadow/test_strategy_shadow_runtime.py tests/application/strategy_shadow/test_portfolio_operator.py tests/application/strategy_shadow/test_postgres_portfolio.py
  git add src/market_regime_alpha/application/strategy_shadow tests/persistence/postgres/test_shadow_observations.py tests/application/strategy_shadow/test_observation_builder.py tests/application/strategy_shadow/test_strategy_shadow_runtime.py tests/application/strategy_shadow/test_portfolio_operator.py tests/application/strategy_shadow/test_postgres_portfolio.py
  git diff --cached --check
  git commit -m "fix(phase-d): bind automatic shadow state to exact lineage"
  ```

### Task 4: Forward Migration 067 Lineage Constraints

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/067_phase_d_correctness_lineage.sql`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `tests/persistence/postgres/test_migrator.py`
- Modify: `tests/persistence/postgres/test_schema.py`
- Modify: affected PostgreSQL fixtures if the repository uses a central expected migration count

**Interfaces:**
- Consumes: the typed lineage relationships defined in Task 3.
- Produces: migration head 067, lineage-aware Portfolio uniqueness, durable full-reference relationships, exact-lineage query indexes, and readable legacy rows.

- [ ] **Step 1: Add migration contract tests**

  Assert 067 is the sole new head, 060-066 hashes/content are unchanged, fresh and
  066-to-067 upgrade paths succeed, legacy Portfolio rows remain readable, and a
  second Portfolio with the same policy but different exact lineage is allowed.

- [ ] **Step 2: Confirm migration tests are red**

  ```bash
  .venv/bin/python -m pytest -q tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_schema.py
  ```

- [ ] **Step 3: Implement the forward-only schema correction**

  Remove policy-only uniqueness without changing legacy rows. Add nullable
  lineage columns/relations for legacy compatibility, full hash columns, checks
  requiring new-lineage fields as a complete set, lineage-aware unique keys, and
  composite indexes in exact query order. Index every new foreign-key lookup.
  Migration statements remain safe under the repository's idempotency runner.

- [ ] **Step 4: Run fresh, upgrade, idempotency, and concurrency migration tests**

  ```bash
  .venv/bin/python -m pytest -q tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_schema.py tests/persistence/postgres -k 'migration or idempot or concurr'
  ```

- [ ] **Step 5: Commit migration 067**

  ```bash
  git add src/market_regime_alpha/persistence/postgres/migrations/067_phase_d_correctness_lineage.sql src/market_regime_alpha/persistence/postgres/schema.py tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_schema.py
  git diff --cached --check
  git commit -m "feat(phase-d): add forward exact-lineage constraints"
  ```

### Task 5: Historical Exact Strategy-to-Performance Resolution

**Files:**
- Modify: `src/market_regime_alpha/application/historical_research/contracts.py`
- Modify: `src/market_regime_alpha/application/historical_research/runner.py`
- Modify: `src/market_regime_alpha/application/historical_research/postgres_session_owner.py`
- Modify: `src/market_regime_alpha/application/historical_research/postgres_journal.py`
- Modify: `src/market_regime_alpha/cli/research_shadow.py`
- Test: `tests/application/historical_research/test_contracts.py`
- Test: `tests/persistence/postgres/test_historical_session_owner.py`
- Test: `tests/persistence/postgres/test_historical_research_runner.py`
- Test: `tests/persistence/postgres/test_historical_research_journal.py`

**Interfaces:**
- Consumes: explicit experiment/configuration/Target/Strategy-policy/Portfolio-policy/root-owner references and Task 3 lineage.
- Produces: exact stage outputs for Strategy, Portfolio, Outcome, and Performance plus deterministic resume/replay.

- [ ] **Step 1: Add cross-experiment contamination tests**

  Seed the same date with Top1 and Top3, different Strategy policies, experiments,
  Portfolio states, Outcomes, and Performance reports. Assert each Historical
  request returns only its exact chain and rejects a mixed ID/hash or legacy
  unbound record.

- [ ] **Step 2: Add deterministic resume/recovery tests**

  Interrupt after each stage, resume from the journal, replay with shuffled row
  insertion order, and assert identical ordered stage references and artifact
  hashes. A replaced predecessor or diverging hash must fail closed.

- [ ] **Step 3: Carry typed references through request and journal**

  Preserve configuration references that the current `session_request()` drops.
  Add explicit strategy/portfolio policy and root references. Journal identity
  includes the complete request so a resume cannot drift to another experiment.

- [ ] **Step 4: Replace date scans with exact owner traversal**

  Resolve Decision -> Strategy -> Portfolio -> Outcome -> Performance through
  verified full references and typed relations. Use canonical dates as asserted
  properties after owner selection, never as the selector. Reject zero, multiple,
  legacy-unbound, or semantically inconsistent matches.

- [ ] **Step 5: Run Historical/CLI integration and commit**

  ```bash
  .venv/bin/python -m pytest -q tests/application/historical_research tests/persistence/postgres/test_historical_session_owner.py tests/persistence/postgres/test_historical_research_runner.py tests/persistence/postgres/test_historical_research_journal.py tests/cli/test_research_shadow_cli.py
  git add src/market_regime_alpha/application/historical_research src/market_regime_alpha/cli/research_shadow.py tests/application/historical_research tests/persistence/postgres/test_historical_session_owner.py tests/persistence/postgres/test_historical_research_runner.py tests/persistence/postgres/test_historical_research_journal.py tests/cli/test_research_shadow_cli.py
  git diff --cached --check
  git commit -m "fix(phase-d): isolate historical experiment lineage"
  ```

### Task 6: Performance and Cross-Owner Temporal Integrity

**Files:**
- Modify: `src/market_regime_alpha/application/strategy_shadow/performance.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/performance_operator.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/postgres_performance.py`
- Modify: `src/market_regime_alpha/application/research_evaluation/postgres_target_repository.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/postgres_observations.py`
- Test: `tests/application/strategy_shadow/test_performance.py`
- Test: `tests/persistence/postgres/test_shadow_performance.py`
- Test: `tests/persistence/postgres/test_shadow_observations.py`

**Interfaces:**
- Consumes: exact Portfolio/state, Outcome, receipt, and source references with recorded/available timestamps.
- Produces: canonically ordered Performance reports whose generation time and owner hashes are valid.

- [ ] **Step 1: Add wrong-hash and time-travel tests**

  Reject a correct state/Portfolio/Outcome ID with a false hash and reject
  `recorded_at`, `materialized_at`, or `generated_at` earlier than any required
  input. Verify equal timestamps are accepted.

- [ ] **Step 2: Add insertion-order invariance tests**

  Supply the same Portfolio state chain in canonical and shuffled order through
  the public Performance builder and assert identical report reference, NAV,
  turnover, cost, return, and drawdown.

- [ ] **Step 3: Normalize by canonical session and validate the chain**

  Sort states by canonical trading-session order, then validate sequence,
  previous-state full reference, Portfolio identity, and monotonic recorded time.
  Generate only after the maximum required timestamp. Writers reload and compare
  all parent owners before publishing.

- [ ] **Step 4: Run Performance/Observation tests and commit**

  ```bash
  .venv/bin/python -m pytest -q tests/application/strategy_shadow/test_performance.py tests/persistence/postgres/test_shadow_performance.py tests/persistence/postgres/test_shadow_observations.py
  git add src/market_regime_alpha/application/strategy_shadow src/market_regime_alpha/application/research_evaluation/postgres_target_repository.py tests/persistence/postgres/test_shadow_performance.py tests/persistence/postgres/test_shadow_observations.py
  git diff --cached --check
  git commit -m "fix(phase-d): enforce shadow temporal owner integrity"
  ```

### Task 7: Conservative Runtime Scope Composition

**Files:**
- Modify: `src/market_regime_alpha/universe/runtime_scope.py`
- Modify: `src/market_regime_alpha/universe/runtime_scope_operator.py`
- Modify: `src/market_regime_alpha/universe/postgres_runtime_scope.py`
- Test: `tests/universe/test_runtime_scope.py`
- Test: `tests/persistence/postgres/test_runtime_scope.py`

**Interfaces:**
- Consumes: provider `included`, listing status, ST, suspension, history, and liquidity facts.
- Produces: one conservative eligibility result where exclusion cannot be relaxed by source combination.

- [ ] **Step 1: Add exclusion-priority truth-table tests**

  Cover provider `included=false`, delisted/non-listed, unknown required listing,
  ST, suspension, insufficient history, and insufficient liquidity. Include a
  case where all later facts pass but an earlier provider/listing exclusion must
  remain excluded.

- [ ] **Step 2: Confirm current combined observation re-admits excluded symbols**

  ```bash
  .venv/bin/python -m pytest -q tests/universe/test_runtime_scope.py tests/persistence/postgres/test_runtime_scope.py
  ```

- [ ] **Step 3: Encode the conservative gate in the public observation model**

  Preserve provider inclusion and listing state in combined observations. Apply
  priority: explicit exclusion/non-listed, then suspension/ST, then history, then
  liquidity, then included. Unknown required inclusion/listing fails closed.

- [ ] **Step 4: Verify persistence/replay and commit**

  ```bash
  .venv/bin/python -m pytest -q tests/universe/test_runtime_scope.py tests/persistence/postgres/test_runtime_scope.py
  git add src/market_regime_alpha/universe tests/universe/test_runtime_scope.py tests/persistence/postgres/test_runtime_scope.py
  git diff --cached --check
  git commit -m "fix(phase-d): preserve conservative runtime exclusions"
  ```

### Task 8: Ablation Metric Correctness

**Files:**
- Modify: `src/market_regime_alpha/application/research_validation/ablation.py`
- Test: `tests/application/research_validation/test_alpha_ablation.py`

**Interfaces:**
- Consumes: observations with explicit canonical session identity, symbol, actual return, variant score, weight/selection, and costs.
- Produces: per-variant IC, RankIC, TopK, Spread, Hit Rate, Incremental Lift, Turnover, Cost, Net Return, NAV, and Drawdown independent of insertion order.

- [ ] **Step 1: Add opposite-ranking Hit Rate test**

  Use known returns `(+10%, -10%)` and two exactly opposite rankings with Top1.
  Assert one variant Hit Rate is `1.0` and the other is `0.0`; the expected values
  are literals, not recomputed by the implementation algorithm.

- [ ] **Step 2: Add per-variant Turnover and shuffle tests**

  Give two variants different prior/current holdings on two sessions. Assert
  literal turnover values from `0.5 * sum(abs(current_weight - prior_weight))`.
  Shuffle all observations and assert all metrics, NAV, and Drawdown are equal.

- [ ] **Step 3: Implement canonical per-variant paths**

  Group by explicit session identity, sort canonically, rank each variant, derive
  its actual TopK weights, compute Hit Rate only from selected returns, and carry
  that variant's weights to the next session. Align Incremental Lift by session
  and derive all path metrics from the ordered net-return series.

- [ ] **Step 4: Run the ablation suite and commit**

  ```bash
  .venv/bin/python -m pytest -q tests/application/research_validation/test_alpha_ablation.py
  git add src/market_regime_alpha/application/research_validation/ablation.py tests/application/research_validation/test_alpha_ablation.py
  git diff --cached --check
  git commit -m "fix(phase-d): correct variant path metrics"
  ```

### Task 9: Strategy Entry, Holding Path, and Exit Semantics

**Files:**
- Modify: `src/market_regime_alpha/application/strategy_shadow/economics.py`
- Modify: upstream Strategy observation adaptation only where required by the public type contract
- Test: `tests/application/strategy_shadow/test_economics.py`

**Interfaces:**
- Consumes: separate Entry observation, Holding path, Exit observation, side, prices, barriers, and cost assumptions.
- Produces: fail-closed Economics results that never infer an unobserved intrabar execution path.

- [ ] **Step 1: Add T versus T+1 execution tests**

  Assert normal T Entry stays valid when T+1 is limit-up, limit-down, or suspended;
  those T+1 conditions affect Holding/Exit only. Add side-aware buy limit-up and
  sell limit-down tests and missing Entry/Exit evidence tests.

- [ ] **Step 2: Preserve barrier ambiguity adversarial coverage**

  Keep and strengthen the same-5-minute-bar test so simultaneous upper/lower
  touches yield the literal status `AMBIGUOUS_NOT_OBSERVABLE` regardless of input
  ordering.

- [ ] **Step 3: Split the public market-path contract**

  Replace the aggregated condition input with immutable Entry, Holding, and Exit
  evidence. Entry fillability uses only Entry evidence; Holding records path
  conditions without rewriting Entry; Exit uses only Exit evidence. Apply cost
  at the actual modeled leg and never infer a fill between bar endpoints.

- [ ] **Step 4: Run Economics/Strategy tests and commit**

  ```bash
  .venv/bin/python -m pytest -q tests/application/strategy_shadow/test_economics.py tests/application/strategy_shadow
  git add src/market_regime_alpha/application/strategy_shadow tests/application/strategy_shadow
  git diff --cached --check
  git commit -m "fix(phase-d): separate strategy execution conditions"
  ```

### Task 10: Runtime Boundary and Current Documentation

**Files:**
- Modify: `docs/architecture/Research-Strategy-Lifecycle.md`
- Modify: `docs/architecture/Authority-Map.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/status/Roadmap.md`
- Test: `scripts/check_docs_links.py`

**Interfaces:**
- Consumes: final executable composition and tests from Tasks 1-9.
- Produces: code-accurate Phase D status and explicit evidence ceiling.

- [ ] **Step 1: Re-audit actual runtime consumers**

  Trace CLI and `CONTINUOUS_RESEARCH` composition for Historical, Observation,
  Performance, Model, Economics, Risk, Attribution, and Ablation. Record only
  executable current-HEAD consumers.

- [ ] **Step 2: Update current documents truthfully**

  Describe the typed spine and migration 067. Keep Economics, Portfolio Risk,
  Attribution/Feedback, and Ablation exploratory when no natural formal consumer
  exists. Mark Phase D engineering complete only if every required gate is green;
  otherwise document the precise remaining blocker.

- [ ] **Step 3: Validate documentation and commit**

  ```bash
  .venv/bin/python scripts/check_docs_links.py
  .venv/bin/python -m pytest -q tests/scripts/test_check_docs_links.py
  git add docs
  git diff --cached --check
  git commit -m "docs(phase-d): record final correctness boundary"
  ```

### Task 11: Final Verification, Review, and Draft PR

**Files:**
- Review: all changes from merge-base `origin/main`
- Create only if repository convention requires it: final local evidence artifacts excluded from Git unless explicitly tracked by existing policy

**Interfaces:**
- Consumes: final branch HEAD and isolated PostgreSQL 16 database.
- Produces: command-by-command evidence, clean pushed branch, Draft PR, and resolved P1/P2 correctness review.

- [ ] **Step 1: Run fresh and upgrade PostgreSQL validation**

  Provision a project-scoped PostgreSQL 16 test database. Run the repository's
  fresh migration, 066-to-067 upgrade, idempotency, concurrency, replay, recovery,
  and CLI integration suites with the exact database URL exported only to the
  test process.

- [ ] **Step 2: Run every repository quality gate on final HEAD**

  ```bash
  uv sync --frozen --extra dev --extra postgres
  .venv/bin/python scripts/check_docs_links.py
  .venv/bin/python -m pytest -q tests/scripts/test_check_docs_links.py
  .venv/bin/python -m pytest -q tests/platform
  .venv/bin/python -m pytest -q
  .venv/bin/python -m ruff check .
  .venv/bin/python -m mypy
  .venv/bin/python -m build
  git diff --check
  ```

  Record each result as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`. No failed or
  blocked required local gate permits Phase D closure.

- [ ] **Step 3: Review against Standards and Spec**

  Inspect `git diff origin/main...HEAD`, repository contracts, the approved
  design, and every requested adversarial case. Correct all P1/P2 findings, rerun
  affected focused suites, then rerun any invalidated final gate.

- [ ] **Step 4: Commit final review corrections and verify cleanliness**

  ```bash
  git diff --check
  git status --short
  ```

  Expected: no unstaged or staged files and `.idea/modules.xml` absent from branch
  history and status.

- [ ] **Step 5: Recheck latest main, push, and open a Draft PR**

  Fetch `origin/main`, compare the merge base and changed migration head, push
  `codex/phase-d-final-correctness-closure`, and open a Draft PR with evidence and
  explicit non-claims. Do not merge.

- [ ] **Step 6: Process PR correctness review**

  Read thread-level review state. Resolve every actionable P1/P2 correctness
  issue in code, tests, and documentation; commit and push; rerun affected and
  final gates. If no GitHub Actions workflow runs, record `CI_NOT_RUN` rather than
  CI success.
