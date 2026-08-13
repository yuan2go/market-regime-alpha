-- Phase E2 selective partition lookup for bounded Historical materialization.

CREATE INDEX historical_corpus_partition_selective_read_idx
ON historical_corpus_partition(
    owner_id,
    owner_hash,
    timeframe,
    symbol_bucket,
    first_market_date,
    last_market_date
)
INCLUDE (
    ordinal,
    partition_id,
    partition_hash,
    row_count,
    relative_path,
    physical_checksum
);

COMMENT ON INDEX historical_corpus_partition_selective_read_idx IS
'Exact-owner timeframe/date/bucket access path for checksum-verified selective Parquet reads.';
