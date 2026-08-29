"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from datetime import datetime


from market_regime_alpha.market.domain import (
    ClassificationMembershipRevision,
    ClassificationRevision,
    Instrument,
    InstrumentFactKind,
    InstrumentIdentifier,
    MarketFactKind,
    NormalizationBatch,
    Provider,
    ProviderProduct,
    TradingSession,
)
from market_regime_alpha.runtime.errors import (
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)


from market_regime_alpha.infrastructure.postgres.repositories._market_repository_support import _MarketRepositorySupport


class _MarketReferenceRepository(_MarketRepositorySupport):
    def register_provider(self, provider: Provider) -> int:
        self._connection.execute(
            "\n            INSERT INTO mra.provider (\n                provider_id, provider_code, display_name, provider_kind\n            )\n            VALUES (%s, %s, %s, %s)\n            ",
            (provider.provider_id, provider.provider_code, provider.display_name, provider.provider_kind.value),
        )
        return 1

    def register_provider_product(self, product: ProviderProduct) -> int:
        self._validate_product_predecessor(product)
        self._connection.execute(
            "\n            INSERT INTO mra.provider_product (\n                provider_product_id, provider_id, product_code, revision,\n                payload_family, media_type, payload_encoding,\n                fact_kinds, instrument_fact_kinds, bar_timeframes,\n                price_bases,\n                decision_visibility_policy, source_availability_policy,\n                supersedes_provider_product_id\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                    'KNOWN_AT', %s, %s)\n            ",
            (
                product.provider_product_id,
                product.provider_id,
                product.product_code,
                product.revision,
                product.payload_family,
                product.media_type,
                product.payload_encoding,
                [item.value for item in product.fact_kinds],
                [item.value for item in product.instrument_fact_kinds],
                [item.value for item in product.bar_timeframes],
                [item.value for item in product.price_bases],
                product.source_availability_policy.value,
                product.supersedes_provider_product_id,
            ),
        )
        return product.revision

    def _insert_instrument(self, instrument: Instrument, *, recorded_at: datetime, known_at: datetime) -> None:
        self._connection.execute(
            "\n            INSERT INTO mra.instrument (\n                instrument_id, canonical_code, exchange, instrument_type,\n                currency, source_capture_id, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                instrument.instrument_id.value,
                instrument.canonical_code,
                instrument.exchange,
                instrument.instrument_type.value,
                instrument.currency,
                instrument.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_instrument_identifier(self, identifier: InstrumentIdentifier, *, recorded_at: datetime, known_at: datetime) -> None:
        self._validate_identifier_predecessor(identifier)
        self._connection.execute(
            "\n            INSERT INTO mra.instrument_identifier (\n                instrument_identifier_id, instrument_id, identifier_scheme,\n                identifier_value, effective_from, effective_to, revision,\n                supersedes_identifier_id, source_capture_id, recorded_at,\n                known_at, decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                identifier.instrument_identifier_id,
                identifier.instrument_id.value,
                identifier.identifier_scheme,
                identifier.identifier_value,
                identifier.effective_from,
                identifier.effective_to,
                identifier.revision,
                identifier.supersedes_identifier_id,
                identifier.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_trading_session(self, session: TradingSession, *, recorded_at: datetime, known_at: datetime) -> None:
        self._connection.execute(
            "\n            INSERT INTO mra.trading_session (\n                session_id, exchange, session_date, timezone_name, open_at,\n                break_start_at, break_end_at, close_at,\n                decision_reference_at, source_capture_id, recorded_at,\n                known_at, decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                session.session_id.value,
                session.exchange,
                session.session_date,
                session.timezone_name,
                session.open_at,
                session.break_start_at,
                session.break_end_at,
                session.close_at,
                session.decision_reference_at,
                session.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_classification(self, item: ClassificationRevision, *, recorded_at: datetime, known_at: datetime) -> None:
        self._validate_classification_predecessor(item)
        self._connection.execute(
            "\n            INSERT INTO mra.classification (\n                classification_id, classification_scheme,\n                classification_code, display_name, revision,\n                effective_from, effective_to,\n                supersedes_classification_id, source_capture_id, recorded_at,\n                known_at, decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                item.classification_id,
                item.classification_scheme,
                item.classification_code,
                item.display_name,
                item.revision,
                item.effective_from,
                item.effective_to,
                item.supersedes_classification_id,
                item.source_capture_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_classification_membership(
        self, item: ClassificationMembershipRevision, *, recorded_at: datetime, known_at: datetime
    ) -> None:
        self._validate_membership_predecessor(item)
        self._connection.execute(
            "\n            INSERT INTO mra.classification_membership_revision (\n                membership_revision_id, classification_id, instrument_id,\n                source_capture_id, membership_status, effective_from,\n                effective_to, revision, supersedes_membership_revision_id,\n                recorded_at, known_at, decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                item.membership_revision_id,
                item.classification_id,
                item.instrument_id.value,
                item.source_capture_id,
                item.membership_status.value,
                item.effective_from,
                item.effective_to,
                item.revision,
                item.supersedes_membership_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _validate_product_capabilities(self, batch: NormalizationBatch) -> None:
        row = self._connection.execute(
            "\n            SELECT fact_kinds, instrument_fact_kinds, bar_timeframes,\n                   price_bases\n            FROM mra.provider_product\n            WHERE provider_product_id = %s\n            FOR SHARE\n            ",
            (batch.source_provider_product_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"ProviderProduct {batch.source_provider_product_id} does not exist")
        allowed_kinds = frozenset((MarketFactKind(str(item)) for item in row[0]))
        if not batch.required_fact_kinds <= allowed_kinds:
            missing = sorted((item.value for item in batch.required_fact_kinds - allowed_kinds))
            raise RuntimeStateConflictError(f"Normalization exceeds ProviderProduct fact capabilities: {missing}")
        allowed_instrument_fact_kinds = frozenset((InstrumentFactKind(str(item)) for item in row[1]))
        if not batch.required_instrument_fact_kinds <= allowed_instrument_fact_kinds:
            missing = sorted((item.value for item in batch.required_instrument_fact_kinds - allowed_instrument_fact_kinds))
            raise RuntimeStateConflictError(f"Normalization exceeds ProviderProduct instrument-fact capabilities: {missing}")
        allowed_timeframes = frozenset((str(item) for item in row[2]))
        allowed_bases = frozenset((str(item) for item in row[3]))
        required_timeframes = {item.timeframe.value for item in batch.bars} | {
            item.timeframe.value for item in batch.gaps if item.timeframe is not None
        }
        required_bases = {item.price_basis.value for item in batch.bars} | {
            item.price_basis.value for item in batch.gaps if item.price_basis is not None
        }
        if not required_timeframes <= allowed_timeframes:
            raise RuntimeStateConflictError("Normalization exceeds ProviderProduct timeframe capabilities")
        if not required_bases <= allowed_bases:
            raise RuntimeStateConflictError("Normalization exceeds ProviderProduct price-basis capabilities")

    def _validate_product_predecessor(self, product: ProviderProduct) -> None:
        if product.supersedes_provider_product_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT provider_id, product_code, revision\n            FROM mra.provider_product\n            WHERE provider_product_id = %s\n            FOR SHARE\n            ",
            (product.supersedes_provider_product_id,),
        ).fetchone()
        if row != (product.provider_id, product.product_code, product.revision - 1):
            raise RuntimeStateConflictError("ProviderProduct predecessor is not exact")

    def _validate_identifier_predecessor(self, item: InstrumentIdentifier) -> None:
        if item.supersedes_identifier_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT instrument_id, identifier_scheme, identifier_value,\n                   effective_from, revision\n            FROM mra.instrument_identifier\n            WHERE instrument_identifier_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_identifier_id,),
        ).fetchone()
        if row != (item.instrument_id.value, item.identifier_scheme, item.identifier_value, item.effective_from, item.revision - 1):
            raise RuntimeStateConflictError("InstrumentIdentifier predecessor is not exact")

    def _validate_classification_predecessor(self, item: ClassificationRevision) -> None:
        if item.supersedes_classification_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT classification_scheme, classification_code,\n                   effective_from, revision\n            FROM mra.classification\n            WHERE classification_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_classification_id,),
        ).fetchone()
        if row != (item.classification_scheme, item.classification_code, item.effective_from, item.revision - 1):
            raise RuntimeStateConflictError("Classification predecessor is not exact")

    def _validate_membership_predecessor(self, item: ClassificationMembershipRevision) -> None:
        if item.supersedes_membership_revision_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT prior_classification.classification_scheme,\n                   prior_classification.classification_code,\n                   membership.instrument_id, membership.effective_from,\n                   membership.revision\n            FROM mra.classification_membership_revision AS membership\n            JOIN mra.classification AS prior_classification\n              ON prior_classification.classification_id = membership.classification_id\n            WHERE membership.membership_revision_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_membership_revision_id,),
        ).fetchone()
        classification = self._connection.execute(
            "\n            SELECT classification_scheme, classification_code\n            FROM mra.classification\n            WHERE classification_id = %s\n            FOR SHARE\n            ",
            (item.classification_id,),
        ).fetchone()
        expected = (*(classification or (None, None)), item.instrument_id.value, item.effective_from, item.revision - 1)
        if row != expected:
            raise RuntimeStateConflictError("ClassificationMembership predecessor is not exact")
