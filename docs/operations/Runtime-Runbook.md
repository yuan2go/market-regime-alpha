# Runtime Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Current executable operator procedures
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-13
> **Code Evidence:** `pyproject.toml`, `scripts/*.py`, `src/market_regime_alpha/cli`

## Install and verify environment

```bash
uv sync --frozen --extra dev --extra postgres
uv run continuous-research --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
uv run continuous-research portfolio-shadow-day --help
uv run continuous-research recovery-audit --help
uv run continuous-research qualification-protocol-record --help
uv run continuous-research qualification-forecast-record --help
uv run continuous-research qualification-evaluation-record --help
uv run continuous-research qualification-historical --help
uv run continuous-research qualification-oos --help
uv run continuous-research qualification-calibration --help
uv run continuous-research qualification-shadow --help
uv run continuous-research qualification-status --help
uv run model-governance --help
uv run pit-authority --help
```

## Phase E Historical Corpus

This free-data path remains `EXPLORATORY / PIT_INCOMPLETE`. PostgreSQL is the
only business Authority; the Artifact Root stores immutable large bytes and is
never scanned to select an owner.

Freeze an effective-dated real historical constituent set before an Index run:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema market_regime_alpha \
  --principal-id "$MRA_PRINCIPAL_ID" \
  historical-universe-sync \
  --effective-date 2026-06-15 \
  --artifact-root /absolute/path/to/artifact-root
```

`historical-corpus-acquire` accepts an explicit `symbols` list, one or more
exact frozen Universe snapshots, or one exact longitudinal Universe Timeline.
Longitudinal acquisition requires `context_instruments` with distinct,
role-labelled `market_index_symbol` and `theme_etf_symbol`; the command records
and returns the immutable Context Instrument Set reference that must be bound
to the Historical Command. The Phase E frozen methodology accepts exactly
`000300.SH` as the market index and `510300.SH` as the theme ETF; changing those
roles requires a new frozen Experiment. Legacy single-snapshot acquisition may retain the
pre-E3 `context_symbols` input only for replay compatibility. Optional
`timeframe_ranges` freezes different Daily and 5-minute windows without an
implicit Reader shortcut. It performs BaoStock acquisition, deterministic
normalization, logical hashing, staging validation, atomic publish, PostgreSQL
registration and exact reload. Empty provider results, rejected rows and
missing fields remain in coverage.

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema market_regime_alpha \
  --principal-id "$MRA_PRINCIPAL_ID" \
  historical-corpus-acquire \
  --input phase-e-acquire.json \
  --artifact-root /absolute/path/to/artifact-root
```

Before execution, freeze one Free Research Universe owner and a WATCHLIST or
`INDEX` policy. An index constituent set must never be labelled `FULL_A`; the
materializer derives an exact membership snapshot from the historical
constituent owner.

Then freeze the
canonical exploratory Target Protocol, Governed Experiment owner and
`HistoricalResearchCommand`. The command binds the exact normalized Dataset,
security master, policy, target, experiment, calendar, code revision and
DecisionTime. Historical `retrieved_at` is never rewritten to the trading date.

For `FREE_RESEARCH_ARCHIVE`, run, resume and replay require the same explicit
Artifact Root:

```bash
uv run continuous-research ... historical-run \
  --input phase-e-run.json --artifact-root /absolute/path/to/artifact-root
uv run continuous-research ... historical-resume \
  --run-id historical-research-run-... \
  --artifact-root /absolute/path/to/artifact-root
uv run continuous-research ... historical-replay \
  --run-id historical-research-run-... \
  --artifact-root /absolute/path/to/artifact-root
```

`historical-run` input is exactly `command` plus nullable
`max_stage_commits`; a bounded value is the supported interruption test. Resume
reloads exact command/session/receipt/component owners. Feature through Forecast
can see only rows with `event_end <= DecisionTime`; next-session bars enter only
Outcome.

