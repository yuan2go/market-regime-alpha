# Operational data-loop verification — 2026-09-10

> **Status:** HISTORICAL
> **Authority:** Immutable engineering and operational observation record; not qualification Authority

The original research scope was handed to the frozen canonical installation.
A real new prediction was published before its Target window, and survives
graceful restart and independent backup restoration with identical report/replay.
Its Outcome has not naturally matured. **Overall exit: BLOCKED_BY_REAL_TIME.**
Historical terminal failures remain failures; they are not repaired by this result.

## Revision and environment

| Identity | Exact value |
|---|---|
| Fetched main baseline, also unchanged at final fetch | `876b995268673b6556c1f148c9c9af485cd8f135` |
| Baseline tree | `c782b15e55bc81f4ad594941c002127c947c198c` |
| Installed implementation | `1b5377d6adf46b61b06f34356bd37f2e599c74e5` |
| Implementation source tree | `1e8f6682340c8591f25d7575f2960ae13197c3fc` |
| Final test-only correction | `0d09cda03f24146dbef4a224b91076bd17305e3e` |
| Verified tests tree | `f9bb41fdb2bdd80f9ec5b5a5e2a2d8495d141a8b` |
| Branch | `agent/operational-data-loop-proof-20260909` |
| Frozen wheel SHA256 | `c4251402a8fbf0c44ae42da0da9e21459174e6eba02f60e84b03ace8f453a9da` |
| Installed implementation content SHA256 | `b705e0c2b4b5529137d2a5679dbcae2ecfe58596fc423771ee741a3f5d50fcce` |
| Dependency lock SHA256 | `5cfb5ced3a2587910e172a66f5a5912668d16d0c8dd54e0ae3e619384113a41d` |
| Original database | `mra_wp18q_r2_operational_20260905`, OID `287543`, cluster `7681924516459622681` |
| PostgreSQL | `16.15`; original owner retained |
| Schema | `MRA_REFOUNDATION_1`, registered v8, 194 canonical tables |
| Catalog SHA256 | `44a27e01109567395ad803e0c0c3b2859e8890fb23cf27b0b2c26b98db559e51` |
| Artifact root binding SHA256 | `a44c60d4bbf9045fd33a119de4da520d965364d37904a79275fdc2236a7678a0` |
| Deployment receipt SHA256 | `f6a855f93ef14faa371038f627f816d33905d439918a1757558cf47b70df6680` |
| Profile after verified backup refresh SHA256 | `bc58d4587089a9c9665300716cd385ced7af63712c342a950e817230f6b0de21` |

The documentation delivery is a descendant with identical source/tests, SQL,
dependencies and executable templates. The external delivery attestation binds
its actual final commit; this record does not include its own containing commit.
The original checkout, branch, unrelated changes and `.idea/modules.xml` were
preserved. No push, PR, merge, history rewrite or campaign rerun occurred.

## Actual topology and exclusion

`owned current-user LaunchAgent → non-editable installed mra → bootstrap_application
→ canonical Runtime/Market/daily owners → PostgreSQL + content-addressed Artifact
→ original-plan queries/reconciliation/report`.

The service label is `local.mra.prospective.r2-xshg32`, UID 501. The private
deployment record supplies executable, paths, credentials and profile; none is
inferred from a process name. Final bounded activation was at
`2026-09-09T18:18:38.644277Z`, graceful SIGTERM at `18:19:55Z`, and restart of the
same installation at `18:26:30Z`. The observation cutoff is
`18:32:43.570383Z`. The approximately 14-minute wall-clock interval includes the
backup stop; it is not 14 minutes of uninterrupted uptime or a multi-day proof.

Only the owned service and its existing backup job were changed. Backup refresh
uses 03:00/19:00 local-time triggers, `KeepAlive=false`, no initial immediate
trigger, and the tested exact-installation drain/backup/verify/restart procedure.
The main service continues waking under Runtime's reservation. The supervisor
does not decide business due time. Future scheduled backup firings are unobserved.

The runtime authenticates as `mra_r2_runtime_20260909`, OID `6775405`.
Diagnostics and manual backup have separate read-only logins. Exact-database HBA
rules reject the old generic login while leaving other databases' rules and
shared operator role unchanged. Runtime has required owner inserts/updates and
identity-column reference locks, without DELETE/TRUNCATE/DDL, ModelVersion
registration or formal qualification writes. HBA SHA256:
`183f3c28c132ab76aa7fa094e194c456372b6b49152d522e6a122d731bd67cf1`.

