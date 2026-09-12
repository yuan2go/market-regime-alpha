"""Market-owned exact source roster checks before historical acquisition."""

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain.historical_acquisition import HistoricalAcquisitionPlan


class PostgresHistoricalAcquisitionSources:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def validate(self, plan: HistoricalAcquisitionPlan) -> dict:
        with self._pool.connection(read_only=True) as connection:
            source = connection.execute("""SELECT product.provider_id, provider.provider_code,
                archive.content_sha256, clock_timestamp() FROM mra.market_archive archive
                JOIN mra.provider_product product USING(provider_product_id) JOIN mra.provider provider USING(provider_id)
                WHERE archive.market_archive_id=%s""", (plan.template_archive_id,)).fetchone()
            if source is None or source[2] != plan.template_archive_sha256:
                raise ValueError("historical acquisition template Archive identity mismatch")
            if "baostock" not in source[1].lower():
                raise ValueError("historical acquisition requires the exact existing BaoStock Provider")
            if plan.end_date >= source[3].date():
                raise ValueError("historical acquisition must end before the actual current UTC date")
            identities = connection.execute("""SELECT DISTINCT identifier.identifier_value, identifier.instrument_id
                FROM mra.instrument_identifier identifier
                JOIN mra.market_capture_instrument_identifier_normalization binding USING(instrument_identifier_id)
                JOIN mra.market_archive_capture_observation observation USING(capture_id)
                WHERE observation.market_archive_id=%s AND identifier.identifier_scheme='BAOSTOCK'
                  AND identifier.identifier_value=ANY(%s) ORDER BY identifier.identifier_value""",
                (plan.template_archive_id, list(plan.codes))).fetchall()
            if tuple(row[0] for row in identities) != plan.codes:
                raise ValueError("requested securities must match exact archived identifiers; no current-list substitution")
        return {"provider_id": source[0], "securities": identities}
