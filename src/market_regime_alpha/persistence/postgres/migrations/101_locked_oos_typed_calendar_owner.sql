-- Frozen Locked OOS scopes reload the canonical PIT Trading Calendar owner.
-- The generic Research Validation projection is not Calendar authority.

ALTER TABLE frozen_locked_oos_scope
DROP CONSTRAINT frozen_locked_oos_scope_trading_calendar_id_trading_calend_fkey;

ALTER TABLE frozen_locked_oos_scope
ADD CONSTRAINT frozen_locked_oos_scope_calendar_owner_fk
FOREIGN KEY (trading_calendar_id, trading_calendar_hash)
REFERENCES pit_trading_calendar_canonical_snapshot(calendar_id, calendar_hash)
ON DELETE RESTRICT;
