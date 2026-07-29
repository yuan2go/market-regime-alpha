# WP-D3.1 Real Decision Evidence Implementation Plan

> **Status:** ROADMAP
> **Authority:** Approved execution plan for WP-D3.1 real decision evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../audit/WP-D3-1-Real-Decision-Evidence-Baseline.md, ../specs/2026-07-30-wp-d3-1-real-decision-evidence-design.md
> **Code Evidence:** `main@2ecf4aad5096fa8e978f2b4e73b7630a87415a32`; implementation evidence is added after delivery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Add auditable current-session security-status evidence and independently recoverable history/status/quote acquisition so a real fixed-20-stock archive can reach `OUTCOME_PENDING` only when all decision-time facts are genuinely available before 14:55 Asia/Shanghai.

**Architecture:** Preserve `RunRequestId` as the SQLite journal key and derive `DailyRunId` only after the three immutable source stages have been frozen. Extend the public-composite provider boundary with typed security-status observations, publish them through a scope-bound V3 stage artifact, project them into SourceManifest V2 facts without changing historical readers, and expose four idempotent application commands: prepare history, freeze status, freeze quote, and finalize. Current-session facts remain provider evidence; prior-session BaoStock status is retained only as explicitly scoped history evidence.

**Tech Stack:** Python 3.12, frozen dataclasses, `Protocol`, JSON content-addressed artifacts, SQLite runtime journal, pytest, mypy, Ruff.

## Global Constraints

- Keep `data_eligibility=EXPLORATORY`, `formal_pit=NOT_ESTABLISHED`, `formal_oos_alpha=NOT_ESTABLISHED`, and `trading_authority=NOT_GRANTED`.
- Do not modify historical `daily_research` V1 contracts, schemas, identifiers, readers, ENTER behavior, or tests.
- Do not alter Feature formulas, B0/B1 definitions, ranks, tie breaks, weights, Targets, or Entry state vocabulary.
- Never infer current status from symbol syntax, a static list, or prior-session evidence.
- LIVE has no local-archive fallback; REPLAY performs no network access.
- A status or quote observed after `DailyRunCommand.decision_time` is unusable for that symbol.
- Preserve all 20 configured symbols in reconciliation with explicit exclusion reasons.

## Task 1: Add typed security-status evidence contracts

**Files:**

- Modify: `src/market_regime_alpha/data/providers/public_composite/contracts.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/live_clients.py`
- Test: `tests/data/providers/public_composite/test_live_clients.py`
- Test: `tests/data/test_public_composite_provider.py`

**Steps:**

1. Add failing tests proving:
   - `TRADING_STATUS`, `ST_STATUS`, and `LISTING_STATUS` are distinct facts.
   - each observation carries event, availability, retrieval, decision, and policy-effective time independently;
   - prior-session observations cannot validate current-session status;
   - unknown values remain unknown and include reason codes.
2. Introduce frozen contracts:

   ```python
   class SecurityStatusFactType(str, Enum):
       TRADING_STATUS = "TRADING_STATUS"
       ST_STATUS = "ST_STATUS"
       LISTING_STATUS = "LISTING_STATUS"

   class SecurityStatusEvidenceScope(str, Enum):
       PRIOR_SESSION_STATUS = "PRIOR_SESSION_STATUS"
       CURRENT_DECISION_SESSION = "CURRENT_DECISION_SESSION"

   @dataclass(frozen=True)
   class PublicSecurityStatusObservation:
       symbol: CanonicalInstrumentId
       fact_type: SecurityStatusFactType
       value: str
       scope: SecurityStatusEvidenceScope
       event_time: datetime | None
       available_time: datetime | None
       retrieved_time: datetime
       decision_time: DecisionTime
       policy_effective_time: datetime | None
       provider_id: ProviderId
       source_artifact_id: SourceArtifactId
       authority_kind: SourceAuthorityKind
       quality_status: SourceFieldQualityStatus
       reason_codes: tuple[str, ...]
       finality: DataFinality
       data_eligibility: DataEligibility
   ```