Daily feature history uses one predicate-pushed read whose first date is capped
at 180 calendar days before the Decision date and whose per-symbol result is
then capped at the frozen 61-session Canonical requirement. A sparse, newly
listed or suspended symbol therefore remains explicitly history-insufficient;
it cannot force a scan back to the beginning of a multi-year package.

After a terminal run, `historical-evidence --run-id ... --artifact-root ...`
persists Corpus Summary, cumulative Alpha Ablation, Strategy Economics,
Portfolio Performance and owner-resolved Exploratory Model evidence. Repeating
the command returns the same identities. Negative, inconclusive and
not-estimable findings remain durable. Costs, fillability, impact and capacity
are `ENGINEERING_ASSUMPTION` until calibrated; temporal validation is not Formal
OOS.

Never repair a failed run by scanning directories, choosing `latest`, silently
filling data, substituting a provider or resuming under a different computation
revision. Freeze a new Experiment and Command when code changes, and retain the
interrupted run for audit.

Commands frozen before the Phase E3 constituent timeline remain immutable.
Terminal pre-E3 runs use `IMMUTABLE_PRE_E3_RECEIPT_VERIFICATION`: PostgreSQL
reloads and content-validates their exact command, session and receipt chain,
without applying current E3 materialization semantics. An incomplete pre-E3
run requires its exact historical code revision and otherwise fails closed;
operators must not silently resume it with E3 semantics.

## PostgreSQL Authority Only

Bootstrap a dedicated local authority only with an administrator URL:

```bash
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL" \
  --dry-run
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL"
```

Apply or verify the packaged schema:

```bash
uv run python scripts/apply_postgres_migrations.py
uv run python scripts/apply_postgres_migrations.py --verify-only
```

Expected head: migration 086, `stateful_strategy_lifecycle`. Expected schema
catalog: 270 tables. Migrations 052–067 add Formal Protocol bindings and
owner-resolution receipts, Provider×Contract×Fact decisions,
Historical/Locked-OOS/Calibration owners, the durable underlying Locked-OOS
and frozen-family consumption ledgers, owner-computed Forecast receipts,
reusable Strategy Shadow Policy, C6/C7 stage decisions,
persisted blocked Production Admission and Controlled Execution readiness.
Migration 059 adds only the immutable exploratory training/model-parameter
journal consumed by the owner-resolved Forecast executor; all Formal/OOS,
Calibration and Production flags remain database-enforced false.
Migration 068 installs Historical Corpus Authority. Migration 069 adds the
exact-owner timeframe/date/symbol-bucket selective-read index. Migration 070
accepts the v2 effective-dated historical constituent owner while preserving
immutable v1 Research Universe rows.
Migrations 071–080 add effective/publication-dated Historical Security Facts,
unresolved corporate-action gaps, bounded component/Outcome projections, the
exact constituent timeline, v4 content-verifiable fact acquisition scope,
immutable labelled index/ETF context, owner-bound Outcome label dates and the
exploratory Experiment Definition reloaded before longitudinal Scope.
Corporate-action
absence is evidence only when symbol, interval and constituent lineage are all
inside that immutable scope.
Migrations 081–084 complete longitudinal Historical fact, feature and
configuration ownership. Migration 085 adds stable Strategy Contracts/Versions,
shared cycles/runs/gates/proposals, cross-strategy Portfolio decisions,
observed-Fill allocation, Path Outcomes and typed feedback. It also admits the
bounded `STRATEGY_RUNTIME` child to the existing Continuous Journal; it does not
create a scheduler, broker path, physical Position writer or Production
authorization.
Migration 086 adds one immutable fill-derived realized Strategy Outcome table.
Open Strategy sleeve state remains reconstructed from existing Proposal, Fill
allocation and manual account observation owners; no Position table, scheduler
or execution Authority was added.
Migrations 060–062 add the Full-A Runtime Scope, restartable shared Historical
Session journal, owner-resolved Shadow observations and multi-period Shadow
performance evidence. They grant no trading or Formal research authority.
Migration 067 is a forward-only correction that adds exact Strategy/Portfolio
lineage bindings and temporal/owner constraints. It does not rewrite migrations
060–066 or infer typed lineage for legacy rows.
Migration 065 names the global Artifact-root locator contract for Controlled
packages. New rows must use it; old un-namespaced rows remain immutable and
fail closed instead of triggering filesystem discovery.
Migration 046 remains unchanged. Missing/unreachable PostgreSQL is a blocked
operation; there is no alternate persistent backend.

