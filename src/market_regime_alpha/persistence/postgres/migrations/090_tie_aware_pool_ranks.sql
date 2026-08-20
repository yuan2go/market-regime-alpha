-- A rank is an equivalence class, not a row identity.  V2 tie-aware ranking
-- can therefore persist multiple included symbols with the same rank.  The
-- (pool_id, symbol) primary key remains the immutable member identity.

ALTER TABLE dynamic_stock_pool_member
    DROP CONSTRAINT dynamic_stock_pool_member_pool_id_rank_key;

COMMENT ON COLUMN dynamic_stock_pool_member.rank IS
'Tie-aware competition rank. Multiple symbols in one pool may share a rank; rank is never an identity or implicit selection tie-break.';
