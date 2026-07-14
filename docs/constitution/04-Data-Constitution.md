# The Constitution of Market Regime Alpha

# Volume V — Data Constitution

> **Document:** `docs/constitution/04-Data-Constitution.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide data eligibility, point-in-time correctness, provenance, dataset identity, quality, revision, access, and data-governance rules  
> **Applies to:** Market data, reference data, universe data, fundamentals, events, policy data, industry/theme mappings, ETF data, Level 1/Level 2 data, research datasets, replay datasets, model inputs, labels, sidecars, manifests, data providers, adapters, data builders, agents, research and future production systems  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, `02-Architecture-Blueprint.md`, and `03-Research-Framework.md`

---

## 0. Purpose

`market-regime-alpha` is an Alpha Research Operating System for the China A-share market.

Such a system cannot be more trustworthy than the information on which its research claims are built.

A model can be mathematically correct and still be invalid because:

- the historical universe used today's surviving securities;
- a bar was treated as final before it was actually final;
- a financial statement was used before its publication time;
- a current industry classification was backfilled into the past;
- a forward-adjusted price series introduced future corporate-action information;
- missing historical trading-status fields were replaced with convenient defaults;
- a free API response was treated as a reproducible historical dataset;
- a provider changed semantics without changing dataset identity;
- a result could not be reconstructed because the raw source artifact was not preserved;
- a bar-derived proxy was presented as real capital flow;
- a research process queried “latest” data during historical replay.

The purpose of this Data Constitution is therefore to answer one governing question:

> **What data is allowed to support what level of research claim, under what temporal, provenance, quality, licensing and reproducibility conditions?**

The central rule is:

> **Data accessibility does not create evidence authority. Evidence authority must be earned through explicit semantics, point-in-time correctness, provenance, quality, reproducibility and governance.**

This document defines:

- the project-wide meaning of data eligibility;
- the separation between source access, canonical data and formal research datasets;
- the required point-in-time model;
- the temporal semantics of market and non-market data;
- data provenance and lineage requirements;
- raw, normalized, canonical and derived data responsibilities;
- dataset identity and manifest requirements;
- quality-gate behavior;
- missing-data and conflict policy;
- corporate-action and price-adjustment rules;
- tradable-universe and eligibility requirements;
- industry, theme, ETF, capital-flow and microstructure data rules;
- fundamental, event and policy availability rules;
- data-provider qualification;
- licensing, storage and access constraints;
- revision, backfill and incident handling;
- current repository data posture during refoundation.

This document intentionally does **not** define:

- the mathematical definition of every feature;
- IC, RankIC or factor-promotion thresholds;
- strategy entry, hold, add, reduce, rotate or exit rules;
- train/validation/test numeric acceptance criteria;
- portfolio allocation rules;
- execution fill models.

Those responsibilities belong to later Constitution volumes and lower-level specifications.

---

# 1. Constitutional Position of Data

## 1.1 Data is part of the research claim

Within this project, a result is never interpreted as:

```text
Model M achieved result R.
```

The more complete statement is:

```text
Model M
using Dataset D
constructed from Source Set S
under Time Semantics T
for Population U
with Adjustment Policy A
and Quality State Q
achieved Result R
under Experiment Identity E.
```

The dataset is therefore not an interchangeable implementation detail.

Changing a result-affecting data property may change the research meaning.

Examples include:

- provider;
- timestamp interpretation;
- adjustment method;
- finalization rule;
- universe history;
- security identifier mapping;
- missing-data treatment;
- corporate-action treatment;
- market calendar;
- industry/theme mapping version;
- event publication time;
- revision policy.

A material change to these properties must create a new dataset identity or an explicitly versioned revision.

---

## 1.2 Data validity is claim-relative

There is no universal binary classification:

```text
Good Data / Bad Data
```

A dataset may be sufficient for one purpose and insufficient for another.

For example:

- a recent free minute API may be sufficient for interface development;
- the same source may be insufficient for a multi-year point-in-time candidate-ranking claim;
- unadjusted prices may be correct for historical execution simulation;
- an explicitly point-in-time adjusted view may be more appropriate for certain return or trend calculations;
- a hand-curated industry map may be useful for a current dashboard;
- the same map may be invalid for historical theme-rotation research.

The correct question is:

> **Is this dataset eligible for this exact research claim and decision-time convention?**

---

## 1.3 Data convenience has no constitutional authority

The project does not promote a source merely because it is:

- free;
- fast;
- familiar;
- easy to call from Python;
- already integrated;
- available on the current machine;
- able to return plausible values.

Likewise, the project does not reject a source merely because it is paid.

The relevant criteria are:

```text
Semantics
Point-in-Time Correctness
Coverage
Provenance
Reproducibility
Revision Policy
Quality
Authorization
Operational Reliability
Cost Relative to Research Value
```

---

# 2. The Data Authority Model

The project distinguishes the following concepts.

```text
Provider
    ↓
Source Artifact
    ↓
Adapter / Ingestion
    ↓
Normalized Observation
    ↓
Canonical Point-in-Time Data
    ↓
Dataset Build
    ↓
Dataset Manifest + Quality Report
    ↓
Eligibility Classification
    ↓
Research Role Assignment
    ↓