3. Extend `PublicCompositeBatch` with an immutable observation tuple, defaulting to empty for source/archive compatibility.
4. Parse BaoStock history columns `tradestatus` and `isST` into `PRIOR_SESSION_STATUS` observations only. Keep `available_time=None`, preserve `UNKNOWN` finality, and never project them as current status.
5. Run:

   ```bash
   python -m pytest -q tests/data/providers/public_composite/test_live_clients.py tests/data/test_public_composite_provider.py
   python -m ruff check src/market_regime_alpha/data/providers/public_composite tests/data
   python -m mypy
   git diff --check
   ```

6. Commit:

   ```text
   feat: add security status acquisition contracts
   ```

## Task 2: Add the BaoStock current-session status provider

**Files:**

- Modify: `src/market_regime_alpha/data/providers/public_composite/live_clients.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/profiles.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/__init__.py`
- Test: `tests/data/providers/public_composite/test_live_clients.py`
- Test: `tests/data/providers/public_composite/test_profiles.py`

**Steps:**

1. Add failing provider tests for:
   - exact decision-date `tradestatus` and `isST`;
   - `query_stock_basic.status`;
   - raw response preservation;
   - incomplete/unparseable rows remaining unknown;
   - per-symbol timeout/error isolation;
   - a retrieval later than decision time producing unusable status evidence;
   - a prior-session row never being relabeled current.
2. Implement `BaoStockSecurityStatusClient`:
   - log in once per batch;
   - query exact decision date for `date,code,tradestatus,isST`;
   - query stock basic for listing status;
   - preserve canonical raw bytes and raw hash per symbol;
   - use a bounded network timeout;
   - map only documented values and leave everything else unknown;
   - use actual retrieval time as current observation availability, explicitly limited to exploratory evidence;
   - return provider-level limitations if all symbols are unusable.
3. Extend `PublicCompositeLiveProfile` with `acquire_security_status(...)` and require the status client for LIVE composition.
4. Keep `PublicCompositeReplayProfile` archive-only.
5. Run the focused provider tests, Ruff, mypy, and `git diff --check`.
6. Commit:

   ```text
   feat: bind security status provider evidence
   ```

## Task 3: Publish scope-bound V3 stage artifacts

**Files:**

- Modify: `src/market_regime_alpha/data/providers/public_composite/stage_artifact.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/contracts.py`
- Test: `tests/data/test_public_source_stage_artifact.py`

**Steps:**

1. Add failing tests for:
   - V3 exact file set and checksum verification;
   - typed security observations round-trip;
   - stage scope binding to run request, decision date/time, provider profile, universe policy, and acquisition stage;
   - raw-payload hash binding;
   - cross-run and cross-stage artifact rejection;
   - orphan V3 discovery by exact scope;
   - unchanged V1/V2 reader routing;
   - tamper rejection.
2. Add:

   ```python
   @dataclass(frozen=True)
   class PublicSourceStageScope:
       run_request_id: str
       decision_date: date
       decision_time: DecisionTime
       provider_profile_id: str
       universe_policy_id: str
       acquisition_stage: PublicSourceAcquisitionStage
   ```

3. Add `PublicSourceAcquisitionStage.SECURITY_STATUS_SOURCE_FROZEN`.
4. Publish V3 packages with:
   - a manifest containing schema/version, stage identity, scope, batch hash, and all raw hashes;
   - a batch document containing normalized status observations;
   - raw payload bytes;
   - checksums and atomic non-overwrite publication.
5. Preserve V1/V2 readers byte-for-byte except version dispatch required to add V3.
6. Run focused tests, Ruff, mypy, and `git diff --check`.
7. Commit:

   ```text
   feat: add security status stage artifact
   ```

## Task 4: Split runner acquisition into independently resumable commands

**Files:**

- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Modify: `src/market_regime_alpha/application/daily_loop/repositories.py`
- Modify: `src/market_regime_alpha/application/daily_loop/sqlite_repository.py`
- Modify: `src/market_regime_alpha/application/daily_loop/state.py`
- Test: `tests/application/daily_loop/test_runner.py`
- Test: `tests/application/daily_loop/test_recovery.py`

