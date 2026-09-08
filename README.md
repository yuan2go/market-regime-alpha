# Market Regime Alpha

A-share research and human decision support, with PostgreSQL-backed Runtime,
immutable market evidence, explicit forecasts and reproducible evaluation.
Research outputs do not authorize unattended trading.

Start with [current documentation](docs/README.md). Architecture and owner
contracts describe the executable system; the
[Development guide](docs/Development.md) defines the environment and test gates.
Historical plans and evidence are opt-in through the documentation archive.

```bash
uv sync --frozen --extra dev --extra postgres
uv run mra --help
```

The `mra` interface exposes schema operations, Runtime inspection/recovery,
Generic Backtest/report/replay, archive/prospective operations, daily research and
evidence backup/verification. Retained legacy CLIs have explicit separate
consumers; this is not a full Runtime or account cutover.

Operational writes need task authorization and exact scope, schema, backup,
resource and single-writer preflight. Read the
[Runtime Runbook](docs/operations/Runtime-Runbook.md) before operating an existing
database. Keep credentials, machine paths and deployed profiles outside Git.

No passing test, replay or positive research result establishes formal Provider,
PIT/OOS, Alpha, Model or Production qualification.
