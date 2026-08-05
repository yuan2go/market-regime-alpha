from __future__ import annotations

from datetime import date, datetime
from urllib.error import URLError
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    AcquiredSourcePayload,
    TencentCurrentQuoteClient,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    PublicCompositeRequest,
)
from market_regime_alpha.data.providers.public_composite.live_clients import (
    AShareDataError,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2026, 8, 5, 14, 55, tzinfo=SHANGHAI))
QUOTE_BYTES = (
    'v_sh601919="1~name~601919~14.91~14.86~14.94~989225~528140~461085~14.90~2221~'
    "14.89~582~14.88~1189~14.87~783~14.86~591~14.91~6727~14.92~1604~14.93~4367~"
    '14.94~6746~14.95~11373~~20260805145400~0.05~0.34~14.98~14.78";\n'
).encode("gb18030")


def _request() -> PublicCompositeRequest:
    return PublicCompositeRequest(
        symbols=("601919.SH",),
        decision_time=DECISION,
        history_start=date(2026, 1, 1),
        minimum_history_sessions=20,
    )


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "text/plain; charset=GBK",
    ) -> None:
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_metadata_binds_request_response_and_raw_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = iter(
        (
            datetime(2026, 8, 5, 14, 54, 0, tzinfo=SHANGHAI),
            datetime(2026, 8, 5, 14, 54, 1, tzinfo=SHANGHAI),
        )
    )
    monkeypatch.setattr(
        "market_regime_alpha.data.providers.public_composite.live_clients.urlopen",
        lambda *_args, **_kwargs: _Response(QUOTE_BYTES),
    )
    client = TencentCurrentQuoteClient(
        clock=lambda: next(observed),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    )

    batch = client.acquire(_request())

    source = batch.raw_payloads[0]
    metadata = source.request_metadata
    assert metadata is not None
    assert metadata.provider_profile_id == TENCENT_FREE_OPERATIONAL_PROFILE_ID
    assert metadata.endpoint == "https://qt.gtimg.cn/q="
    assert metadata.request_parameters == (("symbols", "sh601919"),)
    assert metadata.requested_at.isoformat() == "2026-08-05T14:54:00+08:00"
    assert source.retrieved_time.isoformat() == "2026-08-05T14:54:01+08:00"
    assert metadata.decision_time == DECISION.value
    assert metadata.available_at == source.retrieved_time.value
    assert metadata.http_status == 200
    assert metadata.content_type == "text/plain; charset=GBK"
    assert metadata.response_size == len(QUOTE_BYTES)
    assert metadata.encoding == "gb18030"
    assert metadata.symbol_scope == ("601919.SH",)
    assert metadata.field_scope == ("current_quote",)
    assert source.raw_hash.startswith("sha256:")
    restored = AcquiredSourcePayload.from_canonical_dict(
        source.to_canonical_dict(include_payload=True)
    )
    assert restored == source


def test_legacy_payload_without_metadata_keeps_original_identity() -> None:
    source = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="legacy-quote",
        locator="https://qt.gtimg.cn/q=sh601919",
        raw_payload=QUOTE_BYTES,
        retrieved_time=RetrievedAt(datetime(2026, 8, 5, 14, 54, tzinfo=SHANGHAI)),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    encoded = source.to_canonical_dict(include_payload=True)

    assert "request_metadata" not in encoded
    assert AcquiredSourcePayload.from_canonical_dict(encoded) == source


def test_valid_mislabeled_tencent_body_is_recorded_not_silently_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "market_regime_alpha.data.providers.public_composite.live_clients.urlopen",
        lambda *_args, **_kwargs: _Response(
            QUOTE_BYTES,
            content_type="text/html",
        ),
    )
    client = TencentCurrentQuoteClient(
        clock=lambda: datetime(2026, 8, 5, 14, 54, tzinfo=SHANGHAI)
    )

    batch = client.acquire(_request())

    assert len(batch.quotes) == 1
    assert "TENCENT_CONTENT_TYPE_MISMATCH" in batch.limitations
    assert batch.raw_payloads[0].request_metadata is not None
    assert batch.raw_payloads[0].request_metadata.content_type == "text/html"


@pytest.mark.parametrize(
    ("response", "match"),
    (
        (_Response(b""), "empty response"),
        (_Response(b"<html>upstream error</html>"), "invalid response envelope"),
        (_Response(b"\xff\xfe\xff"), "invalid response encoding"),
    ),
)
def test_invalid_tencent_response_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    response: _Response,
    match: str,
) -> None:
    monkeypatch.setattr(
        "market_regime_alpha.data.providers.public_composite.live_clients.urlopen",
        lambda *_args, **_kwargs: response,
    )
    client = TencentCurrentQuoteClient(
        clock=lambda: datetime(2026, 8, 5, 14, 54, tzinfo=SHANGHAI)
    )

    with pytest.raises(AShareDataError, match=match):
        client.acquire(_request())


def test_tencent_network_error_fails_closed_without_static_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> _Response:
        raise URLError("offline")

    monkeypatch.setattr(
        "market_regime_alpha.data.providers.public_composite.live_clients.urlopen",
        fail,
    )
    client = TencentCurrentQuoteClient(
        clock=lambda: datetime(2026, 8, 5, 14, 54, tzinfo=SHANGHAI)
    )

    with pytest.raises(AShareDataError, match="Tencent quote query failed"):
        client.acquire(_request())


def test_tencent_free_operational_profile_has_distinct_identity() -> None:
    profile = TencentFreeOperationalProfile(
        history_client=object(),
        security_status_client=object(),
        current_client=object(),
    )

    assert profile.profile_id == TENCENT_FREE_OPERATIONAL_PROFILE_ID
