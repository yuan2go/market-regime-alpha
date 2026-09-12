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
from urllib.error import HTTPError

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
    state: str = "UNKNOWN"
    request_sha256: str | None = None
    response_sha256: str | None = None


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
            return NotificationResult(self.channel, False, "missing FEISHU_WEBHOOK_URL", "PROVEN_NOT_SENT")
        payload = build_feishu_text_payload(text, secret=self.secret, timestamp=int(self.clock()))
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_hash = hashlib.sha256(request_body).hexdigest()
        request = Request(
            self.webhook_url,
            data=request_body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                body = response.read(65537)
                status = response.status
        except HTTPError as exc:
            # A real HTTP rejection still has response bytes. Keep their digest;
            # status alone cannot prove that an external effect was absent.
            try:
                with exc:
                    body = exc.read(65537)
                response_hash = hashlib.sha256(body).hexdigest()
            except Exception:
                response_hash = None
            return NotificationResult(self.channel, False, "HTTP response not accepted", "UNKNOWN", request_hash, response_hash)
        except Exception as exc:  # noqa: BLE001
            # An interrupted POST may have been accepted. Never expose the URL
            # or exception text, and never turn transport uncertainty into retry.
            return NotificationResult(self.channel, False, f"request failed: {type(exc).__name__}",
                                      request_sha256=request_hash)

        response_hash = hashlib.sha256(body).hexdigest()
        if type(status) is not int or status != 200 or len(body) > 65536:
            return NotificationResult(self.channel, False, "unexpected HTTP response", "UNKNOWN", request_hash, response_hash)

        try:
            data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_response_fields,
                              parse_constant=_invalid_response_number)
        except (UnicodeDecodeError, ValueError):
            return NotificationResult(self.channel, False, "invalid response", "UNKNOWN", request_hash, response_hash)

        if _feishu_success(data):
            return NotificationResult(self.channel, True, "remote accepted; final delivery unverified",
                                      "ACCEPTED", request_hash, response_hash)
        # Even a negative/malformed response is not sufficient evidence for an
        # automatic duplicate POST. A protocol-specific reconciler must prove absence.
        return NotificationResult(self.channel, False, "remote acceptance unverified", "UNKNOWN", request_hash, response_hash)


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


def _feishu_success(data: object) -> bool:
    """Webhook ACK only; the official response supplies no remote message ID.

    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    StatusCode is a deprecated compatibility field. Either explicit numeric
    success field is accepted; every present status must agree and be an int.
    """
    if not isinstance(data, dict):
        return False
    statuses = [data[key] for key in ("code", "StatusCode") if key in data]
    return bool(statuses) and all(type(value) is int and value == 0 for value in statuses) and all(
        key not in data or isinstance(data[key], str) for key in ("msg", "StatusMessage")
    ) and ("data" not in data or isinstance(data["data"], dict))


def _unique_response_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate webhook response field")
        result[key] = value
    return result


def _invalid_response_number(value: str) -> None:
    raise ValueError("non-finite webhook response number")
