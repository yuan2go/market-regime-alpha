# H5 Artifact-Derived Thesis Health Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for approved H5 implementation
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-04-h5-artifact-derived-thesis-health-design.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** Plan starts from `feat/h5-artifact-derived-thesis-health@df5c731da018819d9710f2d2f1ecffb4995fa082`; implementation evidence will be bound to later checkpoints.

> **For agentic workers:** Execute task-by-task with test-driven development. Every behavioral step starts with a focused failing test, then the minimum implementation, then a focused green run.

**Goal:** Replace caller-authored Thesis-health conclusions in the new operational path with a deterministic, content-addressed, replayable and durable H5 observation derived from verified Artifacts and explicit machine rules.

**Architecture:** Put new H5 domain behavior in `position/thesis_health.py`, storage neutrality in a Position repository Protocol, SQLite authority in `position/sqlite_thesis_health.py`, orchestration in a bounded Application Service and CLI, and a thin V2-only adapter over shared Holding/Exit decision internals. Preserve V1 Readers and avoid a complete LifecycleReview V2 package.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum/Protocol, canonical JSON/SHA-256, existing Artifact Readers, SQLite `BEGIN IMMEDIATE`, argparse, pytest, Ruff, mypy and Python build.

## Global constraints

- No caller may submit component support, triggered condition or final health state to H5.
- No natural-language description or condition-name parsing.
- No `LifecycleReviewRunV2`, H6, H4.5, H7, H8 or H9 implementation.
- No ManualTrade, Fill, Position or Broker mutation.
- No automatic Thesis transition or H4 decision.
- Preserve all H4 behavior and known H4.5/H7 gaps.
- Preserve `.idea/modules.xml` and exclude it from every commit.
- Preserve formal PIT/OOS, Shadow, production and trading-authority non-claims.

---

### Task 1: Typed rules, configuration and exact Thesis binding

**Files:**
- Create: `src/market_regime_alpha/position/thesis_health.py`
- Create: `tests/position/test_thesis_health_rules.py`
- Modify: `src/market_regime_alpha/position/__init__.py`

**Red tests:**

- canonical round trip and identity for every typed rule;
- configuration and rule-set identity/hash tamper;
- duplicate, missing and extra condition mapping;
- `InvalidationKind` mismatch;
- unknown typed rule;
- `TIME_AFTER` different from `thesis.time_invalidation`;
- strict numeric, enum, ordering and timezone inputs.

Run:

```bash
python -m pytest -q tests/position/test_thesis_health_rules.py
```

Expected first result: import/contract failures.

**Green implementation:**

- add rule/config schema constants and content-derived identities;
- implement typed rule union and exact canonical dispatch;
- implement complete explicit state mappings and freshness/path thresholds;
- implement `ThesisInvalidationRuleSet.validate_for(thesis)`;
- export only public H5 domain types.

Run the same test until PASS, then run Ruff on affected files.

### Task 2: Manual evidence, replay bundle and Observation V2 contracts

**Files:**
- Modify: `src/market_regime_alpha/position/thesis_health.py`
- Create: `tests/position/test_thesis_health_contracts.py`

**Red tests:**

- manual evidence canonical round trip, identity/hash and timezone rules;
- V2 exact fields, canonical round trip and identity/hash tamper;
- input bundle strict actual types and canonical round trip;
- prior ID/hash/state fields are paired and reconstructible;
- first `DATA_INSUFFICIENT` allows nullable effective state;
- authority ceiling strings cannot inflate.

**Green implementation:**

- add content-addressed `ManualInvalidationEvidence`;
- add private, content-addressed `ThesisHealthInputBundle`;
- add content-addressed `ThesisHealthObservationV2` with current/creation
  evidence, component states, prior lineage and authority limitations;
- ensure callers cannot instantiate inconsistent derived states.

Run:

```bash
python -m pytest -q tests/position/test_thesis_health_contracts.py
```

### Task 3: Artifact scope, lineage and freshness validation

