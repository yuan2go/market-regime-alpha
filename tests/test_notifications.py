from __future__ import annotations

import json
import sys
import unittest
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
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
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
