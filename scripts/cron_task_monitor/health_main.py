from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .env_file import load_health_monitor_env_files
from .health_config import load_health_config
from .health_probe import run_health_probe
from .models import Alert, AlertKind
from .notifier import send_webhook, should_send_notify


def run_health_monitor(
    config_path: Path,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
) -> int:
    load_health_monitor_env_files()

    if not config_path.is_file():
        print(f"health config not found: {config_path}", file=sys.stderr)
        return 2

    cfg = load_health_config(config_path)
    tz = ZoneInfo(cfg.timezone)
    if at:
        now = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        else:
            now = now.astimezone(tz)
    else:
        now = datetime.now(tz)

    result = run_health_probe(cfg)
    alerts: list[Alert] = []

    if not result.ok:
        msg = result.error or "行情 health 探活失败"
        alerts.append(
            Alert(
                kind=AlertKind.HEALTH_CHECK_FAILED,
                task_id="quotes-health",
                task_name="行情 API Health",
                message=f"{msg}（url={cfg.url}）",
                notify=cfg.notify or "on-call",
                severity="critical",
            )
        )

    notify_ok = None
    notify_msg = ""
    if alerts and not no_notify and should_send_notify(
        notify,
        dry_run,
        webhook_env=cfg.wecom_webhook_env,
        channel="health",
    ):
        notify_ok, notify_msg = send_webhook(
            alerts,
            webhook_env=cfg.wecom_webhook_env,
            channel="health",
            alert_title="【行情 API Health 告警】",
        )

    if as_json:
        out = {
            "checked_at": now.isoformat(),
            "mode": "health_monitor",
            "ok": result.ok,
            "http_status": result.http_status,
            "root_status": result.root_status,
            "check_count": result.check_count,
            "down_checks": result.down_checks,
            "error": result.error,
            "alert_count": len(alerts),
            "alerts": [{"message": a.message} for a in alerts],
        }
        if notify_ok is not None:
            out["wecom_notify"] = notify_ok
            out["wecom_message"] = notify_msg
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if result.ok:
            print(
                f"ok url={cfg.url} root={result.root_status} "
                f"checks={result.check_count}"
            )
        else:
            print(f"FAIL {result.error}")
        for a in alerts:
            print(f"! {a.message}")
        if notify_ok is not None:
            print(f"wecom_notify={'ok' if notify_ok else 'fail'} {notify_msg}")

    return 1 if alerts else 0