Migration 046 intentionally stops if an existing database contains reference-only qualified Validation or Historical Sample rows. Do not update or delete those append-only rows in place. Preserve/export the database, audit the owning evidence, and use a separately reviewed forward-repair migration before retrying 046.

## Canonical Runtime

Inspect required arguments before scheduling:

```bash
uv run continuous-research run-due --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
uv run continuous-research portfolio-shadow-day --help
uv run continuous-research portfolio-shadow-replay --help
uv run continuous-research research-universe-sync --help
uv run continuous-research recovery-audit --help
uv run continuous-research report-day --help
uv run continuous-research replay-day --help
uv run continuous-research inspect-run --help
uv run continuous-research inspect-strategy --help
uv run continuous-research replay --help
```

Every command requires an explicit database URL/schema and `--principal-id`.
Bootstrap and administer engineering Principals through `model-governance access-*`;
`continuous-research` checks the active Role/Permission before any
read or mutation. The Principal ID remains a caller assertion until a future
external authentication binding exists, so this is engineering RBAC rather
than production authentication. Every invocation is audited against a
content-addressed operation resource. Non-Admin Shadow and recovery mutations
also require `--approval-decision-id` for an exact independently approved
resource; the denial output reports the required resource ID/hash. Production
mode is rejected before any Runtime Journal mutation. `run-due` remains the
canonical tick operation. `run-day` invokes that same operation and, for a
completed `SHADOW` run, resolves its PostgreSQL Summary and freezes Research
Shadow. Before a due Research/Shadow decision it also attempts the bounded
BaoStock Historical Sample build. No samples remains a valid fail-closed
Forecast result. An already-available `UNQUALIFIED` Registry Dataset permits an
exploratory, uncalibrated Forecast. Production never receives that provider.

After a completed run, inspect the two families and the cross-strategy decision
through the read-only projection:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  --principal-id "$MARKET_REGIME_ALPHA_PRINCIPAL_ID" \
  inspect-strategy \
  --run-id CONTINUOUS_RUN_ID
```

The result must show exact cycle/run/version hashes, gate and proposal counts,
Portfolio status and any lineage-scoped Path Outcome/feedback artifacts. A
`DATA_INSUFFICIENT` run and a `NO_ACTION` Portfolio are valid available facts.
Inspection is read-only and cannot recompute or promote a decision.

For a stateful account-bound Shadow tick, pass the same account identity to the
canonical operation:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  --principal-id "$MARKET_REGIME_ALPHA_PRINCIPAL_ID" \
  run-due \
  --strategy-account-id "$MARKET_REGIME_ALPHA_STRATEGY_ACCOUNT_ID" \
  ...
```

This makes the Strategy child resolve sleeve state from PostgreSQL observed
Fill allocations and manual account observations before policy execution.
Omitting the option preserves stateless research compatibility; it must not be
used for claims about cross-session Position decisions. `inspect-strategy`
reports the frozen position states and any fill-derived realized Outcomes.

The free-data operational sequence is:

```text
continuous-research run-day ...
continuous-research settle-day \
  --trading-date YYYY-MM-DD --next-session-date YYYY-MM-DD \
  --artifact-root ARTIFACT_ROOT --at RFC3339
continuous-research strategy-day --observations OBSERVATION_JSON
continuous-research portfolio-shadow-day --observations PORTFOLIO_JSON
continuous-research report-day --trading-date YYYY-MM-DD --at RFC3339
continuous-research recovery-audit --checked-at RFC3339
continuous-research replay-day --trading-date YYYY-MM-DD
```