**Files:**
- Modify: `src/market_regime_alpha/position/thesis_health.py`
- Create: `tests/position/test_thesis_health_builder.py`
- Create: `tests/position/thesis_health_fixtures.py`

**Red tests:**

- symbol mismatch and missing primary theme;
- Theme or Capital theme/symbol absence/mismatch;
- Signal not bound to current Candidate;
- Path not bound to current Signal;
- Candidate not bound to current Market/Theme/Capital;
- Capital not bound to current Theme;
- incompatible research DecisionTime/SourceManifest lineage;
- future or stale research Artifact;
- current chain before creation Opportunity evidence;
- incorrect envelope/source-manifest hash;
- price later than research within skew;
- price over skew, stale, future, wrong symbol or insufficient quality.

**Green implementation:**

- canonical-round-trip every input;
- verify exact input ID/hash pairs and common current research chain;
- prove Thesis creation evidence against actual Opportunity;
- select unique Candidate/theme/capital/price entries;
- implement per-component ages and separate price skew/age checks;
- derive price observation identity/hash without inventing SourceManifest hash.

Run:

```bash
python -m pytest -q tests/position/test_thesis_health_builder.py -k 'scope or lineage or fresh or price or creation'
```

### Task 4: Component derivation and invalidation priority

**Files:**
- Modify: `src/market_regime_alpha/position/thesis_health.py`
- Modify: `tests/position/test_thesis_health_builder.py`

**Red tests:**

- all support yields observed/effective `HEALTHY`;
- weak Signal, Theme and Capital yield `WEAKENING`;
- Market risk-off follows explicit mapping;
- explicit Market extreme-risk rule invalidates;
- Signal evaluation uses state, five confirmation states, score and confidence;
- Path uses status, calibration, sample, MFE/MAE and barrier gates without
  probability language;
- both Theme and Symbol Capital are required;
- price, time and manual rules trigger exact condition IDs;
- missing evidence yields `DATA_INSUFFICIENT`;
- time/price/manual invalidation wins over unrelated missing Signal/Capital;
- absent manual evidence is not triggered;
- malformed/future/conflicting manual evidence is data insufficient;
- output retains formal-OOS and manual-authentication limitations.

**Green implementation:**

- implement component support evaluators with explicit configuration only;
- overlay typed invalidation rules and collect exact reason codes;
- implement `INVALIDATED > DATA_INSUFFICIENT > WEAKENING > HEALTHY`;
- ensure Capital language and Path limitations remain honest.

Run:

```bash
python -m pytest -q tests/position/test_thesis_health_builder.py
```

### Task 5: Prior observation and effective-state machine

**Files:**
- Modify: `src/market_regime_alpha/position/thesis_health.py`
- Create: `tests/position/test_thesis_health_state_machine.py`

**Red tests:**

- first healthy;
- healthy to weakening;
- weakening observed healthy remains effectively weakening;
- weakening to invalidated;
- invalidated cannot recover;
- data insufficient preserves prior effective state;
- first data insufficient leaves effective state null;
- prior ID correct/hash wrong;
- prior from another Thesis, future prior and newer Thesis version;
- stale prior produces observed insufficient unless deterministic invalidation
  wins.

**Green implementation:**

- validate full prior identity/scope/time/version;
- bind prior ID/hash/observed/effective states into output;
- implement monotonic effective-state transition function;
- emit explicit recovery-not-authorized and stale-prior reasons.

Run:

```bash
python -m pytest -q tests/position/test_thesis_health_state_machine.py
```

### Task 6: Repository Protocol and migration 008

**Files:**
- Create: `src/market_regime_alpha/position/repositories.py`
- Create: `src/market_regime_alpha/position/sqlite_thesis_health.py`
- Create: `src/market_regime_alpha/position/migrations/008_thesis_health_up.sql`
- Create: `src/market_regime_alpha/position/migrations/008_thesis_health_down.sql`
- Modify: `pyproject.toml`
- Modify: `src/market_regime_alpha/position/__init__.py`
- Create: `tests/position/test_sqlite_thesis_health.py`

