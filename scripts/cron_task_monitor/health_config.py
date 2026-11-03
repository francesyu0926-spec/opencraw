from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class HealthMonitorConfig:
    timezone: str
    url: str
    method: str
    token_env: str
    request_timeout_seconds: int
    expected_status: str
    notify: str
    login_url: str = "https://terminal.sfccn.com/terminal/zxt-web/login/pwd"
    login_code_env: str = "QUOTES_LOGIN_CODE"
    login_password_env: str = "QUOTES_LOGIN_PASSWORD"
    wecom_webhook_env: str = "WECOM_WEBHOOK_URL_HEALTH"


def load_health_config(path: str | Path) -> HealthMonitorConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("health config must be a mapping")
    wecom = data.get("wecom") or {}
    if not isinstance(wecom, dict):
        wecom = {}
    return HealthMonitorConfig(
        timezone=str(data.get("timezone") or "Asia/Shanghai"),
        url=str(data["url"]),
        method=str(data.get("method") or "POST").upper(),
        token_env=str(data.get("token_env") or "QUOTES_HEALTH_TOKEN").strip(),
        request_timeout_seconds=int(data.get("request_timeout_seconds") or 30),
        expected_status=str(data.get("expected_status") or "UP"),
        notify=str(data.get("notify") or ""),
        login_url=str(
            data.get("login_url")
            or "https://terminal.sfccn.com/terminal/zxt-web/login/pwd"
        ).strip(),
        login_code_env=str(data.get("login_code_env") or "QUOTES_LOGIN_CODE").strip(),
        login_password_env=str(
            data.get("login_password_env") or "QUOTES_LOGIN_PASSWORD"
        ).strip(),
        wecom_webhook_env=str(
            wecom.get("webhook_env") or "WECOM_WEBHOOK_URL_HEALTH"
        ).strip(),
    )