`settle-day` resolves the frozen Controlled package, Candidate, Dynamic Pool and
Research Shadow IDs from PostgreSQL and acquires BaoStock five-minute OHLC after
close for both current and missed sessions. It writes Outcome, Targeted Outcome,
Panel V2 and Factor Enrichment artifacts. The same step derives eighteen
multi-horizon/barrier calibration hypotheses from the frozen Forecast exposure
and factual Target labels. A hypothesis can fit only when the Forecast Target
identity equals the Outcome Target identity; the current multi-session Forecast
is therefore not reused as a T+1 forecast and remains `NOT_ESTIMABLE`. Positive
and negative hypotheses persist their complete lineage. It records a versioned engineering protocol (Platt
by default; the research harness also supports Isotonic and Binning) with
trading-date partitions and label-aware purge; insufficient
samples produce `NOT_ESTIMABLE`, and every artifact remains
`calibrated=false`. A forecast quantile is treated as a raw score, never as a
probability. Tencent last-price snapshots remain runtime context and are never
promoted to factual OHLC/barrier evidence. Once factual settlement exists,
retries reload its PostgreSQL-owned identities and immutable packages without
calling the Provider again.

`strategy-day` resolves the settled Research Shadow, Panel and Candidate from
PostgreSQL. When the tick has a Multi-Strategy cycle, its Entry creation also
requires and records the exact canonical Overnight ENTER Proposal; otherwise it
returns `NO_ACTION` instead of independently re-deciding Entry. Its observation
file must explicitly provide every quantity,
price, fillability, cost, holding/exit value and each value's provenance as
`OBSERVED_FACT`, `ENGINEERING_ASSUMPTION`, `CALIBRATED_PARAMETER` or
`OPERATOR_INPUT`; no result-affecting numeric default is supplied. It advances
only the isolated Strategy Shadow ledger.

`portfolio-shadow-day` resolves current Candidate scores, the settled Panel
and any previous Portfolio state from PostgreSQL. Its input supplies a stable
versioned Policy and explicit per-value provenance for prices, ADV, trading
status, price-limit state and session observations. Missing price, ADV,
trading-status, price-limit or session evidence becomes an unfilled Shadow
Intent. `portfolio-shadow-replay` verifies the immutable predecessor/CAS chain.
Shadow Fill/Position never become real Fill/Position.

All four day commands are duplicate-safe and resume partial owner journals on
reinvocation. Strategy Shadow reloads immutable Entry/Fill/Position owner rows
and can advance later Holding/Exit observations until Outcome settlement.
`resume --run-id` releases recoverable Continuous Runtime state;
`replay`, `strategy-replay` and `replay-day` verify owner histories without
creating real trading state. Provider failures leave earlier immutable
PostgreSQL evidence intact. Lease/fence or CAS conflicts fail closed and must be
retried through the same command and identifiers.

`recovery-audit` is read-only. It identifies expired Tick leases, retryable
Provider/Tick failures, partial or missed Research Shadow settlement, missing
Panel V2, partial Strategy Shadow and failed Portfolio replay. It reports the
owner command to use; it does not mutate or bypass a fence.

Free data may run only in `RESEARCH` or `SHADOW`. A Production request must fail with `FREE_DATA_PRODUCTION_AUTHORITY_DENIED`. Do not edit status rows, receipts or hashes to recover a run; resume through the owning journal.

## Phase C evidence resolution

Use `pit-authority assess-provider-fact` separately for every exact Provider,
Contract and Fact Kind. It reloads typed source qualifications/evidence and may
return `QUALIFIED`, `INCOMPLETE`, `REJECTED`, `SUSPENDED` or `REVOKED`; never
copy one Fact Kind's status to another. Current BaoStock/Tencent scopes resolve
`REJECTED` until independently validated formal evidence exists.
`pit-authority revoke-provider-fact` appends an explicit terminal revocation;
ordinary reassessment cannot silently reinstate that scope.

`qualification-protocol-record` accepts only the Formal Protocol reference
graph. PostgreSQL reloads the Target Protocol and Targets, Evaluation Protocol,
Trading Calendar, Universe, Dataset, Historical Sample, Feature, Factor, Model,
Threshold, OOS, Cost, Calibration, Strategy and Entry/Holding/Exit owners, then
stores an immutable owner-resolution receipt for every binding. The Calendar
payload snapshot is accepted only when it is anchored to the existing PIT
Artifact Authority resolution; it is not a second Calendar owner. Caller-supplied
component payloads are rejected. Model Governance also freezes current lifecycle,
Registry version and exact governance action revisions; terminal models are
rejected. Pre-057 Protocols are replay-compatible after migration backfill but
cannot enter a new Formal research path. `qualification-forecast-record` accepts only
Formal Protocol, Formal PIT, symbol/scope and idempotency references. PostgreSQL
derives DecisionTime from the PIT request, resolves exact Model/Configuration/
Code/Feature/Factor/Threshold/Dataset/Universe/Target lineage, invokes only its
installed executor catalog and assigns materialization time from its own clock.
Caller prediction values and backdated materialization times are not accepted;
unsupported exact executors persist `NOT_ESTIMABLE` receipts.
`qualification-evaluation-record` accepts only immutable Forecast, Target
Outcome Label and Panel slice/row bindings; PostgreSQL reconstructs score,
return, label interval and slices, freezes the complete result-affecting
lineage across the complete pre-registered Target family and all referenced PIT
requests. A raw subject/decision-session/outcome-session path is unlocked once;
only that already-frozen family may then consume its Target-specific labels.
The family ledger is bridged to the migration-056 legacy ledger, so neither path
can make previously read evidence pristine again. It never accepts caller-supplied
observation values or result timestamps. `qualification-historical` binds each
sample record to its exact DecisionTime PIT and owner-computed Forecast receipt.
`qualification-oos` requires the Locked-OOS record set to equal the qualified C3
record set inside the exact Locked-OOS windows for every frozen Target. It first
requires estimable Train and Validation floor metrics for every required
Target/fold/sensitivity, then replays Locked-OOS observations, Calendar and
family-level multiplicity before persisting C4. For every Formal operator JSON
command, `actor` must exactly equal the already-authorized `--principal-id`.
`qualification-calibration` accepts a frozen policy file but re-reads the
Formal Protocol, target/label/Forecast pair, calibration artifact, partition
bindings and Formal OOS decision. `qualification-shadow` counts only sessions
created and scheduled after its policy lock with `LIVE_TRUSTED` clock and
`LIVE_ACQUISITION` origin; it replays session events, SourceManifest,
attestation, complete T+1 factual Outcome, Strategy Outcome and Portfolio day. `qualification-status`
persists C6, C8 and C9 state. An optional `--entry-policy` records the exact C6
policy and owner bindings. These commands can persist negative, blocked,
not-estimable or accumulating results. They do not invoke a Broker, unlock
Canonical `ENTER`, or automatically promote a model.

## Authority administration

```bash
uv run state-system --help
uv run decision-system --help
uv run model-governance --help
uv run pit-authority --help
uv run research-shadow --help
uv run model-governance access-bootstrap-admin --help
uv run model-governance access-authorize --help
uv run model-governance access-request-approval --help
uv run model-governance access-decide-approval --help
```

`decision-system` is manual-account decision support. It requires current PostgreSQL model selection; Production qualification is currently forced closed. `research-shadow` freezes research decisions and outcomes, not simulated fills. Strategy Shadow is exposed only as subcommands of `continuous-research`; there is no duplicate installed CLI.

Access Governance permits a one-time Admin bootstrap only while the Principal
table is empty, then uses append-only Role grant/revoke and two-person
engineering Approval. It intentionally has no Production Admission or Broker
permission. Principal IDs on a local CLI are not proof of authentication.

## Validation

```bash
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$TEST_DATABASE_URL" uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

PostgreSQL tests never skip. Use a disposable database and the isolated schemas created by test fixtures. Never point tests at a production database.