Experiment Consumption
```

These layers must not be collapsed.

---

## 2.1 Provider

A **Provider** is the external or internal origin from which information is obtained.

Examples may include:

- exchange or official source;
- commercial data vendor;
- broker or QMT archive;
- Tushare;
- public web API;
- local licensed archive;
- internally generated reference dataset.

A provider is not a dataset.

The same provider may expose multiple products with different:

- fields;
- frequencies;
- retention;
- permissions;
- timestamp conventions;
- revision rules;
- quality guarantees.

Provider name alone is insufficient for reproducibility.

---

## 2.2 Source Artifact

A **Source Artifact** is the retrievable or preserved unit that the project actually ingested.

Examples:

- a downloaded file;
- an API response payload;
- a provider snapshot;
- a vendor export;
- a broker archive file;
- a versioned reference-data package.

Where legally and operationally permitted, source artifacts should be immutable or content-addressed.

A source artifact should be identifiable by information such as:

```text
Provider
Product / Endpoint
Retrieval Time
Request Parameters
Coverage
Schema / Data Dictionary Version
Content Hash
License / Access Context
```

The project must not assume that the same API query executed later returns the same historical truth.

---

## 2.3 Adapter / Ingestion

An adapter translates provider-specific representation into project-understood semantics.

An adapter may:

- map symbols;
- parse timestamps;
- normalize units;
- decode provider fields;
- attach provider metadata;
- validate schema;
- reject ambiguous records.

An adapter must not silently:

- invent missing historical state;
- reinterpret unknown timestamp semantics as known;
- declare unfinished bars final;
- manufacture point-in-time history;
- convert proxy data into “real flow” labels;
- hide provider conflicts;
- upgrade data eligibility by convenience.

An adapter performs translation, not epistemic promotion.

---

## 2.4 Normalized Observation

A normalized observation uses stable internal field names and types.

Normalization answers:

> “Can the system read this information consistently?”

It does **not** automatically answer:

> “Was this information historically available and formally eligible?”

The current `a_share_bars.py` capability is an example of valuable normalization and provider abstraction.

Its existence does not, by itself, prove:

- historical finalization;
- PIT adjustment;
- PIT universe;
- historical tradability;
- reproducible provider snapshots;
- formal research eligibility.

---

## 2.5 Canonical Point-in-Time Data

Canonical data is the project-approved representation of an information domain for a defined use scope.

Canonical data must have explicit semantics for:

- identity;
- time;
- availability;
- version;
- provenance;
- missingness;
- corrections;
- eligibility.

There may be multiple canonical views for different legitimate purposes.

For example:

```text
Raw Unadjusted Price View
Point-in-Time Adjusted Research View
Execution Eligibility View
Current Display View
```

The project must not collapse different legitimate views into one ambiguous column.

---

## 2.6 Dataset

A **Dataset** is a controlled, identifiable collection of data artifacts prepared for a defined research scope.

A dataset must not be defined only by a directory name such as:

```text
data/final
```

Its identity must come from a manifest and content or version references.

---

## 2.7 Research Role

Data quality and data role are different dimensions.

A formally eligible dataset may be assigned a role such as:

```text
Development
Train
Validation
Calibration
Test
Sealed Test
Shadow Observation
Production Input
```

The rules governing sample-role isolation belong primarily to `07-Validation-Constitution.md`.

This Data Constitution requires that role assignment be explicit and that data access controls preserve the assigned role.

---

# 3. Data Eligibility Classes

The project separates **data eligibility class** from **dataset research role**.

The canonical eligibility classes are:

```text
UNQUALIFIED
EXPLORATORY
REHEARSAL
FORMAL_RESEARCH
```

A future production system may apply additional production-input qualification, but production authority is not implied by `FORMAL_RESEARCH` status.

---

## 3.1 `UNQUALIFIED`

Use when critical semantics are unknown or the artifact has not been reviewed.

Examples:

- unknown timestamp meaning;
- unknown adjustment status;
- unknown symbol mapping;
- untraceable copied CSV;
- missing provenance;
- unknown revision state.

Allowed uses may include:

- manual inspection;
- debugging parsers;
- initial source reconnaissance.

It must not support formal performance claims.

---

## 3.2 `EXPLORATORY`

Use when data is sufficiently understood for hypothesis exploration but does not satisfy the requirements of the intended formal claim.

Typical uses:

- prototyping;
- smoke tests;
- interface development;
- rough hypothesis screening;
- chart inspection;
- non-authoritative dashboards;
- adapter development.

Exploratory results must be labeled honestly.

An exploratory result may motivate formal research.

It may not be silently promoted into formal evidence.

---

## 3.3 `REHEARSAL`

Use when a controlled dataset satisfies a defined subset of formal contracts and is intended to prove that the research pipeline can operate correctly before wider formal construction.

A rehearsal dataset may be used to validate:

- ingestion;
- schema;
- PIT joins;
- sidecar coverage;
- manifest construction;
- replay behavior;
- execution simulation wiring;
- attribution pipeline;
- fail-closed gates.

A rehearsal dataset does not automatically prove market-wide Alpha.

The current repository's `formal_dataset_builder.py` is a useful existing implementation pattern:

- fail closed;
- explicit required fields;
- sidecar requirements;
- content-addressed manifest concepts;
- immutable output artifacts;
- `REHEARSAL_ONLY` marking;
- no sealed-test access;
- no silent source repair.

Its current MVP constraints such as a small symbol count or limited calendar span are **implementation-stage scope constraints**, not eternal constitutional requirements.

The Constitution freezes the governance pattern, not one temporary number.

---

## 3.4 `FORMAL_RESEARCH`

Use when the dataset satisfies the data requirements necessary for the intended formal research claim.

Formal eligibility requires, as applicable:

- known and versioned source semantics;
- point-in-time correctness;
- reproducible provenance;
- valid time semantics;
- appropriate universe history;
- required tradability history;
- required corporate-action treatment;
- quality gates;
- manifest identity;
- authorization for the intended use;
- explicit limitations.

Formal eligibility is claim-relative.

A dataset may be formally eligible for daily-factor research while remaining ineligible for intraday microstructure research.

---

## 3.5 Eligibility class does not replace dataset role

The following is invalid:

```text
FORMAL_RESEARCH
therefore
SEALED_TEST may be inspected freely
```

The correct model is two-dimensional:

```text
Data Eligibility Class
        +
Research Role
        =
Allowed Use
```

Example:

```text
Eligibility: FORMAL_RESEARCH
Role: SEALED_TEST
Access: Restricted by validation governance
```

---

# 4. Point-in-Time Discipline

Point-in-time correctness is a constitutional requirement.

The central test is:

> **At historical decision time T, could the system actually have possessed the exact information used by the research process, in the form and state in which it was used?**

If the answer is unknown, the data cannot be assumed PIT-correct.

---

## 4.1 Point-in-time applies beyond price

PIT requirements may apply to:

- bars;
- ticks;
- order book;
- corporate actions;
- adjustment factors;
- listing status;
- ST status;
- suspension;
- price-limit rules;
- previous close;
- index membership;
- ETF constituents;
- industry membership;
- theme membership;
- ETF shares;
- financial statements;
- estimates;
- announcements;
- policy documents;
- event classifications;
- data revisions.

---

## 4.2 Historical truth and current truth are different objects

The project must not use:

```text
Current State
```

as a substitute for:

```text
State Known at Historical Time T
```

Examples of prohibited backfill by current truth:

- today's ST status applied to the past;
- today's industry classification applied to historical dates;
- today's surviving stock list used as the historical candidate universe;
- the latest restated financial value treated as originally published data;
- current theme membership copied backward without an as-of rule.

---

# 5. Canonical Time Semantics

Time is a first-class data dimension.

Different timestamps answer different questions and must not be collapsed merely because one datetime column is easier to use.

Relevant concepts may include:

```text
source_event_time
source_period_start
source_period_end
provider_timestamp
source_publish_time
retrieved_at
available_at
finalized_at
effective_at
revised_at
decision_time
execution_eligible_time
```

Not every data type requires every timestamp.

Every data type must define the timestamps necessary to reconstruct historical availability.

---

## 5.1 `source_event_time`

The time when the underlying market or business event occurred.

Examples:

- trade time;
- order-book snapshot time;
- announcement release time;
- policy publication time.

---

## 5.2 `source_period_start` and `source_period_end`

For aggregated observations, the covered interval must be explicit where relevant.

A five-minute bar labeled `09:35` may mean:

- interval start;
- interval end;
- provider-defined bucket label.

The project must not guess.

---

## 5.3 `source_publish_time`

The time the source published the information.

This is especially important for:

- financial reports;
- announcements;
- official statistics;
- policy documents;
- index changes.

---

## 5.4 `retrieved_at`

The time the project obtained the artifact.

`retrieved_at` does not prove `available_at`.

A historical file downloaded today may contain information that was available earlier, later, or revised.

---

## 5.5 `available_at`

The earliest time the project considers the information usable by a historical decision process under the defined contract.

This may depend on:

- provider latency;
- publication time;
- bar finalization;
- system ingestion policy;
- safety buffer.

---

## 5.6 `finalized_at`

The time after which an observation is considered complete under the data contract.

Historical existence alone does not prove historical finalization.

---

## 5.7 `effective_at`

The time a rule, classification or corporate action becomes effective.

Publication time and effective time may differ.

Both may matter.

---

## 5.8 `revised_at`

The time a previously published value was corrected or restated.

The project must be able to distinguish:

```text
Value known at T
```

from:

```text
Latest revised value
```

when the research claim requires it.

---

# 6. Bar Data Constitution

Bar data is foundational but easy to misuse.

A canonical bar contract must define, as applicable:

```text
symbol
interval
interval_start
interval_end
timestamp_label_semantics
timezone
open
high
low
close
volume
amount
bar_final
available_at
source
source_artifact_id
adjustment_view
schema_version
```

---

## 6.1 Bar finalization is explicit

A bar must not be treated as final because:

- the file is historical;
- the timestamp is in the past;
- the provider returned one row;
- the current wall clock is later than the bar.

The project needs an explicit finalization contract or provider evidence.

For formal historical intraday research, the system must be able to determine:

- the interval represented;
- when the interval closed;
- when the final value became available;
- whether the provider can later revise the bar;
- how revisions are handled.

---

## 6.2 Closed-bar research must use closed bars

If a feature contract states:

```text
closed_bars_only = true
```

then any use of an unfinished bar is a contract violation.

A current-session dashboard may intentionally display partial bars.

That is a different data object and must be labeled accordingly.

---

## 6.3 Calendar and session alignment are mandatory

A-share bar validation must account for the applicable trading calendar and session structure.

The data model must be capable of representing:

- trading date;
- session boundaries;
- morning close;
- afternoon open;
- session close;
- holidays;
- exceptional closures where applicable.

A generic continuous-clock resample must not silently manufacture bars across non-trading intervals.

---

## 6.4 `volume`, `amount` and `VWAP` semantics must be auditable

The project must define units and aggregation rules.

If `VWAP` is derived as:

```text
amount / volume
```

then:

- units must be compatible;
- the transformation must be explicit;
- the source of `amount` and `volume` must be known;
- provider-specific scaling must be normalized.

A field named `vwap` must not be populated with an unrelated price proxy.

---

# 7. Raw, Normalized, Canonical and Derived Data

The project distinguishes logical data zones.

The exact physical directory structure may evolve.

The logical responsibilities may not be collapsed.

```text
Raw / Source Artifacts
        ↓