**Steps:**

1. Add failing tests checking provider call counts for:
   - orphan artifact after history publish;
   - orphan artifact after status publish;
   - orphan artifact after quote publish;
   - status failure retaining history;
   - quote failure retaining history and status;
   - all stages frozen before source-archive publication failure;
   - source archive published before receipt failure;
   - repeated commands issuing no additional network calls.
2. Add runner application methods:

   ```python
   def prepare_history(self, command: DailyRunCommand) -> AcquisitionStageReceipt: ...
   def freeze_security_status(self, command: DailyRunCommand) -> AcquisitionStageReceipt: ...
   def freeze_decision_quote(self, command: DailyRunCommand) -> AcquisitionStageReceipt: ...
   def finalize_run(self, command: DailyRunCommand) -> DailyRunRecord: ...
   ```

3. Require exact `PublicSourceStageScope` verification whenever loading a receipt or claiming an orphan artifact.
4. Make `finalize_run` network-free and fail closed unless the three verified stage receipts exist.
5. Keep `run` as an idempotent convenience composition over those four methods.
6. Continue using `RunRequestId` as the SQLite primary key; bind, but never replace it with, the source-derived `DailyRunId`.
7. Keep source archive/DailyRun identity recovery stable across crashes.
8. Run focused application tests, Ruff, mypy, and `git diff --check`.
9. Commit:

   ```text
   refactor: split daily acquisition commands
   ```

## Task 5: Project current status into the manifest and enforce time semantics

**Files:**

- Modify: `src/market_regime_alpha/data/providers/public_composite/manifest_builder.py`
- Modify: `src/market_regime_alpha/data/source_manifest.py`
- Modify: `src/market_regime_alpha/data/daily_quality.py`
- Modify: `src/market_regime_alpha/universe/daily_exploratory.py`
- Modify: `src/market_regime_alpha/features/daily_pipeline.py`
- Test: `tests/data/test_source_manifest_and_quality.py`
- Test: `tests/universe/test_daily_exploratory.py`
- Test: `tests/features/test_daily_pipeline.py`

**Steps:**

1. Add failing tests proving:
   - Decision Time is protocol authority only;
   - membership is universe-policy authority only;
   - eligibility is eligibility-policy authority only;
   - current trading/ST/listing status is declared provider authority only;
   - prior status does not satisfy current status;
   - status availability after decision excludes only that symbol;
   - quote event, availability, or retrieval after decision excludes only that symbol;
   - unknown remains an explicit per-symbol exclusion;
   - provider-wide failure and invalid policy/stage identity globally block;
   - a remaining population below five blocks with `CANDIDATE_POPULATION_INSUFFICIENT`.
2. Add manifest projection for current status observations and optional, noncritical prior-session evidence.
3. Keep Tencent `trading_status=UNKNOWN`; do not let the quote client claim status authority.
4. Update decision-price materialization to use verified manifest status rather than Tencent’s placeholder field.
5. Enforce:

   ```text
   quote.event_time <= decision_time
   quote.available_time <= decision_time
   quote.source.retrieved_at <= decision_time
   status.available_time <= decision_time
   status.retrieved_time <= decision_time
   ```

6. Preserve global/per-symbol gate separation and all-symbol reconciliation.
7. Run focused data/universe/feature tests, Ruff, mypy, and `git diff --check`.
8. Commit:

   ```text
   fix: enforce decision-window status and quote availability
   ```

## Task 6: Add staged CLI scheduling

**Files:**

- Modify: `scripts/run_exploratory_daily_loop.py`
- Test: `tests/scripts/test_run_exploratory_daily_loop.py`

**Steps:**

1. Add failing CLI tests for:
   - `prepare-history`;
   - `freeze-security-status`;
   - `freeze-decision-quote`;
   - `finalize-run`;
   - retained `run`, `replay`, `settle`, and `report`;
   - shared deterministic command identity across independent invocations;
   - `finalize-run` constructing no live clients and doing no network access.
