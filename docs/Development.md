# Development and testing

> **Status:** CURRENT_ARCHITECTURE
> **Code Evidence:** `pyproject.toml`, `uv.lock`, `tests/conftest.py`, `tests/contracts/conftest.py`, `tests/persistence/postgres/conftest.py`, `scripts/repository_inventory.py`

## Environment and isolation

Use Python 3.12+ with the repository's locked environment. All Python commands
run behind `uv run`. PostgreSQL tests require PostgreSQL 16 and
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL` pointing to an explicitly disposable
database. The contracts fixture drops its `mra` schema; retained persistence
fixtures use unique schemas. Never supply an operational or evidence database
as the test URL. Do not run competing destructive suites in the same database.

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run python scripts/check_repository_hygiene.py
uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

Consumer changes use focused CLI/application/replay tests first. Changes to the
shared persistence factory require the affected PostgreSQL/account regression;
released migration bytes stay fixed. Installed-command and import-closure guards
cover the current research boundary. Historical tool import relocations retain
behavior/serialization tests; retired CLI-only tests are removed with their entry,
not replaced by weakened domain assertions. Run the full repository suite only
when the affected boundary or acceptance scope requires it.

For packaged-artifact smoke, install the built wheel into a fresh environment
and run `mra --help` outside the checkout, then verify installed schema resources.
Build success alone does not prove that the installed artifact imports.

## Contract map

The generated [inventory](architecture/code-inventory.json) maps every test
function to its declared contract, category, assertion shape and imported code.
It includes support-module consumers; it is not a coverage or sufficiency claim.

| Contract group | Protection |
|---|---|
| Domain / serialization | Valid values, arithmetic/time rules, complete rosters and immutable canonical identities |
| Application | Owner commands and consumer behavior through ports, including negative results |
| PostgreSQL integration | Actual constraints/queries, atomic parent/child writes and consumer reconciliation |
| Runtime / recovery | Idempotency, concurrent claims, fences, leases, unknown commits/effects, failure rollback and restart |
| Migration | Fresh schema, exact guarded upgrade, mismatch refusal and historical byte preservation |
| Research correctness | Independent expected prices/fees/capital/metrics and full-path projections |
| Architecture / tooling | Import/write boundaries, installed entry points, docs and reproducibility |
| Historical reconciliation | Exact allowlisted completed evidence and zero-write replay with external prerequisites |

`tests/contracts` contains current context contracts, renamed from an
implementation-phase directory. The other retained suites cover actual legacy
CLI/application consumers, serialization and account/research invariants.
A name containing a version does not make a serialization contract obsolete.

`tests_historical` is outside default regression because it needs a particular
historical database and Artifact root. Missing prerequisites fail explicitly,
rather than silently skipping. Full retained-suite verification includes:

```bash
uv run python -m pytest -q tests_historical
```

Set `MRA_WP17P_HISTORICAL_DATABASE_URL` and
`MRA_WP17P_HISTORICAL_ARTIFACT_ROOT` to the explicitly identified read-only
evidence scope. Those stable environment names remain historical interfaces;
they do not create an active task or authorize writes. Ordinary decoder rejection
and serialization compatibility stay in default contracts.

## Changing tests or documentation

Delete a test only when its invariant is obsolete, equivalent protection exists,
or it tests only a disposable fixture/implementation detail. Record the precise
reason and replacement protection; retain real failures. Mocked ports are useful
for time/error boundaries when a PostgreSQL slice does not cover that behavior.

Financial expected values must come from independent hand/reference calculation.
Do not derive expected results by invoking the production function under test.
Test count reduction is not an acceptance condition.

After a source/schema/test inventory change run:

```bash
uv run python scripts/repository_inventory.py --write
uv run python scripts/check_repository_hygiene.py
```

Only the small set in `docs/README.md` is current context. Historical records are
immutable, opt-in and checked against their original link namespace. Keep
comments for non-obvious invariants, external constraints and dangerous actions.
A historical work-package name is not an explanation. Published SQL resource
bytes and versioned business identities must not be edited for cosmetic cleanup.
