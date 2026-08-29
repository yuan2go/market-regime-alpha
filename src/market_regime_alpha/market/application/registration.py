"""Explicit Market/PIT commands over a narrow bounded transaction."""

from __future__ import annotations


from market_regime_alpha.market.domain import (
    Provider,
    ProviderProduct,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.shared.hashing import canonical_json_sha256

from market_regime_alpha.market.application._support import (
    _MarketCommandSupport,
    _replayed_mutation,
)
from market_regime_alpha.market.application.results import MarketMutationResult


class _RegistrationCommands(_MarketCommandSupport):
    def register_provider(self, provider: Provider, context: CommandContext) -> MarketMutationResult:
        request_hash = canonical_json_sha256(provider)
        result_hash = canonical_json_sha256({"provider_id": provider.provider_id, "version": 1})
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_MARKET_PROVIDER",
                scope_id=provider.provider_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.market.register_provider(provider)
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="MARKET_PROVIDER",
                aggregate_id=str(provider.provider_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_MARKET_PROVIDER",
                context=context,
            )
            uow.commit()
            return MarketMutationResult(
                aggregate_kind="MARKET_PROVIDER",
                aggregate_id=str(provider.provider_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def register_provider_product(self, product: ProviderProduct, context: CommandContext) -> MarketMutationResult:
        request_hash = canonical_json_sha256(product)
        result_hash = canonical_json_sha256({"provider_product_id": product.provider_product_id, "revision": product.revision})
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_PROVIDER_PRODUCT",
                scope_id=f"{product.provider_id}:{product.product_code}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_mutation(receipt)
            version = uow.market.register_provider_product(product)
            self._finish_mutation(
                uow,
                receipt_id=receipt.receipt_id,
                aggregate_kind="PROVIDER_PRODUCT",
                aggregate_id=str(product.provider_product_id),
                aggregate_version=version,
                result_hash=result_hash,
                action="REGISTER_PROVIDER_PRODUCT",
                context=context,
            )
            uow.commit()
            return MarketMutationResult(
                aggregate_kind="PROVIDER_PRODUCT",
                aggregate_id=str(product.provider_product_id),
                aggregate_version=version,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )
