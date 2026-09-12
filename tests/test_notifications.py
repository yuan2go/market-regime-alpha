from __future__ import annotations

import json
import sys
import unittest
import pytest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.notifications import (  # noqa: E402
    FEISHU_WEBHOOK_URL_ENV,
    FeishuWebhookNotifier,
    build_feishu_text_payload,
    feishu_sign,
    send_notifications,
    _feishu_success,
)


class FakeResponse:
    status = 200
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class NotificationsTests(unittest.TestCase):
    def test_feishu_text_payload_without_secret(self) -> None:
        payload = build_feishu_text_payload("hello")

        self.assertEqual(payload["msg_type"], "text")
        self.assertEqual(payload["content"]["text"], "hello")
        self.assertNotIn("sign", payload)

    def test_feishu_text_payload_with_secret(self) -> None:
        payload = build_feishu_text_payload("hello", secret="abc", timestamp=123)

        self.assertEqual(payload["timestamp"], "123")
        self.assertEqual(payload["sign"], feishu_sign("abc", 123))

    def test_send_notifications_reports_missing_feishu_webhook(self) -> None:
        results = send_notifications("hello", channels="feishu", env={})

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn(FEISHU_WEBHOOK_URL_ENV, results[0].message)

    def test_feishu_notifier_sends_text_request(self) -> None:
        captured: dict[str, object] = {}

        def fake_opener(request, timeout):  # noqa: ANN001, ANN202
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"StatusCode": 0, "StatusMessage": "success"})

        notifier = FeishuWebhookNotifier(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/demo",
            opener=fake_opener,
            clock=lambda: 123,
        )
        result = notifier.send_text("中远海控量化提醒")

        self.assertTrue(result.success)
        self.assertEqual(captured["url"], "https://open.feishu.cn/open-apis/bot/v2/hook/demo")
        self.assertEqual(captured["timeout"], 8.0)
        self.assertEqual(captured["body"]["content"]["text"], "中远海控量化提醒")


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("payload", [
    {}, {"msg": "success"}, {"code": None}, {"code": False}, {"code": "0"},
    {"code": 0.0}, {"StatusCode": []}, {"code": 0, "StatusCode": 1},
    {"code": 1, "StatusCode": 0}, {"code": 0, "data": []}, {"code": 0, "msg": []},
    None, [], 0, "success",
])
def test_ambiguous_or_malformed_webhook_response_never_acknowledges(payload):
    assert _feishu_success(payload) is False
    notifier = FeishuWebhookNotifier(webhook_url="https://example.invalid/hook",
                                    opener=lambda *_args, **_kwargs: FakeResponse(payload))
    result = notifier.send_text("immutable report")
    assert not result.success


@pytest.mark.parametrize("payload", [{"code": 0}, {"StatusCode": 0},
    {"code": 0, "StatusCode": 0, "msg": "success", "data": {}}])
def test_webhook_acceptance_does_not_invent_delivery_or_remote_identity(payload):
    from market_regime_alpha.interfaces.daily_delivery import LegacyNotifierDeliveryAdapter
    notifier = FeishuWebhookNotifier(webhook_url="https://example.invalid/hook",
                                    opener=lambda *_args, **_kwargs: FakeResponse(payload))
    attempt = LegacyNotifierDeliveryAdapter(notifier).deliver("report", idempotency_key="frozen-request")
    assert attempt.state == "ACCEPTED"
    assert attempt.remote_receipt_id is None
    assert len(attempt.request_sha256) == 64
    assert len(attempt.response_sha256) == 64


def test_transport_exception_is_unknown_without_credential_leak():
    def fail(*_args, **_kwargs):
        raise TimeoutError("https://private.invalid/secret-webhook")
    notifier = FeishuWebhookNotifier(webhook_url="https://example.invalid/hook", opener=fail)
    result = notifier.send_text("report")
    assert result.state == "UNKNOWN"
    assert "secret-webhook" not in result.message


def test_legacy_boolean_success_alone_is_not_remote_evidence():
    from market_regime_alpha.interfaces.daily_delivery import LegacyNotifierDeliveryAdapter
    from market_regime_alpha.notifications import NotificationResult
    class Legacy:
        channel = "fixture"
        def send_text(self, text):
            return NotificationResult(self.channel, True, "sent")
    attempt = LegacyNotifierDeliveryAdapter(Legacy()).deliver("report", idempotency_key="frozen-request")
    assert attempt.state == "UNKNOWN"
    assert attempt.remote_receipt_id is None


@pytest.mark.parametrize("body,status,accepted", [
    (b'{"code":0,"data":{},"msg":"success"}', 200, True),
    (b'{"code":0,"code":1}', 200, False),
    (b'{"code":0,"data":{"unknown":NaN}}', 200, False),
    (b'{"code":0}', 500, False), (b'\xff', 200, False),
])
def test_local_http_webhook_protocol_binds_actual_request_and_response(body, status, accepted):
    from hashlib import sha256
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from urllib.request import build_opener, ProxyHandler
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        notifier = FeishuWebhookNotifier(webhook_url=f"http://127.0.0.1:{server.server_port}/fixture",
            clock=lambda: 123, opener=build_opener(ProxyHandler({})).open)
        result = notifier.send_text("exact frozen report")
        assert result.success is accepted
        assert result.state == ("ACCEPTED" if accepted else "UNKNOWN")
        assert result.request_sha256 == sha256(received[0]).hexdigest()
        assert result.response_sha256 == sha256(body).hexdigest()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
