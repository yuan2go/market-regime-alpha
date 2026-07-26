# Daily Quant Selection Current-State Audit

> **Audit date:** 2026-07-23
> **Audited revision:** `96e41a12d86b3b5f7472c2d4e44011736b087b6b`
> **Work package:** `WP-DQS-0`
> **Scope:** code, tests, scripts, tracked research artifacts, data layout, and current authority documents
> **Authority:** engineering audit; no Alpha, model-promotion, or trading authority

## 1. Executive finding

The repository has a strong Candidate-research spine and strong immutable research-evidence
machinery. It does not yet have a canonical daily decision spine. Daily user-facing selection,
timing, holdings, review, scheduling, and dashboards remain either absent or confined to the
Legacy Dividend-T bounded context.

The safe migration is therefore:

```text
existing PIT Universe / Eligibility / Feature / Candidate outputs
        ↓
new immutable Daily Quant Decision Artifact boundary
        ↓
future stock / ETF / theme / Entry / lifecycle / review applications
```

It is not safe to promote `DividendTStrategy`, `CoscoTimingEngine`, mutable Parquet snapshots, or
the Legacy FastAPI payloads into canonical daily-research authority.

## 2. Capability inventory

| Capability | Status | Evidence | Consequence |
|---|---|---|---|
| Stock Universe | `PARTIAL` | `universe/artifacts.py`, `eligibility_artifacts.py`, `eligibility_policy.py`, `candidates/historical_population.py` implement historical PIT membership and exact-time Eligibility. `dividend_t/universe.py` builds a current-snapshot large-cap list and explicitly records survivorship bias. | Reuse the PIT contracts; a daily multi-source stock-Universe producer and versioned inclusion/exclusion report still need a separate work package. |
| ETF Universe | `NOT_IMPLEMENTED` | The root backtest supports one sample ETF. Xuntou P0 accepts only `A_SHARE_STOCK` and rejects ETF input. No ETF Universe contract, deduplication, tracking-index identity, or primary/alternative selection exists. | Build an ETF-specific Universe; never mix ETF and stock ranks. |
| Industry Mapping | `LEGACY_ONLY` | Watchlist/Tushare rows carry current `industry` strings; `formal_dataset_builder.py` consumes an `industry_id` and `industry_as_of` supplied by a caller. No effective-dated mapping Artifact or semantic Reader exists. | Current industry strings must not be backfilled across history. |
| Theme Mapping | `NOT_IMPLEMENTED` | `theme_state` appears only as an input column in Legacy dataset assembly and in research documents. No membership mapping, version, availability time, or materializer exists. | Theme-aware ranking remains blocked on a separately identified mapping input. |
| Market Context | `LEGACY_ONLY` | `dividend_t/market_environment.py` computes trend, breadth, amount, limit structure and industry diffusion, but `MarketEnvironmentPoint` also owns model self-state, position cap, and `allow_new_buy`. MR-2A/MR-2B context code is experiment-specific. | Extract observations later; do not reuse the bundled Legacy state as canonical Market Context. |
| ETF Strength | `NOT_IMPLEMENTED` | No ETF feature pipeline, relative-strength rank, defensive state, or daily snapshot exists. | WP-DQS-3 remains unstarted. |
| Theme Strength | `NOT_IMPLEMENTED` | No breadth, leader resonance, persistence, decay, or theme-state materializer exists. | WP-DQS-3 remains unstarted. |
| Capital Flow | `LEGACY_ONLY` | `cosco_timing_capital_flow.py` derives signed money-flow and amount-expansion proxies from bars. `signal_audit.py` also reports a `capital_flow` column when supplied. | Any reuse must be registered as `CAPITAL_FLOW_PROXY`, not institutional-flow fact. |
| Candidate Ranking | `IMPLEMENTED` | `candidates/baselines.py` and `composite_baseline.py` implement B0/B1 with complete Population accounting, strict complete-case rejection, explicit direction/weights, target blindness, and evaluation. PIT success V2 reconstructs frozen B1-E scores. | Reuse rankings as inputs; do not alter frozen B1-E semantics. |
| Entry Target | `IMPLEMENTED` | `strategies/entry/contracts.py` and `materialization.py` implement versioned path targets with `UP_FIRST`, `DOWN_FIRST`, `TIMEOUT`, `AMBIGUOUS`, Calendar resolution, availability, finality, and missing-evidence states. | Reuse as Target evidence; it is not an Entry decision. |
| Entry Gate / Assessment | `NOT_IMPLEMENTED` | No canonical `ENTER`, `WAIT_PULLBACK`, `WAIT_CONFIRMATION`, `REJECT` object exists. Legacy buy timing is embedded in integrated strategy engines. | WP-DQS-1 may define the immutable output contract, but model logic belongs to a later package. |
| Position State | `LEGACY_ONLY` | `dividend_t.models.PositionState` is a strategy-specific percentage/cash/T-position input and lacks thesis, recommendation, MFE/MAE lineage, and immutable manual-trade history. | Do not promote or rename it as canonical lifecycle state. |
| Exit Target | `CONTRACT_ONLY` | The continuation labels are specified in `Entry-Position-Lifecycle-Exit-Research-Program.md`; there is no code Target or materializer. | Implement independently of Entry in a later work package. |
| Daily Recommendation | `LEGACY_ONLY` | `trend_snapshot.py`, `CoscoTimingSnapshot`, scripts, and the Legacy Dashboard emit daily/timing output. They do not publish the requested exact, content-addressed daily decision set or provide a semantic Reader. | Introduce a new daily artifact boundary without modifying Legacy output. |
| Manual Trade Record | `NOT_IMPLEMENTED` | `data/local/portfolio/positions.json` is local state; `PaperBrokerAdapter` creates paper orders. Neither is an immutable `ManualTradeRecord` linked to a recommendation. | Future manual execution must be append-only and must not mutate model evidence. |
| Daily Review | `LEGACY_ONLY` | `signal_audit.py` labels counterfactual outcomes and reports calibration/slices for Dividend-T. It is not tied to a frozen canonical recommendation Artifact. | Future review must read the original verified recommendation version. |
| Failure Attribution | `LEGACY_ONLY` | Legacy audit reports setup, signal, market, industry, volatility and execution slices, but no canonical multi-label failure taxonomy exists. | Define after outcomes and manual records have identities. |
| Dashboard | `LEGACY_ONLY` | `web/dividend_t_app.py` and `web/tushare_app.py` are operational, but their payloads are Legacy/manual and not backed by the new decision Reader. | A future Dashboard must consume verified artifacts rather than recompute decisions. |
| Task Scheduling | `LEGACY_ONLY` | `dividend_t/scheduler.py` and scripts schedule Legacy cache/report jobs. Jobs use replace-existing scheduler semantics and do not define a daily Artifact workflow. | Keep operationally isolated until the application Runner exists. |
| Data Persistence | `PARTIAL` | Research packages use staged, exact-file-set, checksummed, non-overwriting Artifacts and semantic Readers. `ResearchStore.write_parquet()` overwrites a stable filename and DuckDB/local caches are operational state. | Reuse the immutable research pattern, not the mutable Legacy store, for decisions. |
| Formal Xuntou daily input | `BLOCKED_EXTERNAL_DATA` | Qualified V4 contracts and success path exist, but the actual run remains blocker `pit-replication-v2-4985eec50a6c63ecf536`; no Validation partition was created. | Auxiliary daily engineering may continue only under exploratory/auxiliary authority. |

