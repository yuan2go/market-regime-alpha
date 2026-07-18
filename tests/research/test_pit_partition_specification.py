from datetime import datetime, timezone

import pytest

from market_regime_alpha.research.pit_partition_v2 import ValidationPartitionSpecification


def test_partition_requires_explicit_date_range() -> None:
    with pytest.raises(ValueError, match="PARTITION_SPEC_REQUIRED"):
        ValidationPartitionSpecification(
            "pit-validation-partition-specification-v1", "p", "XUNTOU", "EXPLICIT", None,
            None, 2, "NONE", "protocol", "model", datetime.now(timezone.utc), "SPECIFIED_NOT_OPENED"
        )
