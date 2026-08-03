# H4 Risk Route Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound H4 implementation and verification record
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-03
> **Supersedes:** H4 findings in Current-Main-Code-Audit-2026-08-01.md
> **Superseded By:** None
> **Related Documents:** Current-Main-Code-Audit-2026-08-01.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md
> **Code Evidence:** `3672067549e1b72a8bfd390f8320e2a7c55c599e`
> **Evidence Boundary:** Local Python 3.12 code, SQLite, tests and build were observed. No remote GitHub Actions result, sustained Shadow evidence, broker execution or formal Alpha result is claimed.

## 1. Baseline and reproduced failure

The repair branch is `fix/h4-risk-route-baseline`, created from `origin/main@c018a6a2cfa6c5a5edc7d2083750d336c6860acb`. That revision is the merge of documentation PR #29; the H4 business-code baseline remained `e183fdac285786ed448c835e65c99dc67189c2b9`.

The workspace contained an unrelated user edit in `.idea/modules.xml`. It was preserved and excluded from every H4 commit.

Observed failures, in discovery order:

1. `python -m pytest -q tests/portfolio/test_risk_route_separation.py` failed collection with `ImportError: cannot import name 'ExecutionConstraintState' from 'market_regime_alpha.portfolio'`.
2. After the public H4 domain exports were restored, collection advanced to `ImportError: cannot import name 'RiskRouteApplicationService' from 'market_regime_alpha.portfolio'`.
3. Static inspection confirmed that `portfolio/sqlite_risk_routes.py` was absent although the test imported it.
4. Once the missing application/repository path existed, the test fixture exposed `LookupError: no later trading session exists`; its explicit synthetic calendar ended before the required next session.
5. The migration-down test then exposed a test precondition error: it asserted that the migration-005 table survived without first installing migration 005. The test now installs the independent owner before applying migration 007 down.

The first three items were H4 implementation blockers. Items four and five were previously hidden test-fixture defects, not production-domain failures.

Diagnostic commands also found pre-existing scope differences:

- bare `pytest -q` produced 15 import/collection errors because the shell entry point did not receive the repository's `pythonpath`; formal CI uses `python -m pytest`;
- `mypy src` reported 44 Legacy/full-range errors in 9 files, while the repository's configured CI target passed. No H4 error remains outside the formal target.

## 2. Delivered H4 boundary

The delivered runtime boundary is:

```text
PositionSnapshot + ReducingExecutionObservation + explicit Gate configuration
→ RiskRouteApplicationService
→ RiskReducingExecutionGate
→ RiskReducingDecision
→ SQLiteRiskRouteRepository
→ verified canonical restoration
→ DECISION_ONLY CLI output
```

It includes:

- stable public H4 exports;
- a version-2 Gate configuration with explicit position and observation age limits;
- strict REDUCE/EXIT quantities and OPEN/ADD rejection;
- immutable, content-addressed decisions;
- SQLite migration initialization plus structural validation of columns, primary/unique constraints, foreign keys, CHECK semantics and append-only trigger SQL;
- atomic decision/evidence/command persistence;
- command idempotency and semantic-conflict rejection;
- append-only decision and command triggers;
- canonical reconstruction, cross-reference checking and Gate replay on read;
- numeric canonicalization before configuration/observation identity calculation and strict CLI command/audit-field types;
- a human-facing assessment CLI that persists a decision and reports evidence references.

It excludes:

- `ManualTradeRecord` or ManualTrade schema changes;
- Fill schema/ledger changes;
- Position mutation;
- Paper Broker, QMT or PTrade calls;
- order creation or automatic confirmation;
- any trading authority.

## 3. Increasing and reducing route separation

Increasing risk remains:

```text
OPEN / ADD
→ Candidate / Signal / Entry / Thesis
→ CompleteAccountPortfolioDecision
→ approved CompleteAccountRiskDecision
→ manual execution authority boundary
```

`RiskIncreasingDecision.create` still requires an approved, matching complete-account Risk decision. A rejected risk object cannot create the increasing-risk reference.