## 3. Real call chains

### 3.1 Canonical Candidate research chain

```text
Provider export / normalized provider evidence
        ↓
TradingCalendarArtifact
        +
HistoricalPITUniverseArtifact
        +
RawTradingEligibilityObservation
        ↓
HistoricalTradingEligibilityArtifact
        ↓
CandidatePopulation
        ↓
FeatureMaterialization
        +
TargetMaterialization
        ↓
CandidateResearchDataset / CandidateResearchPanel
        ↓
B0 or Transparent B1 CandidateRankingRun
        ↓
Candidate evaluation / directional diagnostics
        ↓
immutable research Artifact
        ↓
semantic Reader
```

This chain is implemented and is the upstream source for future daily recommendations. It does not
currently create a daily decision snapshot, Candidate Recommendation, or Entry Assessment.

### 3.2 Formal PIT replication chain

```text
Qualified Xuntou V4 evidence
        ↓
Validation partition seal and first-open receipt
        ↓
Universe ∩ Eligibility ∩ ResearchOrderability
        ↓
Feature evidence → frozen B1-E reconstruction
        ↓
matched-K / exact 10:30 evaluation / statistics
        ↓
success Artifact and semantic Reader
```

The success implementation exists, but the real provider route stops at a verified external-input
blocker. Test-only success fixtures cannot be daily research evidence.

### 3.3 Legacy daily/timing chain

```text
public-source / local bars with fallback
        ↓
Dividend-T fundamental + retreat + technical inputs
        ↓
integrated score and setup selection
        ↓
risk / MACD policy / position sizing
        ↓
StrategyDecision + optional OrderIntent
        ↓
Dashboard / report / scheduler / mutable cache
```

This path is useful for behavior characterization and component extraction. It mixes responsibilities
that the Constitution assigns to separate owners and therefore remains Legacy-only.

## 4. Schema-only and disconnected capabilities

- Exit continuation is research-document-only.
- Daily snapshot, recommendation, manual trade, outcome, review, and failure-attribution names exist
  in the Daily research program but not in code.
- Entry path Targets are implemented but are not connected to an Entry decision policy.
- MR-2A/MR-2B Market Context is bound to specific diagnostics and is not a production daily context.
- The FastAPI applications do not read an immutable daily-decision Artifact.
- APScheduler jobs do not own a deterministic daily-decision run identity.
- Local `positions.json`, paper orders, and Legacy `PositionState` do not constitute manual-trade or
  lifecycle evidence.

## 5. Reusable assets

