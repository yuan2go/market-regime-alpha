from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from uuid import uuid4

import pytest

from market_regime_alpha.selection.domain import (
    CriterionOperator,
    CriterionValueKind,
    EligibilityPolicy,
    EligibilityRule,
    EligibilityRuleKind,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.hashing import sha256_bytes
from market_regime_alpha.shared.identity import InstrumentId


def _scope_bytes(product_id, instruments: tuple[InstrumentId, ...]) -> bytes:
    return json.dumps(
        {
            "classification_code": "CSI_300",
            "classification_scheme": "INDEX",
            "instrument_ids": [str(item) for item in instruments],
            "market_provider_product_id": str(product_id),
            "schema": "selection-universe-scope-v1",
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def test_universe_scope_requires_exact_immutable_canonical_config_identity() -> None:
    product_id = uuid4()
    instruments = tuple(sorted((InstrumentId(uuid4()), InstrumentId(uuid4())), key=str))
    content = _scope_bytes(product_id, instruments)
    scope = UniverseScopeSpecification(
        artifact_id=uuid4(),
        content_sha256=sha256_bytes(content),
        size_bytes=len(content),
        market_provider_product_id=product_id,
        classification_scheme="INDEX",
        classification_code="CSI_300",
        instrument_ids=instruments,
    )
    assert scope.canonical_bytes() == content
    with pytest.raises(ValueError, match="unique and sorted"):
        replace(scope, instrument_ids=tuple(reversed(instruments)))
    with pytest.raises(ValueError, match="hash"):
        replace(scope, content_sha256="0" * 64)
    with pytest.raises(ValueError, match="size"):
        replace(scope, size_bytes=len(content) + 1)


def test_listing_age_and_liquidity_have_no_hidden_unit_window_or_threshold() -> None:
    listing = EligibilityRule(
        eligibility_rule_id=uuid4(),
        rule_code="MIN_LISTING_AGE",
        ordinal=1,
        rule_kind=EligibilityRuleKind.MIN_LISTING_AGE,
        measure_code="LISTING_AGE",
        aggregation="ELAPSED",
        window_value=0,
        window_unit="NONE",
        value_kind=CriterionValueKind.DECIMAL,
        operator=CriterionOperator.GTE,
        value_unit="CALENDAR_DAYS",
        threshold_decimal=Decimal("365"),
    )
    liquidity = EligibilityRule(
        eligibility_rule_id=uuid4(),
        rule_code="MIN_LIQUIDITY",
        ordinal=2,
        rule_kind=EligibilityRuleKind.MIN_LIQUIDITY,
        measure_code="TURNOVER_VALUE",
        aggregation="MEAN",
        window_value=20,
        window_unit="SESSION",
        value_kind=CriterionValueKind.DECIMAL,
        operator=CriterionOperator.GTE,
        value_unit="CNY",
        threshold_decimal=Decimal("100000000"),
    )
    policy = EligibilityPolicy(
        eligibility_policy_id=uuid4(),
        market_provider_product_id=uuid4(),
        policy_code="explicit-policy",
        version=1,
        rules=(listing, liquidity),
    )
    assert policy.rules[0].value_unit == "CALENDAR_DAYS"
    assert policy.rules[1].window_value == 20
    assert policy.rules[1].value_unit == "CNY"
    assert policy.rules[1].threshold_decimal == Decimal("100000000.0000000000")
    with pytest.raises(ValueError, match="invalid explicit shape"):
        replace(listing, value_unit="TRADING_DAYS")
    with pytest.raises(ValueError, match="explicit session window"):
        replace(liquidity, window_value=0)
    with pytest.raises(ValueError, match="invalid explicit shape"):
        replace(liquidity, aggregation="MEDIAN")
    with pytest.raises(ValueError, match="invalid explicit shape"):
        replace(liquidity, operator=CriterionOperator.EQ)


def test_policy_identity_hashes_provider_product_and_complete_ordered_rules() -> None:
    rule = EligibilityRule(
        eligibility_rule_id=uuid4(),
        rule_code="NOT_SUSPENDED",
        ordinal=1,
        rule_kind=EligibilityRuleKind.NOT_SUSPENDED,
        measure_code="SECURITY_STATUS",
        aggregation="POINT",
        window_value=1,
        window_unit="SESSION",
        value_kind=CriterionValueKind.STATUS,
        operator=CriterionOperator.EQ,
        value_unit="STATUS",
        threshold_status="ACTIVE",
    )
    policy = EligibilityPolicy(
        eligibility_policy_id=uuid4(),
        market_provider_product_id=uuid4(),
        policy_code="one-rule",
        version=1,
        rules=(rule,),
    )
    changed_product = replace(policy, market_provider_product_id=uuid4())
    assert changed_product.content_sha256 != policy.content_sha256
    with pytest.raises(ValueError, match="completely ordered"):
        replace(policy, rules=(replace(rule, ordinal=2),))