Reducing risk is independently assessed:

```text
REDUCE / EXIT
→ authoritative H3 PositionSnapshot
→ execution observation and freshness checks
→ RiskReducingDecision
→ PERMITTED_FOR_MANUAL_CONFIRMATION | BLOCKED | DATA_INSUFFICIENT
```

The reducing route does not invoke an Entry Model and cannot produce a Broker Order. Both the Application Service and the Gate reject OPEN/ADD immediately.

## 4. Quantity and freshness semantics

All quantities are strict integers; booleans and floats are rejected rather than coerced.

REDUCE requires:

```text
0 <= target_quantity < current_quantity
order_quantity = current_quantity - target_quantity
order_quantity > 0
order_quantity <= available_quantity
```

EXIT requires:

```text
target_quantity = 0
order_quantity = current_quantity
order_quantity <= available_quantity
```

An unsellable remainder is not disguised as a complete EXIT. A partial sale must be expressed as a distinct REDUCE command.

The Gate receives an explicit timezone-aware `assessed_at`. Configuration schema `risk-reducing-gate-configuration-v2` supplies both `maximum_position_age_seconds` and `maximum_observation_age_seconds`. Future or stale evidence cannot produce permission:

```text
position.as_of > assessed_at                         → DATA_INSUFFICIENT
assessed_at - position.as_of > maximum position age → DATA_INSUFFICIENT
observation.availability_time > assessed_at          → DATA_INSUFFICIENT
assessed_at - observation time > maximum obs age     → DATA_INSUFFICIENT
```

Symbol/session mismatch, UNKNOWN execution state and incomplete T+1 authority also fail closed.

## 5. Repository transaction, replay and restoration

`SQLiteRiskRouteRepository.save_reducing_decision` uses one `BEGIN IMMEDIATE` transaction:

1. validate the idempotency key and SHA-256 command hash;
2. resolve an existing command;
3. reject the same key with a different command hash;
4. insert or strictly compare the immutable decision/evidence bundle;
5. insert the command-to-decision mapping;
6. reload through the verified Reader path;
7. commit, or roll back every write on any exception.

The read path does not return stored JSON directly. It reconstructs Position, Observation, Configuration and Decision through their canonical readers, checks table projections and all foreign evidence identities/hashes, then reruns the Gate with the recorded decision time. Any mismatch fails the read.

Migration 007 is repeat-safe and its schema/triggers are validated at repository initialization. UPDATE and DELETE are prohibited for both decisions and command mappings.

## 6. Decision-only CLI

The command is:

```bash
python scripts/assess_risk_reduction.py \
  --database PATH_TO_SQLITE \
  --request PATH_TO_CANONICAL_REQUEST_JSON
```

It outputs the decision identity, state, reason codes, Position/Observation/Configuration references and the fixed boundary fields:

```text
DECISION_ONLY
NO_ORDER_CREATED
TRADING_AUTHORITY_NOT_GRANTED
```

Only a permitted state sets `manual_confirmation_required=true`. Repeating the same idempotency key and command returns the same decision ID.

## 7. Changed implementation and tests

Implementation/CI files:

- `.github/workflows/ci.yml`;
- `pyproject.toml`;
- `scripts/assess_risk_reduction.py`;
- `src/market_regime_alpha/application/trading_lifecycle/__init__.py`;
- `src/market_regime_alpha/portfolio/__init__.py`;
- `src/market_regime_alpha/portfolio/repositories.py`;
- `src/market_regime_alpha/portfolio/risk_routes.py`;
- `src/market_regime_alpha/portfolio/sqlite_risk_routes.py`;
- migration 007 up/down.

Test files:

- `tests/portfolio/test_risk_route_domain.py`;
- `tests/portfolio/test_risk_route_separation.py`;
- `tests/portfolio/test_sqlite_risk_routes.py`;
- `tests/portfolio/risk_route_test_support.py`;
- `tests/portfolio/test_complete_account_risk.py`;
- `tests/scripts/test_assess_risk_reduction.py`.