Normalized Provider Data
        ↓
Canonical PIT Data
        ↓
Research Datasets
        ↓
Derived Features / Labels / Model Inputs
```

---

## 7.1 Raw / Source Artifacts

Purpose:

- preserve what was actually received;
- support audit;
- support re-normalization;
- support provider dispute investigation.

Raw data should not be modified in place.

Where licensing prevents storage or redistribution, the project must preserve sufficient metadata and secure references to reconstruct the authorized acquisition process.

---

## 7.2 Normalized Provider Data

Purpose:

- stable typing;
- stable identifiers;
- normalized units;
- provider semantics retained.

Provider-specific metadata must not be discarded if it is required to understand the observation.

---

## 7.3 Canonical PIT Data

Purpose:

- establish project-wide semantics;
- resolve explicit source precedence;
- support historical as-of queries;
- support reproducible research.

Canonicalization must be deterministic and versioned.

---

## 7.4 Derived Research Data

Examples:

- labels;
- returns;
- feature frames;
- cross-sectional ranks;
- regime assignments;
- model-ready matrices.

Derived data must retain lineage back to canonical inputs and transformation identity.

The detailed feature lineage model belongs to `05-Factor-Constitution.md`.

---

# 8. Immutability and Content Identity

## 8.1 Research artifacts must not be silently overwritten

The project prefers immutable or append-only behavior for formal research data artifacts.

The following is prohibited:

```text
Run experiment using dataset X
        ↓
Replace files inside X
        ↓
Keep the same dataset name
        ↓
Claim reproducibility
```

A content-changing correction creates:

- a new content identity;
- a new dataset version;
- or an explicit revision record.

---

## 8.2 Content hashes are evidence, not decoration

Where feasible, manifests should record hashes for result-affecting files.

A hash can help answer:

> “Are these the same bytes?”

It does not answer:

> “Are these semantics correct?”

Both identity and semantic validation are required.

---

## 8.3 File names are not identities

The following is insufficient:

```text
final_data.csv
latest.parquet
v2_fixed.csv
```

A formal dataset must have a stable manifest identity independent of descriptive file names.

---

# 9. Dataset Manifest Constitution

Every formal or rehearsal dataset must have a manifest sufficient to identify the data used by an experiment.

A manifest should record, as applicable:

```text
Dataset ID
Dataset Version
Eligibility Class
Intended Scope
Build Timestamp
Builder Version
Source Providers
Source Products / Endpoints
Source Artifact References
Source Artifact Hashes
Schema Versions
Symbol Coverage
Time Coverage
Frequency
Timezone
Timestamp Semantics
Finalization Policy
Adjustment Policy
Corporate-Action Inputs
Universe Version / Reference
Eligibility Sidecar Reference
Industry / Theme Sidecar Reference
Market Context Sidecar Reference
Calendar Version
Quality Report Reference
Known Limitations
License / Access Classification
Parent Dataset / Revision Reference
```

The exact serialized schema belongs to a lower-level specification.

The constitutional requirement is that result-affecting data identity be reconstructable.

---

## 9.1 Dataset identity must include sidecars that affect results

A price file plus a changed universe sidecar is a different effective dataset.

A price file plus a changed corporate-action file is a different effective dataset.

A price file plus a changed industry mapping may be a different effective dataset if the research consumes that mapping.

The manifest must reflect result-affecting dependencies.

---

## 9.2 A manifest is not a quality certificate by itself

A complete manifest may describe a poor dataset accurately.

The project requires both:

```text
Identity
+
Eligibility / Quality Decision
```

---

# 10. Data Quality Constitution

Data quality must be evaluated by dimensions rather than hidden inside one opaque total score.

Relevant dimensions may include:

```text
Schema Validity
Completeness
Uniqueness
Range Validity
Cross-Field Consistency
Temporal Consistency
Calendar Consistency
Finalization Integrity
PIT Integrity
Universe Coverage
Sidecar Coverage
Freshness
Revision Stability
Provider Consistency
Provenance Completeness
Authorization Status
```

---

## 10.1 Blocking failures and warnings are different

A quality report should distinguish:

```text
BLOCKING
WARNING
INFORMATIONAL
```

Examples of possible blocking failures for a claim may include:

- required PIT universe missing;
- ambiguous timestamp semantics;
- unfinished bars where closed bars are required;
- duplicate primary keys;
- impossible price relationships;
- missing required corporate-action history;
- absent required license or authorization evidence;
- incomplete sealed-test isolation.

A single aggregate quality score must not hide a critical blocker.

---

## 10.2 Quality rules are versioned

Changing a quality gate may change which records or datasets become eligible.

Therefore quality-rule versions are part of research reproducibility.

---

## 10.3 Data Builder behavior is fail closed

When a formal dataset builder encounters a critical unresolved requirement, it must reject the build or downgrade eligibility explicitly.

The builder must not:

- invent `bar_final`;
- fill PIT universe from today's list;
- assume missing ST status is false;
- assume missing suspension status is false;
- synthesize a missing historical industry map from current classification;
- convert unknown adjustment status into `POINT_IN_TIME_ADJUSTED`;
- fabricate provider provenance.

---

# 11. Missing Data Policy

Missingness has meaning.

The project distinguishes:

```text
Not Applicable
Not Available
Not Yet Available at Decision Time
Provider Missing
Ingestion Failure
Rejected by Quality Gate
Intentionally Excluded
Unknown
```

These states must not be collapsed into the same default number.

---

## 11.1 Critical missing data blocks authority

If a field is necessary to establish the validity of the research claim, missingness must block or downgrade the claim.

Examples may include:

- unknown historical eligibility for a universe study;
- missing bar finalization for a closed-bar intraday model;
- missing publication time for a point-in-time fundamental feature;
- missing execution eligibility for a realistic fill claim.

---

## 11.2 Non-critical missing data may be handled explicitly

Permitted approaches may include:

- null preservation;
- missing indicator;
- deterministic exclusion;
- model-specific imputation;
- last-known-value rules where semantically valid.

Any imputation that affects research must be:

- documented;
- versioned;
- reproducible;
- evaluated for side effects.

---

## 11.3 Imputation must not fabricate historical truth

The project rejects:

```text
Missing historical ST status
        ↓
