from dataclasses import replace

import pytest

from market_regime_alpha.research.mr2b_f2b_protocol import (
    F2B_PRIMARY_HYPOTHESIS_ID,
    F2BProtocol,
    frozen_f2b_protocol,
)


def test_frozen_protocol_is_directional_and_identified() -> None:
    protocol = frozen_f2b_protocol()

    assert protocol.primary_hypothesis_id == F2B_PRIMARY_HYPOTHESIS_ID
    assert protocol.alternative == "UP_GREATER_THAN_DOWN"
    assert protocol.economic_effect_floor == 0.001
    assert protocol.bootstrap_draws == 10_000
    assert protocol.bootstrap_block_length == 5
    assert protocol.bootstrap_sensitivity_block_lengths == (3, 10)
    assert protocol.random_permutation_draws == 10_000
    assert protocol.authority_ceiling == "EXPLORATORY"
    assert protocol.protocol_id.startswith("sha256:")


def test_protocol_identity_is_payload_sensitive_and_rejects_two_sided() -> None:
    protocol = frozen_f2b_protocol()
    assert replace(protocol, bootstrap_block_length=3).protocol_id != protocol.protocol_id
    with pytest.raises(ValueError, match="UP_GREATER_THAN_DOWN"):
        F2BProtocol(**{**protocol.to_canonical_dict(), "alternative": "TWO_SIDED"})
