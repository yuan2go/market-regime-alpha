# Data and evidence contracts

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `src/market_regime_alpha/infrastructure/postgres/schema.py`, `src/market_regime_alpha/infrastructure/postgres/migrations`, `src/market_regime_alpha/persistence/postgres/migrator.py`, `src/market_regime_alpha/outcome`, `src/market_regime_alpha/runtime/application/evidence.py`

## Database scopes

PostgreSQL 16 is the durable relational store. The research composition verifies
the exact `MRA_REFOUNDATION_1` schema using `SchemaManager.verify`; its release
state remains the value recorded by that owner. Ordinary startup never applies
DDL. Fresh bootstrap and explicit registered additive upgrades are different
operations. An operational scope cannot be destructively recreated.

The separate retained `persistence/postgres/migrator.py:PostgresMigrator` loads
its own numbered SQL resources for retained account, governance and historical
applications. Current research changes belong only to `infrastructure/postgres`;
empty per-package migration globs are not schema owners and have been removed. Those resources and
tables are not the research schema and must not be summed into one catalog.
The [inventory](code-inventory.json) lists every packaged SQL file with its
checksum and declarations. Current table membership comes from
`schema.EXPECTED_TARGET_TABLES`, then is checked against PostgreSQL.

A database identity includes database name/OID, cluster identity and schema
fingerprints. Equal Run UUIDs in different databases are different evidence
scopes. A restored success is not an original failed Run repaired. No database
is adopted because another is unavailable.

## Time and population

Market preserves event time, Provider time where proven, first observation,
recorded time, knowledge cutoff and exact revision lineage. Decision visibility
uses exact source versions known by its cutoff. Retrospective reconstruction
does not confer Formal PIT. Trading sessions come from canonical calendar facts.

Target references and observation windows are explicit definitions. A Decision
reference is not a simulated fill. Market Outcome owns realized labels and
independent path/checkpoint facts; future prices cannot gate an earlier
prediction. Late or revised source data cannot change an original publication's
known time. Missing, suspended, unavailable and not-yet-mature remain distinct.

Universe, eligible, Feature-ready, prediction and mature/estimable populations
retain complete membership/reasons. Candidate ranking is strict complete case.
Partition and Evaluation freeze the complete parent roster before slicing;
unselected broken members cannot disappear from a full-path calculation.

Research Validity reads only the OutcomeRevision acquired by the original
Evaluation, including Capture/normalization clocks and physical hashes. Published
commitments, Partition members, acquisition and Decision commitment rosters must
match. Model/baseline interpretation uses their exact common estimable population;
all sampled and excluded members remain visible. Temporally invalid observations
are excluded with reasons, never relabeled. Calendar and lineage reads retain the
complete cohort, independently of bounded operational health inspection.

Versioned files in `research_qualification/protocols` are immutable source
resources with pinned SHA-256 and database-clock declaration evidence. They are
not registered PostgreSQL Artifacts, persisted Evaluations or qualification.
The existing exclusive service writer reservation stays intact. Evaluation-owned
validity formulas derive read-only interpretation from canonical labels; the
original frozen Evaluation metric rows and report bytes remain authoritative for
their original protocol. Sep-10 new statistics are `POST_HOC_DESCRIPTIVE`.

## Financial and model identity

`research_qualification/domain/episode_economics.py` implements independently
funded, fully liquidated hypothetical episodes. Each episode shares one capital
budget across its securities. Entry/exit notional, cash and fees reconcile;
rejection creates no executed trade. This is not a continuous account,
cross-period position model, or proof of A-share fillability.

Old formula-less/V1 results and newer episode results keep different identities
and financial meanings. Reconciliation reloads actual persisted root fields and
source/cost children. Report consumes those owner results and never computes
labels or economics from bars. The retained exact serializers are required for
historical bytes, not an invitation to mix old and new metrics.

A ModelVersion binds completed training, exact Feature/Target semantics,
training knowledge cutoff, input roster, environment and fitted Artifact.
Experimental consumption uses an explicit allowed Model-use identity and
expiry/revocation. It grants no formal qualification and never chooses the
latest available model.

New explicit `deterministic_ridge` algorithm version `2.0` uses fitted Artifact
schema v2: round-trippable binary64 means, positive scales and coefficients,
stable scaling for tiny nonzero features, and the same binary64 transform at
fit and inference. Prediction output retains its declared 12-decimal precision.
Every fit is loaded and checked for finite training predictions before publication.
Version `1.0` retains its original bytes and Decimal inference; an old fit whose
quantized scale becomes zero now refuses publication. Old ModelVersions are not
retrained, relabeled or automatically replaced by v2.

## Transaction and Artifact consistency

Each owner uses its narrow UoW for business writes, Receipt, Audit and applicable
Runtime completion. Runtime admission/fence and dependencies are checked before
write. A deterministic rejection rolls back; the failure recorder validates a
live fence again before atomically recording failure. A stale fence writes none
of those facts. Unknown external effects require reconciliation before retry.

Large immutable data/model/report bytes live in the Artifact store. PostgreSQL
owns hashes, sizes, locators, dependencies and verification observations.
Publishing/verifying physical bytes occurs outside business write transactions.
Consumers authenticate both the owner binding and physical bytes.

The existing `mra evidence` inventory/backup/restore surface is an operational
projection, not business Authority. A consistent database snapshot is bound to
its referenced Artifact roster. Backup readability alone is insufficient:
restore schema, owner rosters, physical hashes and relevant replay/report bytes
must reconcile in an independently identified copy. Preserve unavailable and
failed evidence; do not fabricate replacement identities or prior known times.

## Artifact producers and consumers

Paths in this table are under `src/market_regime_alpha`. There is no Artifact
kind registry granting business authority: the exact owner binding determines
how bytes may be consumed.

| Payload | Producer / binding | Actual consumer |
|---|---|---|
| Provider response | `market/application/capture.py` → Capture and Artifact metadata | Market normalization, archive verification and source lineage readers |
| Dataset manifest | `interfaces/daily_research.py:DailyResearchOperations`; generic Backtest Dataset materialization → Research definition | Candidate and Decision input queries; Dataset reconciliation |
| Training input and fitted model | `research_qualification/application/research_models.py:ResearchModelApplication` → TrainingRun/ModelVersion | `queries/model_forecast_inputs.py` under the PostgreSQL adapter, exact Model-use inference and model replay |
| Backtest JSON/Markdown | `research_qualification/application/backtest_reports.py:BacktestReportApplication.publish` → report binding | `queries/backtest_reports.py`, inspect/replay and comparison; no raw-bar metric calculation |
| Daily frozen plan and forecast report | `interfaces/daily_research.py:DailyResearchOperations` → Runtime/publication bindings | Pending Outcome recovery, `queries/daily_predictions.py` and `interfaces/daily_delivery.py:DailyReportDelivery` |
| Code/configuration | Exact owning plan/run/archive commands → explicit Artifact bindings | Startup/replay/recovery input authentication; never a current/latest lookup |

`runtime/application/artifacts.py:ArtifactApplication.publish` publishes and
verifies content-addressed bytes before the short metadata UoW. Receipt replay
prevents duplicate business metadata; it does not promise zero repeated file
I/O. `infrastructure/artifacts/local.py:LocalArtifactStore` owns physical storage.