Fill False
```

when the historical state is required for eligibility.

Likewise:

```text
Missing theme membership
        ↓
Use today's theme membership
```

is not imputation.

It is temporal leakage.

---

# 12. Provider Conflict Policy

Multiple sources may disagree.

Disagreement must be observable.

The system must not silently select whichever value is most convenient for the current experiment.

---

## 12.1 Preserve source-specific observations

Before canonical resolution, provider-specific values should remain distinguishable where possible.

---

## 12.2 Canonical precedence must be deterministic

If the project selects one source as authoritative for a field or period, the precedence rule must be explicit and versioned.

Examples may include:

- official source over derived source;
- licensed archive over public scrape;
- primary corporate-action source over secondary aggregation.

The correct precedence is domain-specific.

---

## 12.3 Majority vote is not automatically truth

Three scraped sources agreeing does not necessarily outweigh one authoritative source.

Provider quality, semantics and lineage matter.

---

## 12.4 Material conflicts create a data-quality event

A conflict affecting research results should be:

- logged;
- quantified;
- investigated;
- included in quality reporting;
- capable of invalidating affected datasets.

---

# 13. Price Adjustment and Corporate Actions

Price adjustment is a major leakage risk.

The project must distinguish at least:

```text
Raw / Unadjusted Prices
Current Back-Adjusted Display View
Point-in-Time Adjusted Research View
Execution Prices
```

These views are not interchangeable.

---

## 13.1 Raw prices are preserved

Execution simulation should generally be able to reference actual historical market prices under the execution contract.

Raw observations should not be destroyed by adjustment.

---

## 13.2 Point-in-time adjustment must be explicit

A formal PIT-adjusted series must define:

- the corporate-action events used;
- when those events became known;
- the adjustment method;
- the effective date;
- whether the transformation uses future events;
- the intended research use.

A common back-adjusted historical chart generated with all future corporate actions is not automatically a PIT feature input.

---

## 13.3 Corporate actions are first-class data

Relevant events may include:

- cash dividends;
- stock dividends;
- splits;
- rights issues;
- other capital changes.

The data model should preserve, as applicable:

```text
Announcement Time
Record Date
Ex-Date
Payment / Effective Date
Revision State
Source
```

---

## 13.4 Mixed adjustment views are prohibited

The following is invalid unless explicitly designed and justified:

```text
Feature computed on adjusted price
+
execution simulated on an inconsistent transformed price
+
corporate action cash flow also added separately
```

The project must prevent double counting of corporate-action effects.

---

# 14. Security Master and Identifier Constitution

A security identifier is not merely a string.

The project must be able to distinguish historical instruments correctly.

A security master may need to represent:

- canonical symbol;
- exchange;
- security type;
- listing date;
- delisting date;
- board;
- identifier changes;
- ETF versus stock;
- share class where relevant.

Symbol normalization must be versioned.

A historical research join must not assume that a current ticker string alone uniquely identifies all historical semantics.

---

# 15. Tradable Universe Constitution

Candidate Discovery is cross-sectional.

Therefore the historical search space is part of the model.

The project requires a point-in-time universe contract.

For each decision time or applicable date, the system should be able to determine whether a security belongs to the candidate population under the research rule.

Relevant inputs may include:

- listed status;
- listing age;
- delisting state;
- ST or risk-warning state;
- suspension;
- liquidity;
- data availability;
- board-specific rules;
- strategy-specific exclusions.

---

## 15.1 Universe membership and tradability are related but distinct

A security may belong to a research universe but be temporarily untradable.

The system should distinguish:

```text
Universe Membership
Eligibility
Tradability
Execution Feasibility
```

The exact strategy and execution policies belong elsewhere.

The data layer owns the historical facts required to evaluate them.

---

## 15.2 Survivorship bias is prohibited

The project must not construct historical candidate research using only today's surviving securities when the target claim concerns the historical market.

---

## 15.3 Universe snapshots must be reproducible

A formal cross-sectional experiment should be able to reconstruct:

```text
Which securities were considered at T?
Why was each included?
Why was each excluded?
Which data version supported that answer?
```

---

# 16. Historical Trading Eligibility Sidecars

The Data Platform should support historical sidecars required for A-share trading constraints.

Depending on the research scope, relevant fields may include:

```text
is_suspended
is_st
prev_close
limit_up_price
limit_down_price
limit_regime
trading_session_state
```

Additional fields may be introduced by later specifications.

---

## 16.1 Sidecars must be historical facts, not current-state guesses

The system must not fill:

```text
is_st = false
is_suspended = false
```

merely because the source did not provide the fields.

---

## 16.2 Limit-price regimes are versioned market rules

A-share price-limit rules can vary by:

- board;
- security type;
- date;
- special status.

Historical simulation must use the applicable historical rule, not a timeless hard-coded assumption.

The Execution System owns how the rule affects fills.

The Data Platform owns the historical facts and rule-version inputs required to make that decision.

---

# 17. Market, Index and Benchmark Data

Market context is a first-class input to Market Regime Alpha.

Market-side data may include:

- broad indices;
- style indices;
- sector indices;
- market breadth;
- total turnover;
- advance/decline structure;
- limit-up/limit-down structure;
- volatility measures;
- cross-sectional dispersion.

Each field must have:

- source;
- construction method if derived;
- decision-time availability;
- universe basis;
- version.

A breadth measure built from today's universe cannot be treated as historical PIT breadth.

---

# 18. Industry and Theme Data

Industry and theme information is temporally dynamic.

The project must distinguish:

```text
Classification Definition
Membership
Effective Period
Available-at Time
Source
Version
```

---

## 18.1 Industry mapping must be as-of aware

Historical sector research should not silently use current industry membership.

A formal mapping should support, as applicable:

```text
symbol
classification_system
classification_version
industry_id
valid_from
valid_to
available_at
source
```

---

## 18.2 Theme mapping requires stronger governance than free-form labels

Themes may be:

- overlapping;
- narrative-driven;
- vendor-defined;
- revised retrospectively;
- short-lived.

A theme dataset must specify:

- taxonomy owner;
- membership rule;
- effective time;
- source;
- revision policy;
- whether membership is contemporaneous or retrospectively curated.

Retrospective thematic curation may be useful for descriptive analysis.

It is not automatically valid for point-in-time candidate research.

---

## 18.3 LLM-generated theme classifications are derived data

An AI or LLM may assist in classifying announcements or themes.

The result must be treated as a versioned derived artifact with:

- source-document identity;
- model identity;
- prompt or extraction contract where relevant;
- generation time;
- confidence or review state;
- correction history.

The LLM output is not the original source truth.

---

# 19. ETF Data Constitution

ETF research requires more than ETF price bars when the hypothesis concerns capital flow or underlying exposure.

Relevant domains may include:

- ETF price and volume;
- NAV / IOPV where applicable;
- shares outstanding;
- creation/redemption-related data;
- AUM;
- premium/discount;
- constituent mapping;
- index tracking relationship;
- fund-flow measures.

---

## 19.1 Price momentum is not ETF fund flow

The project prohibits the semantic shortcut:

```text
ETF price or turnover increased
therefore
ETF received net fund inflow
```

A bar-derived proxy may be useful.

It must be labeled as a proxy.

Real ETF flow claims require appropriate underlying data and a defined calculation.

---

## 19.2 ETF shares require point-in-time semantics

If ETF shares outstanding are used to infer flows, the dataset must define:

- observation frequency;
- publication time;
- revision behavior;
- effective date;
- calculation method.

---

## 19.3 ETF constituents and index membership are time-varying

Historical ETF or index exposure research must not use current constituent lists unless the claim explicitly concerns current composition.

---

# 20. Capital Flow Constitution

The project distinguishes:

```text
Observed / Vendor-Defined Flow Data
Order-Book or Trade-Derived Flow Measures
Bar-Derived Flow Proxies
Heuristic Flow Scores
```

These are different information classes.

---

## 20.1 Real flow and proxy flow must not share the same name

Examples of potentially different objects:

```text
Vendor Main-Fund Net Inflow
Large-Order Imbalance
Order-Book Imbalance
Active Buy/Sell Classification
ETF Share Change
OHLCV-Based Capital-Flow Proxy
```

The field name and metadata must preserve the distinction.

---

## 20.2 Vendor definitions are part of the data contract

A provider may define “main fund,” “large order,” or “net inflow” using proprietary rules.

The project must record the provider and definition version where available.

The same label from two vendors must not be assumed equivalent.

---

## 20.3 Bar-derived proxies remain useful but must be honest

The current Legacy system contains capital-flow-like estimates derived from price and volume.

These may remain valid research features.

They must not be promoted semantically into independent real-flow evidence without appropriate data.

This distinction is important for the project's `No Double Counting` principle.

---

# 21. Level 1, Level 2 and Microstructure Data

Level 1 and Level 2 data may provide additional information for certain strategies.

They are not mandatory for the entire project.

The required data depth is hypothesis-specific.

---

## 21.1 Microstructure data requires precise semantics

Relevant contracts may include:

- snapshot frequency;
- event ordering;
- exchange timestamp;
- local receipt time;
- bid/ask depth;
- cancellations;
- trade direction methodology;
- auction periods;
- packet loss or gaps;
- provider normalization.

---

## 21.2 Higher frequency does not imply higher research quality

A Level 2 dataset with poor historical reproducibility or ambiguous event ordering may be less useful for formal research than a lower-frequency dataset with strong PIT and provenance guarantees.

---

## 21.3 Microstructure coverage must match the claim

A model trained only on a subset of symbols or periods with Level 2 availability must identify that population honestly.

---

# 22. Fundamental Data Constitution

Fundamental data is governed by historical availability, not only fiscal period.

A canonical fundamental observation may need to distinguish:

```text
report_period
announcement_time
first_available_at
value
currency
unit
consolidation_scope
revision / restatement
source
```

---

## 22.1 Report period is not availability time

A value for the quarter ending March 31 was not necessarily knowable on March 31.

Historical research must use the publication or availability timeline required by the feature contract.

---

## 22.2 Restatements require version awareness

The latest restated value may be valid for current analysis.

It may be invalid as a substitute for the value known at a historical decision time.

---

## 22.3 Technical information must not be hidden inside fundamental data

The current Legacy pattern where price or moving-average behavior modifies a field named `fundamental_score` is not a valid data-family contract.

Market-derived information belongs to its correct information family.

The Factor Constitution will govern how families are combined.

---

# 23. Event, Announcement and Policy Data

Policy and event-driven research is a core A-share research domain.

Such data requires explicit temporal semantics.

Relevant fields may include:

```text
source_document_id
publisher
published_at
effective_at
event_type
entity_mapping
original_text_reference
extraction_version
classification_version
revision_state
```

---

## 23.1 Publication time and effective time are different

A policy may be:

- announced at one time;
- effective at another time;
- interpreted by the market over a longer period.

The data contract should preserve these distinctions.

---

## 23.2 Knowledge extracted after the event must not be backdated

A later analyst summary, LLM classification or human interpretation cannot be treated as though it were available at the original publication time unless the research explicitly models that delayed availability.

---

## 23.3 Entity mapping must be versioned

Mapping an event to:

- industries;
- themes;
- stocks;
- ETFs;

is a derived process.

The mapping rule, version and availability time may affect results.

---

# 24. Labels and Future Data

Future data is allowed for constructing labels.

It is not allowed to leak into features or decision-time eligibility.

The canonical relationship is:

```text
Information Set Available at Decision Time
        ↓
