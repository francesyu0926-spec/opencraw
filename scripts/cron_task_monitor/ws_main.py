from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Alert, AlertKind
from .notifier import send_webhook, should_send_notify
from .ws_config import load_ws_config
from .ws_probe import run_ws_probe


def run_ws_monitor(
    config_path: Path,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
) -> int:
    if not config_path.is_file():
        print(f"ws config not found: {config_path}", file=sys.stderr)
        return 2

    cfg = load_ws_config(config_path)
    tz = ZoneInfo(cfg.timezone)
    if at:
        now = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        else:
            now = now.astimezone(tz)
    else:
        now = datetime.now(tz)

    result = run_ws_probe(cfg, now)
    alerts: list[Alert] = []

    if result.skipped:
        pass
    elif not result.ok:
        msg = result.error or "WebSocket 探活失败"
        alerts.append(
            Alert(
                kind=AlertKind.WS_PROBE_FAILED,
                task_id="ws-quote",
                task_name="WebSocket 行情探活",
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
        channel="ws",
    ):
        notify_ok, notify_msg = send_webhook(
            alerts,
            webhook_env=cfg.wecom_webhook_env,
            channel="ws",
            alert_title="【WebSocket 行情探活告警】",
        )

    if as_json:
        out = {
            "checked_at": now.isoformat(),
            "mode": "ws_monitor",
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "ok": result.ok and not result.skipped or (result.skipped and not alerts),
            "connected": result.connected,
            "hold_seconds": result.hold_seconds,
            "messages_received": result.messages_received,
            "quote_items_ok": result.quote_items_ok,
            "error": result.error,
            "alert_count": len(alerts),
            "alerts": [{"message": a.message} for a in alerts],
        }
        if notify_ok is not None:
            out["wecom_notify"] = notify_ok
            out["wecom_message"] = notify_msg
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if result.skipped:
            print(f"skipped: {result.skip_reason}")
        elif result.ok:
            print(
                f"ok url={cfg.url} hold={result.hold_seconds}s "
                f"messages={result.messages_received}"
            )
        else:
            print(f"FAIL {result.error}")
        for a in alerts:
            print(f"! {a.message}")
        if notify_ok is not None:
            print(f"wecom_notify={'ok' if notify_ok else 'fail'} {notify_msg}")

    if result.skipped:
        return 0
    return 1 if alerts else 0
