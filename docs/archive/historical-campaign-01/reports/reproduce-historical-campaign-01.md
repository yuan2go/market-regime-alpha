# Historical campaign 01: execution and recovery

Use the retained independent wheel and frozen lock in this evidence root. Never
point destructive pytest fixtures at the persistent research database. The v12
research schema belongs to implementation `81f1ce47508c30e25f9e7dfe104ac2bf77641375`.
Source checkout history and both wheel attestations are retained. Operating
installation activation is outside this campaign.

Set `MRA_DATABASE_URL` to the separately identified persistent research database
and `MRA_ARTIFACT_ROOT` to its canonical root. These are operator environment
bindings; do not paste credentials into Git or reports. `$MRA09` below denotes
`verification/holdout-install-09/bin/mra`, executed with its own interpreter from
outside the checkout. Use `UV_OFFLINE=1 uv run --no-project --python
verification/holdout-install-09/bin/python "$MRA09" ...` for the retained install.

The persistent database identity is `mra_historical_campaign_01_20260912`, OID
7866337, cluster 7681924516459622681. The engineering fixture database is
`mra_historical_campaign_01_disposable_20260912`, OID 7866338. The fresh restore
target is a third disposable database, not a writer replacement.

## Read-only progress, comparison, replay and lineage

```bash
"$MRA09" backtest progress --run-id 7b2f292c-3334-5c86-916b-7f950a61da4d
"$MRA09" backtest replay --run-id 7b2f292c-3334-5c86-916b-7f950a61da4d
"$MRA09" research history-compare --run-id 7b2f292c-3334-5c86-916b-7f950a61da4d --expected-database-name mra_historical_campaign_01_20260912 --expected-database-oid 7866337
"$MRA09" research holdout-inspect --reservation-id e91b28ae-0ba9-5fc9-bcc6-0dd706a5881f --expected-database-name mra_historical_campaign_01_20260912 --expected-database-oid 7866337
"$MRA09" backtest progress --run-id 67794a06-8f16-5732-ace1-de8b00aa4f13
"$MRA09" backtest replay --run-id 67794a06-8f16-5732-ace1-de8b00aa4f13
"$MRA09" research history-compare --run-id 67794a06-8f16-5732-ace1-de8b00aa4f13 --expected-database-name mra_historical_campaign_01_20260912 --expected-database-oid 7866337
"$MRA09" research daily lineage --model-version-id 3924eb4a-b7cd-5741-bc65-d90b93f6f444
```

`progress` reports all declared actions without full owner reconciliation.
`replay` performs the latter. Comparisons are large; redirect exact output to a
new durable file rather than truncating it. `history-compare --publish --actor-id
historical-research-campaign` additionally writes the existing Artifact owner;
read-only comparison without those options does not publish.

## Original-plan continuation and report publication

```bash
"$MRA09" backtest resume --run-id 67794a06-8f16-5732-ace1-de8b00aa4f13 --maximum-actions 510 --maximum-seconds 5400
"$MRA09" backtest publish-report --run-id 67794a06-8f16-5732-ace1-de8b00aa4f13 --actor-id historical-research-campaign --idempotency-key historical-holdout-01-report-v1
```

The displayed continuation is the actual bounded recovery command used after
one completed action. Review remaining original budget and progress before any
future recovery; elapsed invocation time includes drain. Completed actions and
terminal failures are retained. Do not create a new plan from today's template,
rerun FIT with different parameters, or reselect from this already accessed
holdout. New scientific work requires a new experiment and validation design.

Exact reserve/select/prepare/open outputs and their hashes are in
`records/historical-holdout-01-frozen-access-index.json`. The selected plan is
`protocols/historical-selected-holdout-01.json`; the original boundary and
complete development matrix remain unchanged beside it.

## Backup and actual disposable restore

```bash
"$MRA09" evidence backup --directory "$FRESH_BUNDLE" --expected-database-name mra_historical_campaign_01_20260912 --expected-database-oid 7866337 --minimum-free-bytes 1073741824
"$MRA09" evidence fresh-restore --disposable --bundle "$EXACT_BUNDLE" --expected-database-name "$EMPTY_DISPOSABLE_DB_NAME" --expected-database-oid "$EMPTY_DISPOSABLE_DB_OID" --expected-cluster-identity "$DISPOSABLE_CLUSTER_ID" --expected-backup-sha256 "$DUMP_SHA256"
"$MRA09" evidence restore-check --bundle "$EXACT_BUNDLE"
```

For the last two commands, bind the environment to that verified empty
disposable database and a new distinct Artifact root. The actual restore uses
PostgreSQL 16 `pg_restore --single-transaction`; the exact dump, database OID,
cluster, schema, full tables and physical Artifact roster must reconcile.
Never point these commands at the operating or persistent research database
as a restore target. A completed restore does not authorize selecting it as
an operating writer. The final restore record supplies concrete bundle/hash
identities and distinguishes preserved failed history from completed replay.

## Professional source boundary

The repository Runtime Runbook provides `research provider-recording-check`
and `provider-recording-replay`, with versioned original-byte Capture identity,
units, adjustment, finality and timestamp contracts. The local recorded
substitute passed; real professional Provider access was not run. Controlled
source comparisons must hold either the frozen model or the algorithm/protocol
fixed and change one source dimension at a time. Paid access and formal PIT
remain separate authorization/evidence requirements.