Decision Time
        ↓
Next Eligible Execution Time
        ↓
Future Label Window
```

Labels must define:

- reference time;
- reference price;
- horizon;
- event;
- missing-label policy;
- suspension and limit-state treatment where relevant.

Target contracts belong to the Research and Validation systems.

The Data Platform must provide the temporal integrity needed to construct them correctly.

---

# 25. Dataset Building Pipeline

The canonical formal dataset-building flow is:

```text
Approved Source Scope
        ↓
Acquire / Reference Source Artifacts
        ↓
Validate Source Semantics
        ↓
Normalize Without Inventing Truth
        ↓
Attach PIT and Reference Sidecars
        ↓
Run Quality Gates
        ↓
Build Immutable Dataset Artifact
        ↓
Generate Manifest
        ↓
Generate Quality Report
        ↓
Assign Eligibility Class
        ↓
Register Dataset Identity
```

---

## 25.1 Dataset Builder must not opportunistically fetch unknown live data

A reproducible build should consume identified inputs.

A historical replay must not call a “latest” endpoint to fill missing historical fields during the run.

---

## 25.2 Dataset Builder must not silently repair semantics

Permitted deterministic transforms may include:

- unit normalization;
- type conversion;
- known symbol mapping;
- explicit timestamp conversion;
- declared resampling.

Unresolved semantic gaps must block or downgrade the build.

---

## 25.3 Build output is an artifact, not a mutable working directory

Formal and rehearsal artifacts should be non-overwritable or versioned so that an experiment can refer to a stable identity.

The current repository's `write_rehearsal_dataset_artifact()` pattern is directionally correct because it refuses accidental overwrite and marks rehearsal-only status.

---

# 26. Sidecar Constitution

A price table should not be forced to contain every historical fact.

The project may use sidecars for orthogonal domains such as:

```text
Trading Calendar
Security Master
PIT Universe
Trading Eligibility
Corporate Actions
Adjustment Factors
Industry Mapping
Theme Mapping
ETF Mapping
Market Context
Event / Policy Data
```

---

## 26.1 Sidecars are first-class dataset dependencies

If a sidecar changes experiment results, it must be included in dataset or experiment identity.

---

## 26.2 Sidecar joins must be temporally defined

A join rule must specify whether it uses:

- exact timestamp;
- as-of timestamp;
- valid-time interval;
- trade date;
- publication time.

Ambiguous joins are a leakage risk.

---

## 26.3 Coverage is measurable

A dataset builder should be able to report:

- expected sidecar coverage;
- actual coverage;
- missing keys;
- stale mappings;
- invalid time overlaps.

---

# 27. Current Repository Data Posture

This Constitution is informed by the project's current data-source capability audit and existing implementation.

The current posture is a **baseline**, not a permanent provider ranking.

Any source may be reclassified after new evidence, contracts, adapters or audits.

---

## 27.1 Current free and cached sources

The current project audit has established that existing free or cached sources are useful for development and exploratory work but do not, by themselves, prove all requirements for formal intraday research.

Known gaps include, depending on source and artifact:

- explicit `bar_final` provenance;
- interval-label proof;
- minute-level PIT adjustment;
- PIT universe;
- historical ST and suspension state;
- historical limit-price state;
- historical industry/theme as-of mapping;
- complete market sidecars;
- formal licensing and reproducibility guarantees.

Therefore these sources must not be automatically upgraded to formal status.

---

## 27.2 Current source-specific baseline

The current audit posture is approximately:

### Tencent cache / public Tencent access

Useful for:

- local exploratory research;
- active-session observation;
- interface and adapter work.

Not currently sufficient by itself to prove formal PIT intraday research requirements.

### EastMoney / AKShare-derived access

Useful for:

- exploration;
- supplemental access;
- prototype work.

Not currently approved as the formal primary source for the project's required PIT intraday dataset.

### BaoStock

Useful for:

- historical backfill;
- source proof-of-concept;
- adapter testing.

Historical availability alone does not prove bar-finalization, PIT adjustment or full sidecar completeness.

The current BaoStock proof-of-concept demonstrates access and pipeline integration, not formal source promotion.

### Tushare Pro

Potentially useful as:

- a conditional auxiliary source;
- selected reference data;
- selected index, ETF, calendar or security data;
- minute data where the required permission and semantics are verified.

Provider capability must be validated per product and field.

One product's daily adjustment semantics must not be generalized automatically to minute-level PIT adjustment.

### QMT / broker archive

A candidate source category for market-price history where:

- historical depth;
- timestamp semantics;
- finalization;
- authorization;
- revision behavior

can be verified.

A broker price archive is not assumed to provide every required PIT sidecar.

### Commercial PIT data providers

A recommended source category for formal research where contracts and data dictionaries can support:

- historical coverage;
- PIT semantics;
- corporate actions;
- universe history;
- reference data;
- licensed reproducibility.

The Constitution does not mandate one vendor.

Provider selection remains an evidence, capability, cost and authorization decision.

---

## 27.3 Existing raw datasets remain honestly classified

The currently audited local bar files primarily contain fields such as:

```text
symbol
timestamp
open
high
low
close
volume
amount
source_freq
```

Their usefulness is real.

Their missing formal evidence must also remain visible.

They must not be upgraded by adding default columns that falsely imply PIT completeness.

---

## 27.4 Existing formal dataset builder is a governance asset

The current `formal_dataset_builder.py` establishes several valuable patterns:

- explicit required fields;
- explicit PIT-adjustment requirement for its intended rehearsal scope;
- explicit `bar_final` requirement;
- sidecar coverage validation;
- calendar validation;
- immutable artifact writing;
- manifest and quality artifacts;
- fail-closed behavior;
- no source-specific guessing;
- no sealed-test access.

The future Data Platform should generalize these principles.

It should not preserve every current MVP limitation as a permanent universal rule.

---

# 28. Data Provider Qualification

A provider should have a capability profile rather than a binary reputation label.

A provider profile may evaluate:

```text
Domain
Product
Fields
Frequency
Historical Depth
Coverage
Timestamp Semantics
Finalization Semantics
Revision Policy
PIT Support
Corporate-Action Support
Universe / Reference Support
Access Method
Rate Limits
SLA
Licensing
Redistribution Rights
Cost
Operational Reliability
Known Gaps
Audit Date
```

---

## 28.1 Provider qualification is field- and use-specific

A provider may be:

- strong for daily fundamentals;
- weak for historical minute bars;
- useful for calendars;
- insufficient for PIT industry history.

The project must avoid universal labels such as:

```text
Provider X is good for everything.
```

---

## 28.2 Provider changes require review

Changes such as:

- endpoint migration;
- schema change;
- data dictionary change;
- access-level change;
- revision-policy change;
- vendor merger;
- licensing change

may affect eligibility and require re-audit.

---

# 29. Licensing, Authorization and Public Repository Safety

Data rights are part of data governance.

A technically reproducible dataset may still be unauthorized for storage, redistribution or public publication.

---

## 29.1 The public GitHub repository must not become an unauthorized data redistribution channel

Licensed or restricted raw data must not be committed to the public repository unless the license explicitly permits it.

The project may instead commit:

- schemas;
- manifests without restricted payloads;
- hashes;
- synthetic fixtures;
- adapters;
- quality reports that do not expose restricted content;
- instructions for authorized local acquisition.

---

## 29.2 License context is part of reproducibility

A dataset manifest or registry should be capable of identifying access requirements sufficiently to explain why another environment may not be able to reconstruct the same dataset without equivalent authorization.

---

## 29.3 Research convenience does not override terms of use

Agents and developers must not bypass provider restrictions merely to make a pipeline run.

---

# 30. Data Revisions and Backfills

Historical data can change.

The project must distinguish:

```text
Original Artifact
Corrected Artifact
Backfilled Artifact
Restated Artifact
Canonical Revision
```

---

## 30.1 Backfills change coverage and possibly research meaning

Adding earlier history or filling missing records may change:

- sample composition;
- feature warm-up;
- model training;
- universe coverage;
- performance.

A material backfill requires a new dataset identity or revision record.

---

## 30.2 Corrections must not erase auditability

When a data error is corrected, the project should preserve:

- what was wrong;
- which datasets were affected;
- the corrected version;
- the time of correction;
- which experiments may be invalidated.

---

## 30.3 “Latest corrected history” is not always PIT history

A corrected historical value may be appropriate for some current analyses.

It may be inappropriate for reconstructing what a model could have known at historical time T.

The intended use must be explicit.

---

# 31. Data Incidents and Research Invalidation

A data incident is any event that may compromise data identity, semantics, availability or correctness.

Examples:

- provider changed timestamp labels;
- duplicate bars appeared;
- corporate-action adjustment was wrong;
- universe history was built from current membership;
- an API silently changed units;
- a source returned partial history;
- a supposedly sealed dataset was accessed improperly;
- a licensed file was accidentally overwritten;
- a mapping join created future leakage.

---

## 31.1 Data incidents can invalidate research

The project must not protect an attractive result from data review.

If a data incident affects the claim, the affected result may need to become:

```text
Suspect
Quarantined
Invalidated
Rebuilt
Re-evaluated
```

---

## 31.2 Invalidation must be traceable

The project should be able to identify:

- affected dataset IDs;
- affected experiment IDs;
- affected model artifacts;
- affected reports;
- remediation status.

---

# 32. Data Observability

A mature Data Platform should expose operational evidence such as:

- ingestion success and failure;
- latency;
- freshness;
- row counts;
- coverage;
- schema drift;
- duplicate rates;
- missingness;
- sidecar coverage;
- provider conflict rates;
- revision counts;
- quality-gate outcomes.

Operational observability does not replace research validation.

It ensures that data failures can be detected before they silently affect research or decisions.

---

# 33. Candidate Discovery Data Requirements

Candidate Discovery is the current first strategic priority.

Its data requirements are therefore especially important.

Formal cross-sectional candidate research may require, depending on target:

```text
PIT Tradable Universe
Synchronized Decision-Time Observations
Comparable Price / Volume Data
Liquidity and Eligibility Data
Corporate-Action Handling
Market Context
ETF / Industry / Theme Context
Cross-Sectional Coverage
Benchmark References
Execution-Relevant Eligibility
```

---

## 33.1 Cross-sectional comparability is a data problem

A ranking model cannot be trusted merely because every symbol has a number.

The system must examine:

- inconsistent history depth;
- stale symbols;
- missing bars;
- different adjustment states;
- coverage bias;
- provider-specific gaps;
- universe drift.

---

## 33.2 Decision-time snapshots must be reconstructable

For a candidate scan at time T, the system should be able to reconstruct:

```text
Universe at T
Data available at T
Feature input availability at T
Market / ETF / Theme context available at T
Eligibility at T
```

The feature and model layers build on this substrate.

---

# 34. Position Lifecycle Data Requirements

Position Lifecycle research consumes both market information and state.

The data layer must support the historical facts needed to reconstruct:

- market context;
- candidate/continuation inputs;
- price and volume evolution;
- tradability;
- corporate actions;
- theme and ETF context;
- risk observations;
- alternative opportunity set where rotation is studied.

Position state itself is owned by the Position Lifecycle or Portfolio System according to the Architecture Blueprint.

The Data Platform provides the external observations required to evaluate state transitions.

---

# 35. Execution-Related Data Boundary

The Data Platform and Execution System must remain separate.

The Data Platform owns historical facts such as:

- previous close;
- suspension state;
- limit prices;
- session times;
- market observations;
- corporate actions.

The Execution System owns the policy that converts those facts into:

- executable or blocked;
- next eligible time;
- fill assumptions;
- slippage;
- transaction costs;
- partial fill behavior.

The Data Platform must not silently embed strategy-specific fill assumptions into canonical observations.

---

# 36. Research Reproducibility and Data Access

A reproducible experiment should not depend on an uncontrolled query such as:

```text
fetch latest history from provider
```

unless the provider snapshot and retrieval result are themselves part of the experiment identity.

Preferred patterns include:

```text
Experiment
    ↓ references
