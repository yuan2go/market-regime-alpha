-- One retrospective Archive may inventory explicit raw Target and adjusted Feature
-- captures. This token is never valid for a Market bar, gap, Target or prospective archive.
ALTER TABLE mra.market_archive DROP CONSTRAINT market_archive_shape_ck;
ALTER TABLE mra.market_archive ADD CONSTRAINT market_archive_shape_ck CHECK (
        archive_code ~ '^[a-z][a-z0-9_-]{0,99}$'
        AND request_sha256 ~ '^[0-9a-f]{64}$'
        AND lane IN ('RETROSPECTIVE_BACKFILL', 'PROSPECTIVE_CONTEMPORANEOUS')
        AND evidence_class IN ('EXPLORATORY_RETROSPECTIVE', 'FIRST_PARTY_CONTEMPORANEOUS')
        AND exchange_code ~ '^[A-Z][A-Z0-9]{1,15}$'
        AND timeframe IN ('MINUTE_1', 'MINUTE_5', 'MINUTE_15', 'MINUTE_30', 'MINUTE_60', 'DAILY')
        AND (price_basis IN ('RAW_UNADJUSTED', 'FORWARD_ADJUSTED', 'BACKWARD_ADJUSTED')
             OR (price_basis='MIXED_EXPLICIT' AND lane='RETROSPECTIVE_BACKFILL'
                 AND evidence_class='EXPLORATORY_RETROSPECTIVE'))
        AND instrument_scope <> ''
        AND instrument_scope_sha256 ~ '^[0-9a-f]{64}$'
        AND event_window_end >= event_window_start
        AND reserved_free_bytes > 0
        AND maximum_archive_bytes > 0
        AND maximum_slice_bytes > 0
        AND maximum_slice_bytes <= maximum_archive_bytes
        AND provenance_sha256 ~ '^[0-9a-f]{64}$'
        AND slice_count > 0
        AND slice_roster_sha256 ~ '^[0-9a-f]{64}$'
        AND content_sha256 ~ '^[0-9a-f]{64}$'
    );
