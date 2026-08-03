# H5 Artifact-Derived Thesis Health Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound H5 engineering delivery evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../superpowers/specs/2026-08-04-h5-artifact-derived-thesis-health-design.md, ../superpowers/plans/2026-08-04-h5-artifact-derived-thesis-health.md
> **Code Evidence:** implementation checkpoint `89c06908a66fc1744802d7511c992a407f4c5c93`; branch started from `main@df5c731da018819d9710f2d2f1ecffb4995fa082`

## 1. Delivery conclusion

H5 is implemented and locally verified as an engineering capability. New operational H5 commands cannot submit `signal_support`, `theme_support`, `capital_support`, triggered condition conclusions or a final health state. They submit exact typed Artifacts, explicit configuration/rules, assessment time and audit fields; the Builder alone derives the V2 Observation.

This result does not establish formal PIT, formal OOS Alpha, Shadow readiness, production readiness or trading authority.

## 2. Historical V1 boundary

Caller-authored support booleans remain only in the historical compatibility path:

- `position/assessment.py::ThesisHealthObservation` and `ThesisHealthEvaluator`;
- `application/trading_lifecycle/review.py::LifecycleReviewRun` and `LifecycleReviewApplicationService`;
- historical lifecycle review CLI/fixtures and compatibility tests.

The V1 Reader remains intact so historical Artifacts can be reconstructed. `ThesisHealthApplicationService`, `build_thesis_health.py` and `OperationalPositionAssessmentServiceV2` reject V1 input. The V2 adapter consumes the V2 effective state directly through a shared resolved-health context and never fabricates V1 booleans.

## 3. Executable invalidation rules

`ThesisInvalidationRuleSet` binds `thesis_id`, `thesis_version` and every Thesis `condition_id` exactly once. It rejects missing, extra, duplicate and kind-mismatched rules, unknown rule types and TIME thresholds that differ from `TradingThesis.time_invalidation`.

The supported typed rules are:

- `PRICE_BELOW` and `PRICE_ABOVE`;
- `MARKET_STATE_IN` and `TRADE_PERMISSION_IN`;
- `THEME_ROTATION_STATE_IN`;
- `CAPITAL_EVOLUTION_STATE_IN` with Theme, symbol or both scope;
- `SIGNAL_STATE_IN`;
- `TIME_AFTER`;
- `MANUAL_EVIDENCE_REQUIRED`.

Descriptions and condition names are not parsed. Absence of Manual evidence means the Manual condition is not triggered. Submitted Manual evidence is content-addressed and binds Thesis/version/condition/actor/reason/recorded/availability time; malformed, future, conflicting or cross-scope evidence fails closed. `MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED` remains explicit.

## 4. Artifact and time validation

The current research chain validates canonical identities, a compatible DecisionTime and one SourceManifest ID/hash lineage:

```text
Market + Theme + Capital
        ↓
CandidateSet
        ↓
SignalSnapshot
        ↓
PathForecast
```

The Builder additionally verifies Candidate symbol uniqueness and `primary_theme_id`, Theme membership, both Theme and symbol Capital entries, Signal/Path symbol scope, current-chain freshness and that current evidence does not precede Thesis creation evidence. Creation evidence references remain separately recorded from current health evidence.

`DecisionPriceSnapshot` may be later than the research chain. `maximum_price_age_seconds` and `maximum_price_research_skew_seconds` explicitly control its admissibility; event and availability times cannot be future. Missing price or primary Theme is represented as `DATA_INSUFFICIENT`, not invented authority.

## 5. V2 Observation and state machine

`ThesisHealthObservationV2` content-identifies the Thesis/opportunity/symbol/theme, assessed price, every source Artifact ID/hash, original Thesis supporting evidence, configuration/rule identity, Builder revision, component states, triggered/missing/reason codes, Manual evidence references and prior Observation identity/hash/states.

Observed priority is:

