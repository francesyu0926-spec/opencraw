from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import Alert


def format_alert_text(alerts: list[Alert]) -> str:
    lines = ["【定时任务监控告警】"]
    for a in alerts:
        lines.append(f"- [{a.severity}/{a.kind.value}] {a.task_name}({a.task_id}): {a.message}")
        if a.notify:
            lines.append(f"  通知: {a.notify}")
    return "\n".join(lines)


def send_webhook(alerts: list[Alert]) -> bool:
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url or not alerts:
        return False

    payload: dict[str, Any] = {
        "text": format_alert_text(alerts),
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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except urllib.error.URLError:
        return False