Initial and per-action principal checks reject impersonation, wrong principal
or missing grants. A second supervisor was rejected in 0.92 seconds with
`OPERATION_DUPLICATE_SUPERVISOR`; the old installed wheel rejected the current
profile with `DEPLOYMENT_INSTALLED_PACKAGE_MISMATCH`, before Provider or business
writes. Old installations/profiles/logs remain available as provenance. Their
automatic/default launch routes are not current writers. Trusted OS/cluster
administrators still have maintenance power; this is not a hostile-admin boundary.

## Real capture and publication

The explicitly recorded installation handoffs remain within the same original
DB/Artifact lineage. The preceding installed checkpoint `5d81f721…` collected
32 actual BaoStock daily-bar responses for September 9 through claimed Runtime
Attempts. All 32 normalized, with zero SourceGaps. Two explicit population rounds
retain both the failed first normalization and the successful next round; the
Provider's full 300-member classification was normalized, not reduced to the
32-symbol prediction sample. Repeating the recovery reused the same successor.
No historical bytes were presented as a new Provider response.

Another 32 actual bar observations for the older September 8 Target were
explicitly collected late. They retain their September 10 local observation
times and do not establish on-time collection. Across these recorded requests:
66 Capture rows, 64 daily bars, two population Capture requests. These are
post-close exploratory observations, not formal PIT or intraday availability.
Login success in the final installation's preflight is recorded separately.

| New publication binding | Identity / actual fact |
|---|---|
| Prediction | `3c3e181e-692d-535b-aea0-f855c9e9e418` |
| Runtime | `000409b6-eb1e-5e77-898f-eb3a201aadf9`, 9 steps SUCCEEDED, one Attempt each |
| Dataset | `351469dd-f65b-540f-845b-37bbfcceab1f` |
| Decision | `7ac791ea-498d-49f3-ad3d-c768b7a4d6f4` |
| ModelVersion | `fe47f296-17dc-5654-a9eb-cf149f5b01c9`, unchanged |
| Experimental use | `60902ae3-5776-5460-91b1-90ed3bc03525`, unchanged, not revoked |
| Target | `8cdc2e02-bf29-5f96-995c-4b576b9ab130`, unchanged |
| Actual input cutoff / DecisionTime | `2026-09-09T18:16:08.984967Z` |
| Actual publication | `2026-09-09T18:17:35.943618Z` |
| Target window | `2026-09-10T01:30:00Z` to `07:00:00Z` |
| Sampled / active eligible / feature-ready | 32 / 31 / 31 |
| Model / baseline / common predictions | 31 / 31 / 31 |
| Remaining member | Membership UNKNOWN, `MARKET_EVIDENCE_MISSING`; retained in the 32-member report population |
| Publication receipt | `c999b1a3-2b5f-4e77-b129-1c91cef44ec9` |
| JSON report | `90716533-afe5-41f9-bf00-3ebbdafa5a58`, 39,865 bytes, `0a8053a95168f807ed02cc4c08a792337d321872288939f049da02025bf3ed77` |
| Markdown report | `66d9bb81-cb8c-4f8c-8925-dc37846a9068`, 4,080 bytes, `2c288fd5aec84471e15ff050da6bd5bef8fa3fab421b41376ca086a6a744c230` |

This is an explicit new operator request after permission repair, not an
automatic fallback or reopening of failed prediction `d89afb7c…`. No future
Target price was required to publish. The model was registered before publication.
Repeated prediction reused exactly the same Run/steps/Attempts/fences; complete
report/replay matches before and after restart and in the independent restore.
The published research list is not a trading instruction or account result.

## Continuity, negative evidence and repairs