Dataset ID
    ↓ references
Manifest
    ↓ references
Immutable / Versioned Artifacts
```

---

## 36.1 Query reproducibility and artifact reproducibility are different

An API request can be reproducible as code while its returned data changes over time.

Therefore the project should distinguish:

```text
Reproducible Query
```

from:

```text
Reproducible Dataset Content
```

---

## 36.2 External data that cannot be redistributed may still be reproducible under authorization

The project may preserve:

- provider contract identity;
- acquisition parameters;
- hashes;
- transformation version;
- secure artifact references.

The public repository need not contain restricted bytes.

---

# 37. Data and Sealed Evaluation

Sealed evaluation is primarily governed by `07-Validation-Constitution.md`.

This Data Constitution establishes several supporting rules.

---

## 37.1 Sealed data role must be explicit

A dataset or partition assigned to sealed evaluation must have access state that can be audited.

---

## 37.2 Data Builder must not select sealed test based on observed performance

Dataset construction must not repeatedly inspect candidate sealed partitions until one produces a favorable result.

---

## 37.3 Data corrections affecting sealed evaluation require governance

If a genuine data defect is discovered in a sealed dataset, correction may be necessary.

The event must be documented because the correction may alter the integrity of prior sealed evaluation.

---

# 38. Data Governance for Agents

Agents may assist with:

- adapter implementation;
- schema generation;
- quality checks;
- manifest construction;
- anomaly detection;
- documentation;
- provider capability review.

Agents must not silently:

- switch providers;
- change timestamp meaning;
- fill critical missing PIT fields;
- access sealed data;
- reclassify exploratory data as formal;
- overwrite formal artifacts;
- commit restricted vendor data publicly;
- change adjustment policy;
- replace historical mappings with current values;
- reinterpret proxy flow as real flow.

Any agent-driven data change that affects research identity must be traceable.

---

# 39. Data Architecture Responsibilities

The target Data Platform should separate responsibilities such as:

```text
Provider Registry
Provider Adapters
Source Artifact Registry
Schema Registry
Canonicalization
PIT Resolution
Reference / Sidecar Management
Dataset Builder
Quality Gates
Manifest Registry
Eligibility Classification
Data Incident Management
```

One giant provider or data-manager module must not become the new God Object.

---

## 39.1 Provider Adapter owns provider translation

It does not own:

- feature logic;
- candidate ranking;
- strategy decisions.

---

## 39.2 Canonicalizer owns stable internal semantics

It does not invent unknown historical truth.

---

## 39.3 Dataset Builder owns controlled assembly

It does not choose model parameters based on performance.

---

## 39.4 Quality Gate owns eligibility checks

It does not rewrite critical data to make the gate pass.

---

## 39.5 Data Registry owns identity and status

It should make it possible to answer:

```text
What is this dataset?
Where did it come from?
What is it allowed to support?
Which experiments used it?
Has it been revised or invalidated?
```

---

# 40. Data Anti-Patterns

The following patterns are constitutionally prohibited or must remain explicitly exploratory.

---

## 40.1 “The API returned rows, therefore the dataset is formal”

Access is not evidence eligibility.

---

## 40.2 Inferring `bar_final` from historical age

Historical age does not prove original decision-time finalization semantics.

---

## 40.3 Using today's universe for historical cross-sectional research

This creates survivorship and eligibility bias.

---

## 40.4 Using current industry or theme membership in the past

This creates look-ahead or retrospective classification bias.

---

## 40.5 Filling unknown historical eligibility with permissive defaults

Examples:

```text
is_st = false
is_suspended = false
```

without evidence.

---

## 40.6 Mixing raw and adjusted prices without explicit view semantics

This can create leakage or double-count corporate actions.

---

## 40.7 Calling bar-derived flow proxy “real capital flow”

Different information classes must remain semantically distinct.

---

## 40.8 Silent provider switching

Changing the source while preserving dataset identity destroys reproducibility.

---

## 40.9 Overwriting dataset artifacts

A result cannot be reproduced if its underlying bytes silently change.

---

## 40.10 Live fetch during historical replay

A replay must not query uncontrolled current data to repair historical gaps.

---

## 40.11 One opaque data-quality score

A high average quality score must not hide a critical PIT or provenance failure.

---

## 40.12 Treating a proof-of-concept source pull as source approval

Successful download proves access, not formal eligibility.

---

## 40.13 Treating a fixture-based rehearsal as Alpha evidence

A fixture may validate the pipeline.

It does not validate market predictiveness.

---

## 40.14 Committing restricted raw data to a public repository

Research convenience does not override licensing.

---

## 40.15 Retrospective data repair without version change

A corrected dataset must be identifiable as corrected.

---

# 41. Data Review Questions

Every serious data addition or dataset build should be reviewable through the following questions.

## Source

- Who produced the information?
- Which product, endpoint or artifact was used?
- What authorization governs its use?
- Can the source be reconstructed or referenced?

## Semantics

- What does each critical field mean?
- What are the units?
- What is the frequency?
- What does the timestamp label mean?

## Time

- When did the underlying event occur?
- When was the information published?
- When did it become available to the model?
- When was it final?
- Can it be revised?

## PIT

- Could this exact value have been known at decision time?
- Is current information being backfilled into the past?
- Are historical classifications and universe states preserved?

## Quality

- Are there blocking gaps?
- Are duplicates or impossible values present?
- Is sidecar coverage complete for the intended claim?
- Are provider conflicts visible?

## Adjustment

- Is the price view raw, back-adjusted or PIT-adjusted?
- Are corporate actions handled consistently?
- Could future corporate actions leak into historical features?

## Identity

- Is there a manifest?
- Are result-affecting inputs versioned or hashed?
- Can another experiment reference the same exact dataset?

## Eligibility

- Is the data unqualified, exploratory, rehearsal or formal?
- What claim is it eligible to support?
- What claims is it explicitly not eligible to support?

## Revision

- Has the provider or dataset changed?
- Were prior experiments affected?
- Is a new dataset identity required?

## Security / License

- May this data be stored?
- May it be committed publicly?
- May it be redistributed?

---

# 42. Minimum Formal Data Package

Before a dataset can support a formal research claim, it should have, at minimum, as applicable:

```text
1. Dataset Identity
2. Manifest
3. Source / Provider Identity
4. Source Semantics
5. Time and Availability Semantics
6. Schema Version
7. Adjustment Policy
8. Universe / Population Support
9. Required PIT Sidecars
10. Quality Report
11. Blocking-Failure Status
12. Known Limitations
13. Eligibility Classification
14. Authorization / License Context
15. Revision / Parent Identity
```

The exact field schema belongs to lower-level specifications.

The principle does not.

---

# 43. Relationship to Existing Project Assets

## 43.1 `data_sources/a_share_bars.py`

**Value:** multi-source access, normalization, current and historical retrieval helpers.  
**Constitutional interpretation:** provider access and normalization layer.  
**Required evolution:** preserve useful adapters while moving formal semantics, manifests, PIT and eligibility into the Data Platform.  
**Action:** **Adapt + Extract.**

---

## 43.2 `docs/Formal-Data-Source-Capability-Audit.md`

**Value:** existing capability audit that correctly distinguishes source access from PIT evidence.  
**Constitutional interpretation:** provider capability assessment under this Data Constitution.  
**Required evolution:** re-audit as providers, contracts and adapters change.  
**Action:** **Preserve + Update as evidence changes.**

---

## 43.3 `formal_dataset_builder.py`

**Value:** fail-closed rehearsal builder, sidecar checks, manifest generation, immutable artifact pattern.  
**Constitutional interpretation:** early implementation of formal Data Platform governance.  
**Required evolution:** generalize beyond the current MACD/rehearsal scope without weakening gates.  
**Action:** **Preserve design principles + Generalize.**

---

## 43.4 Existing local CSV / Parquet bar archives

**Value:** historical exploratory data and development utility.  
**Constitutional interpretation:** useful assets whose current eligibility is limited by missing PIT and provenance evidence.  
**Required evolution:** retain honestly; do not upgrade with fabricated defaults.  
**Action:** **Preserve + Classify accurately.**

---

## 43.5 Existing QMT / Tencent / BaoStock / Tushare adapters

**Value:** provider access and operational experimentation.  
**Constitutional interpretation:** adapters are not provider approval.  
**Required evolution:** evaluate each output through provider capability profiles and dataset eligibility gates.  
**Action:** **Preserve where useful + Audit per use case.**

---

# 44. Current Refoundation Data Constraints

Until explicitly changed by new evidence and a traceable decision, the following posture remains binding:

```text
Do not treat current free or cached bar data as formally qualified by default.
Do not infer PIT truth from missing fields.
Do not infer bar finalization from historical age.
Do not use today's universe or classification as historical truth.
Do not call bar-derived flow proxy real flow.
Do not treat a successful source POC as provider promotion.
Do not treat fixture rehearsal as Alpha evidence.
Do not access sealed evaluation merely to accelerate iteration.
Do not overwrite formal research data artifacts silently.
Do not commit restricted vendor data to the public repository without permission.
Do not let data convenience override the research claim.
```

The project may continue exploratory research with weaker data.

The evidence claim must remain bounded by the actual data eligibility.

---

# 45. Relationship to the Remaining Constitution

## `05-Factor-Constitution.md`

Will define:

- Feature Registry;
- factor identity;
- source-field lineage;
- information families;
- transformations;
- normalization;
- redundancy;
- IC / RankIC;
- incremental value;
- factor promotion.

The Factor Constitution consumes data governed by this Data Constitution.

It does not upgrade data eligibility.

---

## `06-Strategy-Constitution.md`

Will define:

- Candidate;
- Entry;
- Position Lifecycle;
- Exit;
- strategy registry;
- strategy universe;
- signal sources;
- position management;
- risk;
- invalidation.

A strategy may require stricter data than another strategy.

The Strategy Constitution declares requirements.

The Data Constitution determines whether the required data contract is actually satisfied.

---

## `07-Validation-Constitution.md`

Will define:

- sample roles;
- walk-forward;
- OOS;
- sealed test;
- statistical and economic proof standards;
- promotion gates;
- degradation criteria.

This Data Constitution defines the evidence substrate.

The Validation Constitution defines how that evidence is used to justify authority.

---

## `08-Roadmap.md`

Will sequence:

- provider evaluation;
- Data Platform implementation;
- formal source acquisition;
- PIT sidecar construction;
- dataset expansion;
- Candidate Discovery data readiness.

The Roadmap may prioritize.

It may not weaken the Data Constitution to accelerate delivery.

---

## `09-Glossary.md`

Will freeze terms such as:

- Point-in-Time;
- Available At;
- Finalized Bar;
- Source Artifact;
- Canonical Data;
- Dataset Manifest;
- Sidecar;
- Eligibility Class;
- Rehearsal Dataset;
- Formal Research Dataset;
- Data Incident.

---

# 46. Constitutional Data Commitments

The project commits to the following data model.

1. **Data accessibility does not imply research eligibility.**
2. **Data validity is relative to the exact research claim and decision-time convention.**
3. **Provider, source artifact, adapter, canonical data, dataset and research role are distinct concepts.**
4. **Point-in-time correctness applies to price, universe, tradability, classifications, fundamentals, events and revisions where relevant.**
5. **Current truth must not be silently substituted for historical truth.**
6. **Timestamp meaning, availability and finalization are first-class semantics.**
7. **A historical bar is not automatically proven final merely because it is old.**
8. **Raw, normalized, canonical and derived data must remain logically distinct.**
9. **Formal and rehearsal datasets require identifiable manifests and quality state.**
10. **Result-affecting sidecars are part of effective dataset identity.**
11. **Critical data uncertainty fails closed or downgrades the evidence claim.**
12. **Missing critical historical state must not be replaced by convenient permissive defaults.**
13. **Provider conflicts must remain observable and be resolved deterministically.**
14. **Raw, back-adjusted, PIT-adjusted and execution price views must not be mixed ambiguously.**
15. **Corporate actions are first-class historical data.**
16. **Candidate Discovery requires a reproducible point-in-time universe.**
17. **Historical ST, suspension and price-limit facts must not be inferred from current state.**
18. **Industry and theme mappings require as-of and version semantics for formal historical research.**
19. **ETF price momentum and ETF fund flow are different information objects.**
20. **Real flow, order-derived flow and OHLCV-based flow proxies must remain semantically distinct.**
21. **Level 2 is strategy-specific, not a universal project requirement.**
22. **Fundamental data must respect publication and revision timelines.**
23. **Policy and event research must preserve publication, effective and derived-classification time.**
24. **Future data may construct labels but may not leak into decision-time inputs.**
25. **Formal dataset builders must not silently invent missing semantics.**
26. **Formal research data artifacts must not be silently overwritten.**
27. **A successful provider POC proves access, not formal source approval.**
28. **A fixture-based rehearsal proves pipeline behavior, not Alpha.**
29. **Current provider classifications are reviewable evidence states, not permanent vendor dogma.**
30. **Licensing and redistribution rights are part of data governance.**
31. **Restricted market data must not be committed publicly without authorization.**
32. **Material data revisions create new identity or explicit revision lineage.**
33. **Data incidents can invalidate experiments and promoted artifacts.**
34. **Agents may assist data work but may not bypass PIT, provenance, access or eligibility rules.**
35. **The project must become more explicit about data identity as its research becomes more sophisticated.**

---

# 47. Closing Declaration

The first phase of `market-regime-alpha` proved that useful research can be built from accessible market data.

The next phase must prove something harder:

> **that the project knows exactly what its data means, when it was knowable, where it came from, what changed, what it is allowed to support, and when it is not good enough.**

The project will not confuse:

```text
Rows
with
Evidence
```

It will not confuse:

```text
Historical Data
with
Point-in-Time Data
```

It will not confuse:

```text
Normalized Fields
with
Verified Semantics
```

It will not confuse:

```text
A Provider Connection
with
A Formal Dataset
```

The constitutional data model is therefore:

```text
Know the source.
Preserve the artifact.
Define the time.
Prove availability.
Protect historical truth.
Build the manifest.
Run the gates.
Classify eligibility honestly.
Use data only for claims it can support.
```

That is the data foundation required for Market Regime Alpha to become a credible Alpha Research Operating System for the China A-share market.
