from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import Alert


def format_alert_text(alerts: list[Alert], *, title: str | None = None) -> str:
    lines = [title or "【行情定时任务监控告警】"]
    for a in alerts:
        title = a.task_name or a.task_id or "系统"
        lines.append(f"{title}\n{a.message}")
        if a.notify:
            lines.append(f"负责人: {a.notify}")
        lines.append("")
    return "\n".join(lines).strip()


# §2.1 ELK 定时任务与 §2.2 WebSocket 使用不同机器人时，分别配置环境变量
DEFAULT_WEBHOOK_ENV_ELK = "WECOM_WEBHOOK_URL_ELK"
DEFAULT_WEBHOOK_ENV_WS = "WECOM_WEBHOOK_URL_WS"


def resolve_webhook_url(webhook_env: str | None = None) -> str | None:
    """
    读取 webhook_env 命名的环境变量（YAML 里 wecom.webhook_env）。
    未配置时：ELK 兼容旧变量 WECOM_WEBHOOK_URL；WS 仅认 WECOM_WEBHOOK_URL_WS。
    """
    keys: list[str] = []
    if webhook_env:
        keys.append(webhook_env.strip())
    for fallback in (
        DEFAULT_WEBHOOK_ENV_ELK,
        "WECOM_WEBHOOK_URL",
        "WEIXIN_WEBHOOK_URL",
        "WEWORK_WEBHOOK_URL",
        "ALERT_WEBHOOK_URL",
    ):
        if fallback not in keys:
            keys.append(fallback)

    for key in keys:
        url = os.environ.get(key, "").strip()
        if url:
            return url
    return None


def resolve_webhook_url_ws(webhook_env: str | None = None) -> str | None:
    keys = [webhook_env.strip()] if webhook_env else [DEFAULT_WEBHOOK_ENV_WS]
    for key in keys:
        url = os.environ.get(key, "").strip()
        if url:
            return url
    return None


def _is_wecom_webhook(url: str) -> bool:
    return "qyapi.weixin.qq.com" in url


def _build_payload(
    url: str, alerts: list[Alert], *, title: str | None = None
) -> dict[str, Any]:
    text = format_alert_text(alerts, title=title)
    if _is_wecom_webhook(url):
        return {"msgtype": "text", "text": {"content": text}}
    return {
        "text": text,
        "alerts": [
            {
                "kind": a.kind.value,
                "task_id": a.task_id,
                "task_name": a.task_name,
                "message": a.message,
                "notify": a.notify,
                "severity": a.severity,
            }
            for a in alerts
        ],
    }


def send_webhook(
    alerts: list[Alert],
    *,
    webhook_env: str | None = None,
    channel: str = "elk",
    alert_title: str | None = None,
) -> tuple[bool, str]:
    if channel == "ws":
        url = resolve_webhook_url_ws(webhook_env)
        missing = webhook_env or DEFAULT_WEBHOOK_ENV_WS
    else:
        url = resolve_webhook_url(webhook_env or DEFAULT_WEBHOOK_ENV_ELK)
        missing = webhook_env or DEFAULT_WEBHOOK_ENV_ELK

    if not url:
        return False, f"未配置环境变量 {missing}"
    if not alerts:
        return False, "无告警"

    payload = _build_payload(url, alerts, title=alert_title)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
        if _is_wecom_webhook(url):
            data = json.loads(body)
            if data.get("errcode") == 0:
                return True, "企业微信发送成功"
            return False, f"企业微信返回 errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
        return True, "Webhook 发送成功"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        return False, f"HTTP {e.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return False, str(e)


def should_send_notify(
    cli_notify: bool,
    dry_run: bool,
    *,
    webhook_env: str | None = None,
    channel: str = "elk",
) -> bool:
    if dry_run:
        return False
    if cli_notify:
        return True
    if channel == "ws":
        return resolve_webhook_url_ws(webhook_env) is not None
    return resolve_webhook_url(webhook_env or DEFAULT_WEBHOOK_ENV_ELK) is not None
