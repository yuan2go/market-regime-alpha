# Runtime Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Current executable operator procedures
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
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

Expected head: migration 057, `formal_research_runtime_closure`. Expected schema
catalog: 194 tables. Migrations 052–057 add Formal Protocol bindings and
owner-resolution receipts, Provider×Contract×Fact decisions,
Historical/Locked-OOS/Calibration owners, the durable underlying Locked-OOS
and frozen-family consumption ledgers, owner-computed Forecast receipts,
reusable Strategy Shadow Policy, C6/C7 stage decisions,
persisted blocked Production Admission and Controlled Execution readiness.
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
PostgreSQL. Its observation file must explicitly provide every quantity,
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
component payloads are rejected. `qualification-forecast-record` requires an
exact OutcomeTarget-bound Forecast and reloads its Model Lineage owner.
`qualification-evaluation-record` accepts only immutable Forecast, Target
Outcome Label and Panel slice/row bindings; PostgreSQL reconstructs score,
return, label interval and slices, freezes the complete result-affecting
lineage, and consumes each underlying Locked-OOS subject/session/label interval
in a durable ledger whose identity survives Label revision and Model, Forecast,
Dataset, Target or Protocol substitution. The first exact Target and Label remain
immutable provenance; neither is the raw-outcome reuse key. It never accepts
caller-supplied observation values or result timestamps. `qualification-historical` and
`qualification-oos` persist C3/C4 owner decisions; the latter replays those
owner-resolved observations, the frozen Calendar and metrics.
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