1. `core.identity` and `core.time` for typed identity and timezone-aware semantic time.
2. PIT Universe, Eligibility, and Candidate Population contracts with fail-closed missingness.
3. Feature Definition/Materialization lineage and B0/B1 transparent rankings.
4. Entry path Target and future-evidence contracts, kept separate from Entry policy.
5. Staged directory publication, exact file sets, SHA-256 manifests, and non-overwrite behavior from
   current research artifacts.
6. Semantic Reader practice from F2B/PIT artifacts: recompute identity and derived outputs rather than
   accepting checksum-valid claims.
7. Legacy indicators only after they are extracted behind Feature definitions with explicit source
   family, availability, parameters, and missing policy.

## 6. Duplication and retirement boundaries

### Duplicate logic to consolidate later

- Multiple research modules independently implement canonical JSON, file hashing, staged rename,
  checksum validation, and path-safe run IDs.
- Legacy and new research paths both calculate momentum, volatility, liquidity, moving averages,
  MFE/MAE, and outcome labels under different identities.
- Provider normalization exists both in research adapters and operational `data_sources` fallbacks.
- Legacy `signal_audit` and Candidate evaluation both calculate forward performance, but with different
  populations and ownership.

WP-DQS-1 must not start a broad shared-framework rewrite. It should use a small, isolated Artifact
implementation whose semantics can later justify an extraction.

### Assets that must remain frozen or Legacy-only

- frozen B1-E and MR-2B/F2B results;
- `DividendTStrategy`, `CoscoTimingEngine`, Legacy `PositionState`, `OrderIntent`, and integrated
  `StrategyDecision`;
- current-snapshot large-cap Universe as formal historical membership;
- mutable `ResearchStore` outputs as immutable recommendation evidence;
- ETF sample backtest as ETF Rotation evidence;
- test fixtures as research data.

## 7. Architecture risks

### Responsibility collapse

Legacy `StrategyDecision` combines Candidate-like score, Entry/Exit-like action, position sizing,
risk warnings, and optional order intent. Reuse would violate Candidate/Entry/Lifecycle/Execution
ownership. The new daily Artifact must store Candidate Recommendation and Entry Assessment as
different records and files.

### Context and risk contamination

Legacy Market Environment includes model-performance state, `allow_new_buy`, and a maximum position
cap. Legacy risk and MACD policy can change the final action and size after score calculation. New
Market Observation, Model Performance State, Strategy Gate, and Risk Limit must remain independent;
Candidate score must be preserved before downstream gating.

### Point-in-Time and survivorship risk

- `dividend_t/universe.py` correctly warns that its large-cap list is a current snapshot.
- Legacy industry strings are selected from current/latest rows and are not effective-dated.
- Xuntou v3 current membership and buyability cannot become historical PIT evidence.
- Auxiliary Tencent/BaoStock/local histories are exploratory and do not establish historical
  membership, availability, revision, or orderability.

### Reconstruction risk

Legacy daily JSON, Dashboard responses, and mutable Parquet names are not semantic evidence. A
checksum alone would also be insufficient: IDs, references, ranks, report content, and temporal
constraints must be reconstructed by a Reader.

### Dynamic-configuration risk

Legacy dynamic weights, industry defaults, and in-source thresholds are result-affecting but do not
share one immutable daily configuration identity. WP-DQS-1 therefore stores only configuration
identity and model output evidence; it does not import these defaults.

### Fixture-authority risk

The PIT path already rejects `TEST_ONLY_NOT_RESEARCH_EVIDENCE` in formal execution. The same
classification must remain explicit in daily Artifact tests, and formal authority is outside the
WP-DQS-1 schema.

## 8. Recommended migration

1. Create a `daily_research` bounded context for daily-decision domain contracts, publication, and
   semantic reading.
2. Make the snapshot the root aggregate. Recommendations reference exactly one snapshot; Entry
   Assessments reference exactly one recommendation and cannot alter Candidate fields.
3. Bind every source reference to an exact content hash and a decision-time availability assertion.
4. Publish one exact, immutable file set by content-derived `snapshot_id`; refuse overwrite.
5. Allow `EXPLORATORY`, `AUXILIARY`, and `TEST_ONLY_NOT_RESEARCH_EVIDENCE` only. Do not add a formal
   daily authority label before an approved validation protocol exists.
6. Reconstruct all domain objects, identities, references, ordering, temporal constraints, and the
   rendered report in the Reader.
7. Add stock/ETF Universes only after this boundary is available; do not implement ETF/Theme models,
   Entry logic, manual trades, lifecycle, Exit, or Dashboard in WP-DQS-1.

## 9. Work-package mapping

The 2026-07-20 research program called the decision-contract package `WP-DQS-0`. The 2026-07-23
approved execution package inserts this audit as `WP-DQS-0` and renumbers the decision-contract
implementation to `WP-DQS-1`. This audit follows the newer execution package. No capability is
considered complete twice.

## 10. Stop condition for this audit

`WP-DQS-0` is complete when this evidence inventory and the V1 decision-Artifact specification are
committed. It does not authorize strategy implementation, provider substitution, Alpha claims, or
trading actions.
