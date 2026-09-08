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
its own numbered SQL resources for legacy applications. Those resources and
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