Tests cover successful REDUCE/EXIT, replay/restart, semantic conflicts, decision identity conflicts, tampered decision/configuration/hash data, injected transaction failure, migration repetition/down isolation, append-only triggers, all named A-share constraints, freshness/scope mismatch, OPEN/ADD rejection, complete-account increasing-risk authority and no CLI Broker/ManualTrade/Fill side effects.

## 8. Verification evidence

Observed on the implementation checkpoint:

| Command/scope | Result |
|---|---|
| Focused `test_risk_route_separation.py` | PASS — 22 passed, 0 skipped, 0 failed |
| Portfolio/Position/Execution plus H4 CLI | PASS — 92 passed, 0 skipped, 0 failed |
| Full `python -m pytest -q` with JUnit result capture | PASS — 1305 passed, 0 skipped, 0 failed |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 256 source files |
| `python -m build` | PASS — sdist and wheel |
| `python scripts/check_docs_links.py` | PASS |
| `git diff --check` | PASS |

The first isolated build attempt was blocked by sandbox DNS while fetching `setuptools>=68`; rerunning the same build with approved network access succeeded. This was an environment restriction, not a package failure.

CI now covers Python 3.12, editable dev dependency installation, documentation validation, pytest, Ruff, configured mypy and package build on push/pull request. The repository has no `uv.lock` or other dependency lock; `requirements.txt` matches the runtime dependencies in `pyproject.toml`, but both rely on lower bounds. Locking remains a separate reproducibility gap.

## 9. Read-only associated findings

- `DailyLoopRunner` creates a fresh in-memory `ModelRegistry()` for B0/B1 definitions. Persistent Model/Experiment repositories exist, but the runtime does not use them; process restart therefore does not restore runtime governance state through that call chain. Prediction artifacts bind immutable model-definition identity, but not a durable governed registration transition.
- Canonical `daily_decision.EntryAssessmentState` has only `REJECT` and `WAIT_CONFIRMATION`. The older `daily_research.EntryState` still contains `ENTER`, so namespace/Reader isolation needs an explicit compatibility work package.
- `web/dividend_t_app.py` is Legacy and directly evaluates Legacy strategy/risk inputs; it is not backed by canonical Artifact Readers.
- `PaperBrokerAdapter.place_order` returns an accepted placeholder result but does not update canonical cash, Fill or Position authority.
- QMT/PTrade adapters raise `BrokerUnavailable` for account/order operations.
- Legacy APScheduler has no durable receipts, retry/recovery journal or ShadowRun ownership.

None of these findings was modified by H4.

## 10. H4.5 and next sequence

H4.5 is design-only in this delivery. It will connect a still-fresh permitted decision to a separately authorized ManualTrade command, recheck current Position/T+1 sellability, record the human confirmer/time/reason and preserve partial fill/cancel/redecision history. It requires explicit schema migrations and must complete before or within H7. H4 itself does not depend on H4.5.

The remaining dependency order is:

```text
H5 Artifact-derived Thesis Health
→ H6 Composite Operational Evidence
→ H4.5 Manual Execution Bridge
→ H7 Durable Holding / Exit Decisions
→ H8 Shadow Operations
→ H9 Formal Validation
```

The detailed state, artifact, idempotency, transaction, recovery and acceptance contracts are maintained in the WP-PDL-HARDENING work package.

## 11. Admission conclusion

```text
H4_REDUCING_RISK_ROUTE_IMPLEMENTED_AND_VERIFIED = TRUE
FORMAL_PIT_OOS_ALPHA_ESTABLISHED = FALSE
SHADOW_OPERATIONS_ESTABLISHED = FALSE
SHADOW_READY = FALSE
PRODUCTION_READY = FALSE
ENTRY_TRADING_AUTHORITY_GRANTED = FALSE
REAL_BROKER_AUTHORITY_IMPLEMENTED = FALSE
TRADING_AUTHORITY_GRANTED = FALSE
```