2. Wire the new commands to the runner methods with the same command inputs and output root/runtime journal.
3. Print the RunRequestId, stage, and stage Artifact ID for acquisition commands; print DailyRunId and decision Artifact ID only after finalization.
4. Keep old CLI behavior compatible for `run`.
5. Run focused script tests, Ruff, mypy, and `git diff --check`.
6. Commit:

   ```text
   feat: schedule staged public decision acquisition
   ```

## Task 7: Prove model equivalence, replay determinism, and compatibility

**Files:**

- Modify: `tests/application/daily_loop/test_runner.py`
- Modify: `tests/application/daily_loop/test_recovery.py`
- Modify: `tests/platform/test_candidate_prediction_adapter.py`
- Modify: `tests/data/test_public_source_stage_artifact.py`
- Modify: `tests/data/test_public_composite_provider.py`
- Modify: `tests/daily_decision/test_artifact.py`

**Steps:**

1. Add a complete characterization test comparing the pre-existing fixture path with the new staged path for:
   - every Feature value and materialization ID;
   - candidate population and dataset ID;
   - every B0/B1 prediction and rejection;
   - score, rank, percentile, tie break, ranking coverage, and Top-5;
   - Recommendation and EntryAssessment semantics.
2. Add replay tests proving:
   - zero network calls;
   - same source manifest and DailyRun identity;
   - same candidate population, features, B0/B1 ranks, and recommendations;
   - stable replay hash over repeated replays.
3. Add V1/V2/V3 artifact compatibility and tamper tests.
4. Add a DATA_BLOCKED fixture proving empty Prediction/Recommendation/Entry outputs.
5. Run:

   ```bash
   python -m pytest -q tests/application/daily_loop tests/data tests/universe tests/features tests/platform tests/daily_decision tests/scripts
   python -m ruff check src tests scripts
   python -m mypy
   git diff --check
   ```

6. Commit:

   ```text
   test: prove three-stage recovery and replay equivalence
   ```

## Task 8: Verify runtime evidence, update status, and publish the branch

**Files:**

- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Add: `docs/audit/WP-D3-1-Real-Decision-Evidence-Delivery.md`
- Modify: `docs/README.md`

**Steps:**

1. Run the full quality gate:

   ```bash
   python scripts/check_docs_links.py
   python -m pytest -q
   python -m mypy
   python -m ruff check src tests scripts
   python -m pip check
   git diff --check
   ```

2. Inspect current Asia/Shanghai time:
   - if outside a valid trading-day decision window, run only legitimate stages and record `REAL_1455_RUNTIME_VALIDATION_PENDING`;
   - never synthesize or backdate a current quote;
   - if within the window, run all four commands and capture all artifact identities.
3. Perform an archive-backed replay only from genuinely acquired source evidence and verify no network access and stable hash. If evidence remains incomplete, record the exact blocked status rather than claiming `OUTCOME_PENDING`.
4. Reconstruct and verify the decision artifact and report when one was legitimately published.
5. Update current-state documents with observed engineering and runtime facts only.
6. Commit:

   ```text
   docs: record verified wp-d3-1 delivery state
   ```

7. Confirm:

   ```bash
   git status --short
   git diff --check
   git log --oneline --decorate -10
   ```

8. Push without merging:

   ```bash
   git push -u origin feat/wp-d3-1-real-decision-evidence
   ```

## Acceptance State

Engineering acceptance may be reported as `WP_D3_1_ENGINEERING_COMPLETE` only after all three immutable stages, recovery paths, CLI commands, compatibility routes, and quality gates pass.

Runtime acceptance may be reported as `WP_D3_1_REAL_DECISION_EVIDENCE_CLOSED` only when a real fixed-20-stock run uses no fixture status, freezes current status and quote by 14:55, retains at least five candidates, reaches `OUTCOME_PENDING`, and produces an identical fully offline archive replay. Otherwise report the precise observed state, including `REAL_1455_RUNTIME_VALIDATION_PENDING`, `SECURITY_STATUS_SOURCE_NOT_QUALIFIED`, `PUBLIC_LIVE_STILL_DATA_BLOCKED`, or `REAL_ARCHIVE_REPLAY_STILL_DATA_BLOCKED`.
