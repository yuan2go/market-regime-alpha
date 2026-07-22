# PIT Validation Partition Governance

## Specification before evidence opening

Every replication requires an explicit provider, partition ID, date-selection rule, start date, end
date, exclusion policy, Protocol ID, and frozen B1-E model-spec hash. Missing dates produce
`PARTITION_SPEC_REQUIRED`; the runner does not choose a favorable interval.

## Seal

After provider Calendar validation and before Candidate scoring, the seal records exact included
and excluded sessions, exclusion reasons, Calendar and Universe identities, provider source hashes,
Protocol, and model specification. Included sessions must be unique, within the requested range,
and disjoint from development evidence. A known partition ID cannot be resealed.

The runner persists the specification, seal, and their checksums under
`.pit-validation-partitions/<partition-id>` before model access. This governance record is separate
from a final success Artifact, so a scoring or publication failure cannot erase the fact that the
partition was sealed.

## First open

The first model read creates a receipt binding opened time, Run ID, semantic Reader identity, and
partition content hash. The seal itself retains `first_opened_at = null`; opening is separate
immutable evidence rather than a mutation of the seal.

The receipt is written exactly once using exclusive-create semantics and binds the content hash of
the current semantic Reader implementation. A second open fails closed even if the first run did not
produce a success Artifact.

No formal partition was specified, sealed, or opened in the current environment because the
required qualified Xuntou v4 provider input is absent.
