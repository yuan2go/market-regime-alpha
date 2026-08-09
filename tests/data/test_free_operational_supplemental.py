from __future__ import annotations

from datetime import date, datetime
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data.providers.public_composite import (
    BaoStockFreeSupplementalClient,
    PublicCompositeRequest,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2026, 8, 10, 14, 55, tzinfo=SHANGHAI))


class _FailingBaoStockHistory:
    def __init__(self) -> None:
        self.calls = 0

    def acquire(self, request: PublicCompositeRequest):
        self.calls += 1
        raise AShareDataError("BAOSTOCK_UNAVAILABLE")


def test_free_operational_policy_imports_in_a_fresh_interpreter() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from market_regime_alpha.data.free_operational_policy "
                "import canonical_free_operational_evidence_policy; "
                "canonical_free_operational_evidence_policy()"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_baostock_supplemental_failure_propagates_without_fallback() -> None:
    history = _FailingBaoStockHistory()
    client = BaoStockFreeSupplementalClient(
        history_client=history,
        policy=canonical_free_operational_evidence_policy(),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        clock=lambda: datetime(2026, 8, 10, 14, 30, tzinfo=SHANGHAI),
    )
    request = PublicCompositeRequest(
        symbols=("600000.SH",),
        decision_time=DECISION,
        history_start=date(2026, 7, 1),
        minimum_history_sessions=11,
    )

    with pytest.raises(AShareDataError, match="BAOSTOCK_UNAVAILABLE"):
        client.acquire(request)

    assert history.calls == 1