| Existing work / failure | Actual treatment and remaining boundary |
|---|---|
| New published prediction, future Outcome | `b51cef3b-9ff8-5b41-a015-2b6deffd14d7` QUEUED, `PENDING_MATURITY`; original frozen plan retained after restart |
| Old naturally mature publication `e208e9d4…` | Actual late capture completed, but Outcome Runtime `7d31a1d1…` is FAILED with `OUTCOME_AUTHORITY_INTEGRITY_FAILED`; no reopening or Evaluation claim |
| Old current prediction | `2a357d21…` FAILED after missing reference-lock privilege; service reports `PREDICTION_RECOVERY_REQUIRED`, does not reexecute it, and continues other pending Outcomes |
| Population normalization failure | Whole-classification Instrument Artifact prerequisites repaired; exact original failed plan/Capture reconciled; only explicit next round `6eb6c9af…` executed |
| Expired Artifact verification | Refresh scope now includes original Runtime config, Target/metric code and all existing classification sources; no Capture known-time changes |
| Late unobserved Outcome | `OUTCOME_DATA_UNOBSERVED` after automatic grace; explicit canonical collect-outcome refuses already started/terminal settlement |
| Historical prediction report | Preserved v1 `model_prediction` serialization; old JSON/Markdown hashes match, including after restoration |
| Expired lease / unknown effect at final snapshot | 0 / 0; their refusal/recovery contracts covered in disposable PostgreSQL, not fault-injected into the original DB |
| Evaluation/report pending and delivery UNKNOWN | No corresponding real item; directed unknown-commit/report tests pass. External delivery is NOT_CONFIGURED, not delivered |
| Missed windows / gaps | 544 historical opened slices MISSED, one planning gap retained; current generation is declared with actual time |
| Original large campaign | `6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` remains FAILED; no 936-action rerun or copying of successful rows |
| Historical slow read | Prior QueryCanceled root cause remains UNPROVEN where failure-time telemetry is absent; no timeout increase or new index claimed as a fix |

The prospective series has 864 expected windows: 544 opened and 320 future at
the cutoff. Seventeen slices have historical Attempts (16 DEADLINE_EXHAUSTED,
one NORMALIZATION_BINDING_REJECTED), and zero successful prospective archive
Capture observations. Terminal coverage is 544/544 while successful/on-time
capture rates are 0/544. Final-installation ticks discovered zero legal due
prospective Attempts. Daily captures are a different denominator and do not
rewrite these numbers.

Six recorded final-installation ticks took 41.37–50.67 seconds against a
120-second budget. Current active, expired and unknown Attempts were all zero.
One new publication is pending natural maturity; one older Outcome is failed.
Health is attention-required with explained negative history, not globally green.

## Backup and independent recovery

The existing registered `daily_operational_closure_v8` upgrade was applied to
the identified original v7 database after exact backup/preflight and isolated
verification. All 113 released SQL resources and `uv.lock` are unchanged in Git.
The before/after historical projection matched. Upgrade was not inferred from
a restore, and no original database was recreated.

The post-publication exported snapshot contains 2,973 referenced Artifacts:

- Dump: 208,997,592 bytes, SHA256 `04bb328482508a093314146b5ca1dac74abefa319717a870b27d41993cb16a1b`.
- Receipt: SHA256 `7673cc17f9e54294ee542c6784b77ebade6bf67b04a56c03ad69373da6a9ebc5`; verified `2026-09-09 18:23:34.142289+00`.
- Snapshot contract: `POSTGRES_EXPORTED_SNAPSHOT_AND_EXACT_ARTIFACT_ROSTER`.
- Two verified physical devices on the same host; **not offsite**. Mutable integrity observations after the snapshot are explicitly separate.
- Complete refresh/drain/restart workflow: PASS, 392.98 seconds. A measured per-backup-connection work_mem of 256 MB was used; no global DB timeout/configuration increase.
- Independent restore: `mra_oploop_restore_publication_20260910`, OID `2095544`, cluster `7683543274548948162`, fresh Artifact root; 96.54 seconds.
- Schema, all recorded snapshot table hashes and Artifact bytes reconcile: `matched=true`, `mismatch_count=0`, zero missing/extra bytes.
- Old and new publications replay twice under a database-enforced read-only login. Independent installed CLI report and replay reproduce the complete original output with zero business writes.

Restore deliberately does not clone operational roles, HBA or private credentials.
Those remain separately controlled deployment prerequisites. The copy has never
been an operational writer. No full-database equality is claimed after subsequent
live or integrity-metadata writes.

## Executed checks and retained failures

Exact arguments, timestamps, source/tests identity and exits are in the external
command records. PostgreSQL tests used explicit disposable databases on separate
test ports, never the original operational database.

