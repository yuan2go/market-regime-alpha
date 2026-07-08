"""Notification adapters for quant reports.

The module keeps notification delivery separate from model calculation. Add new
channels here without touching strategy or data-source code.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable, Iterable, Protocol
from urllib.request import Request, urlopen

from market_regime_alpha.data_sources.tushare_client import load_dotenv_if_available


FEISHU_WEBHOOK_URL_ENV = "FEISHU_WEBHOOK_URL"
FEISHU_SECRET_ENV = "FEISHU_SECRET"
NOTIFY_CHANNELS_ENV = "NOTIFY_CHANNELS"


class Notifier(Protocol):
    channel: str

    def send_text(self, text: str) -> "NotificationResult":
        ...


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    success: bool
    message: str


class FeishuWebhookNotifier:
    channel = "feishu"

    def __init__(
        self,
        *,
        webhook_url: str,
        secret: str | None = None,
        timeout_seconds: float = 8.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.webhook_url = webhook_url.strip()
        self.secret = (secret or "").strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.clock = clock

    def send_text(self, text: str) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(self.channel, False, "missing FEISHU_WEBHOOK_URL")
        payload = build_feishu_text_payload(text, secret=self.secret, timestamp=int(self.clock()))
        request = Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(self.channel, False, f"request failed: {exc}")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return NotificationResult(self.channel, False, f"invalid response: {body[:160]}")

        if _feishu_success(data):
            return NotificationResult(self.channel, True, "sent")
        return NotificationResult(self.channel, False, data.get("msg") or data.get("StatusMessage") or str(data))


def build_feishu_text_payload(text: str, *, secret: str = "", timestamp: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        current_timestamp = int(time.time()) if timestamp is None else int(timestamp)
        payload["timestamp"] = str(current_timestamp)
        payload["sign"] = feishu_sign(secret, current_timestamp)
    return payload


def feishu_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_notifications(
    text: str,
    *,
    channels: str | Iterable[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[NotificationResult]:
    notifiers, missing = build_notifiers(channels=channels, env=env)
    results = [notifier.send_text(text) for notifier in notifiers]
    results.extend(missing)
    if not results:
        results.append(NotificationResult("auto", False, "no notification channel configured"))
    return results


def build_notifiers(
    *,
    channels: str | Iterable[str] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[list[Notifier], list[NotificationResult]]:
    if env is None:
        load_dotenv_if_available()
        env = os.environ

    requested = _parse_channels(channels or env.get(NOTIFY_CHANNELS_ENV, "auto"))
    if requested == ["auto"]:
        requested = ["feishu"] if env.get(FEISHU_WEBHOOK_URL_ENV, "").strip() else []

    notifiers: list[Notifier] = []
    missing: list[NotificationResult] = []
    for channel in requested:
        if channel == "feishu":
            webhook_url = env.get(FEISHU_WEBHOOK_URL_ENV, "").strip()
            if not webhook_url:
                missing.append(NotificationResult("feishu", False, f"missing {FEISHU_WEBHOOK_URL_ENV}"))
                continue
            notifiers.append(
                FeishuWebhookNotifier(
                    webhook_url=webhook_url,
                    secret=env.get(FEISHU_SECRET_ENV, ""),
                )
            )
        else:
            missing.append(NotificationResult(channel, False, f"unsupported notification channel: {channel}"))
    return notifiers, missing


def _parse_channels(channels: str | Iterable[str]) -> list[str]:
    if isinstance(channels, str):
        raw_items = channels.replace(";", ",").split(",")
    else:
        raw_items = list(channels)
    output = [str(item).strip().lower() for item in raw_items if str(item).strip()]
    return output or ["auto"]


def _feishu_success(data: dict[str, Any]) -> bool:
    status_code = data.get("StatusCode")
    code = data.get("code")
    return status_code in {0, "0", None} and code in {0, "0", None}
