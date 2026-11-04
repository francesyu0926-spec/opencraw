from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WsMonitorConfig:
    timezone: str
    url: str
    connect_timeout_seconds: int
    hold_seconds: int
    notify: str
    subscribe_message: dict[str, Any]
    skip_window_start: str = "08:30"
    skip_window_end: str = "09:00"
    wecom_webhook_env: str = "WECOM_WEBHOOK_URL_WS"
    message_must_contain: str = "quoteItems"
    interval_seconds: int = 600


def load_ws_config(path: str | Path) -> WsMonitorConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ws config must be a mapping")
    skip = data.get("skip_window") or {}
    wecom = data.get("wecom") or {}
    if not isinstance(wecom, dict):
        wecom = {}
    return WsMonitorConfig(
        timezone=str(data.get("timezone") or "Asia/Shanghai"),
        url=str(data["url"]),
        connect_timeout_seconds=int(data.get("connect_timeout_seconds") or 15),
        hold_seconds=int(data.get("hold_seconds") or 30),
        notify=str(data.get("notify") or ""),
        subscribe_message=dict(data.get("subscribe_message") or {}),
        skip_window_start=str(skip.get("start") or "08:30"),
        skip_window_end=str(skip.get("end") or "09:00"),
        wecom_webhook_env=str(wecom.get("webhook_env") or "WECOM_WEBHOOK_URL_WS").strip(),
        message_must_contain=str(data.get("message_must_contain") or "quoteItems"),
        interval_seconds=int(data.get("interval_seconds") or 600),
    )