**Red tests:**

- repeat-safe migration and migration version 008;
- first save/get and restart;
- same command replay and semantic conflict;
- same observation ID with different content;
- prior root and successor uniqueness/no fork;
- isolated down migration;
- append-only UPDATE/DELETE on both tables.

**Green implementation:**

- define storage-neutral save/resolve/get/latest Protocol;
- add exact schema/check/index/foreign-key/trigger validation;
- implement `BEGIN IMMEDIATE` save and rollback;
- package Position migrations in distributions.

Run:

```bash
python -m pytest -q tests/position/test_sqlite_thesis_health.py -k 'migration or save or replay or restart or append or fork'
```

### Task 7: Strict restoration, Builder replay and tamper recovery

**Files:**
- Modify: `src/market_regime_alpha/position/sqlite_thesis_health.py`
- Modify: `tests/position/test_sqlite_thesis_health.py`

**Red tests:**

- tampered observation JSON;
- tampered input bundle, configuration, rule set or prior JSON;
- projection ID/hash/state/config/rule/prior tamper;
- Builder replay mismatch;
- weak table schema and spoofed append-only trigger;
- command-insert failure leaves neither observation nor command;
- prior row missing or different from bundled prior.

**Green implementation:**

- reconstruct every canonical object from bundle JSON;
- compare every projection and observation input reference;
- load and compare stored prior observation;
- rerun Builder and require byte-semantic equality;
- validate exact migration schema and trigger SQL;
- prove full transaction rollback.

Run:

```bash
python -m pytest -q tests/position/test_sqlite_thesis_health.py
```

### Task 8: Application Service and semantic idempotency

**Files:**
- Create: `src/market_regime_alpha/application/trading_lifecycle/thesis_health.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/__init__.py`
- Create: `tests/application/trading_lifecycle/test_thesis_health_service.py`

**Red tests:**

- valid build/persist and same-key replay;
- same key/different semantics conflict;
- missing or incomplete rule set rejected with
  `THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED`;
- expected prior ID/hash load and mismatch;
- new command without latest prior rejected as a fork;
- strict actual domain input types and canonical tamper;
- service does not mutate Thesis or invoke H4/execution repositories.

**Green implementation:**

- build exact private input bundle and command hash;
- resolve replay before current-tip enforcement;
- load expected prior from repository;
- call Builder and atomically save through Protocol;
- export stable H5 application API.

Run:

```bash
python -m pytest -q tests/application/trading_lifecycle/test_thesis_health_service.py
```

### Task 9: Strict H5 operational CLI

**Files:**
- Create: `scripts/build_thesis_health.py`
- Create: `tests/scripts/test_build_thesis_health.py`

**Red tests:**

- verified package paths produce and persist one V2 observation;
- same request replays the same ID;
- request rejects support booleans, triggered conditions and final health;
- component/prior/reason output is explicit;
- data-insufficient and invalidated output is honest;
- no Thesis, H4, ManualTrade, Fill or Broker side effect;
- output includes `OBSERVATION_ONLY`, `NO_TRADE_ACTION_CREATED` and
  `TRADING_AUTHORITY_NOT_GRANTED`.

**Green implementation:**

- use existing Research/Signal/Path package Readers;
- use strict canonical Readers for Thesis, Opportunity, price, config, rules
  and manual evidence;
- select exact symbol-scoped Signal and Path objects;
- invoke only `ThesisHealthApplicationService` and print canonical summary.

Run:

```bash
python -m pytest -q tests/scripts/test_build_thesis_health.py
```

### Task 10: Shared Holding/Exit internals and V2-only adapter