| Command / scope | Actual result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS, activation baseline locked environment |
| `uv run python -m pytest -q` including PostgreSQL | PASS, 4,142 tests at merged-main baseline; 2,011.52 pytest seconds / 2,040.40 wall seconds |
| `uv run python -m pytest -q tests_historical` with exact read-only prerequisites | PASS, 7 tests; 13.38 seconds initially, 7.52 seconds after relevant source fixes |
| Final directed pytest: restricted login, collection/handoff, complete daily vertical, pending/recovery, Artifact refresh and installed principal | PASS, 43 tests / 75.81 seconds wall, source/test identities above; exact 10-file roster in command record |
| Earlier source-bound directed correction gates | PASS after recorded failures, 39 tests / 69.50 seconds and earlier focused scopes; not summed into a fictitious full-regression count |
| `uv run python -m ruff check .` | PASS at final source/test revision |
| `uv run python -m mypy` | PASS, 635 configured files |
| `uv run python -m build --installer uv` with `UV_OFFLINE=true` | PASS, frozen source, 5.36 seconds; prior online TLS failure retained, cached locked build used |
| Non-editable install from hashed locked requirements; isolated installed `mra --help` | PASS; installed package/metadata/dependency roster verified by prepare-deployment |
| `uv run python scripts/repository_inventory.py --write`; hygiene and docs/link checks | PASS; no source/schema inventory drift |
| `git diff --check` | PASS before each commit and final delivery |
| Full repository repeat after local corrections | NOT_RUN: no further public pool/UoW/schema change; directed owner/runtime/regression scope executed |
| Live fault injection, broker, formal qualification, old campaign rerun | NOT_RUN / outside authorization |
| New real mature Outcome/Evaluation | BLOCKED_BY_REAL_TIME; no synthetic clock, waiting or backdating |
| Sustained multi-day service | BLOCKED_BY_ELAPSED_REAL_TIME |

Failed logs are retained: initial schema incompatibility and stale profiles;
restricted-login permission failures; expired Target/config/classification
Artifact prerequisites; report v1 byte drift; the terminal original Outcome and
prediction failures; and the final zero-prediction test's incomplete Runtime
test double (42 passed / 1 failed, corrected without changing its assertion).
Expected competing-supervisor and old-install refusal exits are successful
negative checks, not unexplained failures. A restore JSON comparison initially
compared dataclass repr strings to structured JSON; canonical installed CLI
report/replay then proved exact equality without changing production serialization.

## Delivery and exit

The [machine-readable evidence index](Operational-Data-Loop-Evidence-2026-09-10.json)
binds the observations, population, protocol and hashes. The incremental private
bundle `operational-data-loop-proof-20260910.tar.gz` contains raw commands/exits,
failed and repaired checks, complete-line service log snapshots, receipts and
delivery attestation. Large prior evidence and backup bytes remain at their
verified original and physical mirror locations; they are referenced by hash,
not repeatedly repackaged. Credentials and full connection configuration are not
in this repository. A recoverable copy of the new incremental bundle is retained
on the second local physical device.

| Gate | Decision |
|---|---|
| OPERATIONAL_HANDOFF_PASS | PASS |
| REAL_DATA_CAPTURE_PASS | PASS in the explicitly recorded original-scope installed handoff lineage |
| REAL_DAILY_PREDICTION_PASS | PASS, actual pre-window publication |
| REAL_MATURE_EVALUATION_PASS | BLOCKED_BY_REAL_TIME for the new publication; old failed settlement remains separate |
| OPERATIONAL_DATA_LOOP_PROOF_EXIT_GATE | BLOCKED_BY_REAL_TIME |
| Original overall prospective qualification | Remains blocked; no new real due archive Attempt observed |
| ALPHA_PROVEN / PRODUCTION_ADMISSION | NO / NO |

The service and bounded backup refresh remain active for natural accumulation.
Do not start another worker to replace the failed identities. Inspect the
original pending plan after its real Target matures; preserve missing/negative
results and replay the resulting canonical Outcome/Evaluation/report. Model use
expires October 7 and the currently captured calendar extends to September 17;
neither is silently replaced. Research-validity/Alpha iteration should begin
only after the loop has accumulated stable real observations, not merely because
this handoff or its disposable engineering tests passed.
