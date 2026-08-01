PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS traceable_manual_trade_bindings_no_delete;
DROP TRIGGER IF EXISTS traceable_manual_trade_bindings_no_update;
DROP TABLE IF EXISTS traceable_manual_trade_bindings;
DROP TABLE IF EXISTS position_book_events;
DROP INDEX IF EXISTS one_open_position_book_per_account_symbol;
DROP TABLE IF EXISTS position_books;
DELETE FROM pdl_schema_migrations WHERE version = 6;

PRAGMA foreign_keys = ON;