```text
deterministic invalidation
> evidence missing/stale/conflicted
> weakening
> healthy
```

Effective state is monotonic:

- first HEALTHY establishes HEALTHY;
- HEALTHY plus observed WEAKENING becomes WEAKENING;
- WEAKENING plus observed HEALTHY remains WEAKENING;
- observed INVALIDATED becomes terminal INVALIDATED;
- observed DATA_INSUFFICIENT preserves the prior effective state;
- first DATA_INSUFFICIENT leaves effective state not established.

Known time, price or valid Manual invalidation is not hidden by unrelated missing evidence.

## 6. Repository, transaction and replay

Migration 008 creates append-only `thesis_health_observations` and `thesis_health_commands`. `SQLiteThesisHealthRepository`:

- opens `BEGIN IMMEDIATE` and rolls back observation plus command on failure;
- implements idempotency key plus semantic command hash replay and conflict rejection;
- rejects branching from anything except the latest stored prior Observation;
- restores Observation, input bundle, configuration, rule set and prior Observation canonically;
- validates every projection column and prior identity/hash;
- reruns `ThesisHealthObservationBuilder` and requires byte-semantic equality;
- validates schema/check constraints and exact append-only trigger semantics;
- survives Repository restart and repeat-safe migration initialization.

The stored `ThesisHealthInputBundle` is an H5-private replay bundle. It is not a `CompositeOperationalInputManifest`, not H6 authority, not a replacement for source Artifacts and cannot promote DataEligibility or formal PIT status.

## 7. Operational boundary

`scripts/build_thesis_health.py` produces and persists one Observation. It outputs component states, source IDs/hashes and explicit boundaries:

```text
OBSERVATION_ONLY
NO_TRADE_ACTION_CREATED
TRADING_AUTHORITY_NOT_GRANTED
```

`OperationalPositionAssessmentServiceV2` produces only `HoldingAssessment` and `ExitAssessment`. It reuses the shared model decision core, does not call H4 and does not create a Thesis transition, ManualTrade, Fill, order or Broker interaction. Historical `ExitAssessment.requires_portfolio_risk` wording remains an H4.5/H7 gap.

## 8. Verification evidence

Local Python 3.12 verification at `89c06908a66fc1744802d7511c992a407f4c5c93`:

```text
FOCUSED_H5 = 74 passed, 0 skipped, 0 failed
H5_AND_POSITION_CONTEXT = 88 passed, 0 skipped, 0 failed
APPLICATION_CONTEXT = 55 passed, 0 skipped, 0 failed
DECISION_CONTEXT = 8 passed, 0 skipped, 0 failed
PORTFOLIO_CONTEXT = 55 passed, 0 skipped, 0 failed
H4_FOCUSED_REGRESSION = 42 passed, 0 skipped, 0 failed
FULL_PYTEST = 1371 passed, 0 skipped, 0 failed
RUFF = PASS
MYPY_FORMAL_SCOPE = PASS, 258 source files
PACKAGE_BUILD = PASS, sdist and wheel
DOCUMENT_AUTHORITY_AND_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

The full test run emitted six pre-existing pandas fragmentation performance warnings in `run_top1000_screened_portfolio_backtest.py`; no test failed or skipped.

## 9. Remaining work

- H6 owns cross-source Composite Operational Evidence.
- H4.5 owns fresh RiskReducingDecision-to-manual-intent confirmation.
- H7 owns durable Holding/Exit scheduling, H3 T+1 projection integration and acknowledgement/state persistence.
- H8 owns sustained Shadow operation and run evidence.
- H9 owns formal PIT/OOS validation.
- DailyLoop still constructs a local in-memory `ModelRegistry`.
- canonical Entry remains `REJECT`/`WAIT_CONFIRMATION`, never `ENTER`.
- Legacy Web, Paper Broker and QMT/PTrade placeholders are not canonical or real trading authority.

## 10. Authority conclusion

```text
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
SHADOW_READY_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
```