**Files:**
- Modify: `src/market_regime_alpha/position/assessment.py`
- Create: `src/market_regime_alpha/application/trading_lifecycle/operational_assessment_v2.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/__init__.py`
- Create: `tests/application/trading_lifecycle/test_operational_assessment_v2.py`
- Modify: `tests/position/test_assessments.py` only for shared-logic regression

**Red tests:**

- V2 healthy, weakening, invalidated and insufficient drive the same existing
  Holding/Exit action rules;
- effective state, not a caller-authored support reconstruction, is consumed;
- V2 service rejects V1 and cross-scope/tampered/future observations;
- result says assessment-only/no trade/no authority;
- service does not call H4 or any execution/broker dependency;
- existing V1 behavior remains unchanged;
- old Portfolio/Risk reason strings and `requires_portfolio_risk` remain.

**Green implementation:**

- introduce an internal resolved health context;
- route V1 evaluator and V2 validator into shared Holding/Exit internals;
- add `OperationalPositionAssessmentServiceV2` without persistence or a new
  LifecycleReview schema;
- never construct V1 support booleans.

Run:

```bash
python -m pytest -q tests/application/trading_lifecycle/test_operational_assessment_v2.py tests/position/test_assessments.py
```

### Task 11: V1 compatibility and H4 regression

**Files:**
- Modify/add compatibility tests only as required.

Run:

```bash
python -m pytest -q tests/evaluation/test_lifecycle_replay.py tests/position/test_assessments.py
python -m pytest -q \
  tests/portfolio/test_risk_route_domain.py \
  tests/portfolio/test_risk_route_separation.py \
  tests/portfolio/test_sqlite_risk_routes.py \
  tests/scripts/test_assess_risk_reduction.py
```

Expected: all V1 fixtures and all H4 focused tests PASS unchanged in authority.

### Task 12: Context and full quality gates

Run and record each as PASS, FAIL, NOT_RUN or BLOCKED:

```bash
python -m pytest -q tests/position
python -m pytest -q tests/application
python -m pytest -q tests/decision
python -m pytest -q tests/portfolio
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
python scripts/check_docs_links.py
git diff --check
```

Remove generated `dist/` after recording build evidence. Fix any H5-introduced
failure. Record but do not expand into unrelated Legacy refactors.

### Task 13: Authoritative documentation and delivery audit

**Files:**
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md`
- Create: `docs/audit/H5-Thesis-Health-Delivery.md`
- Update this plan with completed steps and exact evidence.

Document:

- exact implementation commit and gate counts;
- H5 domain, Artifact, time, state and persistence boundaries;
- private replay bundle non-authority;
- V1 compatibility;
- unchanged H4.5/H7 gaps;
- `FORMAL_PIT_NOT_ESTABLISHED`, `FORMAL_OOS_ALPHA_NOT_ESTABLISHED`,
  `SHADOW_READY_NOT_ESTABLISHED`, `TRADING_AUTHORITY_NOT_GRANTED` and
  `REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED`.

Run documentation checker and full gates after documentation changes.

### Task 14: Reviewable checkpoints, push and Draft PR

Before each checkpoint:

```bash
git diff --check
git status --short
git diff --stat
git diff
git diff --cached
```

Exclude `.idea/modules.xml`, generated artifacts, credentials and unrelated
files. Create one design checkpoint and one dependency-coherent H5 delivery
checkpoint, with a final documentation evidence checkpoint if the exact commit
binding requires it.

Push:

```bash
git push -u origin feat/h5-artifact-derived-thesis-health
```

Create a Draft PR titled:

```text
feat: derive thesis health from verified artifacts
```

If `gh` remains unauthenticated, retain the pushed branch and report:

```bash
gh auth login
gh auth status
```

Never print or persist a token.

## Genuine stop conditions

Stop only if implementation would require changing H4 authority, ManualTrade
or Fill schema, the full LifecycleReview schema, or another explicitly excluded
bounded context; if existing Artifact contracts cannot express the approved
lineage without inventing H6 authority; or if credentials/network state alone
prevents the requested push/PR after all local work and commits are complete.
