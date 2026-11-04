from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config_loader import load_config
from .elk_client import check_elasticsearch
from .mdimonitor_checks import run_mdimonitor_checks
from .models import Alert, AlertKind
from .notifier import send_webhook, should_send_notify
from .quote_utils import msg_keywords_from_config
from .quotes_es import build_query_from_config, default_indices, search_hits

MONITOR_MODE = "elk"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="§2.1 定时任务监控（mdimonitor/test_quotes_es 逻辑，仅 ELK）",
    )
    p.add_argument("-c", "--config", default="config/cron_tasks.yaml")
    p.add_argument("--task", action="append", dest="task_ids")
    p.add_argument("--at", help="模拟当前时间 ISO8601")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--notify",
        action="store_true",
        help="有告警时发企业微信（已配置 WECOM_WEBHOOK_URL 时默认也会发）",
    )
    p.add_argument(
        "--no-notify",
        action="store_true",
        help="不发送企业微信",
    )
    p.add_argument("--check-elk", action="store_true")
    p.add_argument("--print-elk-query", action="store_true")
    p.add_argument(
        "--ws-monitor",
        action="store_true",
        help="§2.2 WebSocket 探活（见 config/ws_monitor.yaml）",
    )
    p.add_argument(
        "--ws-config",
        default="config/ws_monitor.yaml",
        help="WebSocket 监控配置",
    )
    p.add_argument(
        "--ws-daemon",
        action="store_true",
        help="§2.2 WebSocket 长驻探活（每 interval_seconds 一轮，对齐 mdimonitor schedule_task）",
    )
    p.add_argument(
        "--health-monitor",
        action="store_true",
        help="行情 API health 探活（见 config/health_monitor.yaml）",
    )
    p.add_argument(
        "--health-config",
        default="config/health_monitor.yaml",
        help="Health API 监控配置",
    )
    p.add_argument(
        "--writing-monitor",
        action="store_true",
        help="自动化写稿任务验证（见 config/writing_monitor.yaml）",
    )
    p.add_argument(
        "--writing-config",
        default="config/writing_monitor.yaml",
        help="写稿监测配置",
    )
    p.add_argument(
        "--run-scheduled",
        action="store_true",
        help="按 config/monitor_schedule.yaml 执行到期监控（HTTP / WS / ELK）",
    )
    p.add_argument(
        "--schedule-config",
        default="config/monitor_schedule.yaml",
        help="统一调度配置",
    )
    p.add_argument(
        "--job",
        action="append",
        dest="job_ids",
        help="仅运行指定 job（health / ws / elk / writing），可重复",
    )
    p.add_argument(
        "--force-scheduled",
        action="store_true",
        help="忽略时刻表，运行所有已启用的 job（配合 --job 可只跑部分）",
    )
    p.add_argument(
        "--notify-success",
        action="store_true",
        help="（可选）每轮全部 job 成功时发 ELK 企微汇总；整点成功见 monitor_schedule notify_success_trial",
    )
    return p.parse_args()


def _resolve_now(cfg_tz: str, at: str | None) -> datetime:
    tz = ZoneInfo(cfg_tz)
    if at:
        dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    return datetime.now(tz)


def run_monitor(args: argparse.Namespace) -> int:
    if args.run_scheduled:
        from .schedule_runner import run_scheduled_monitors

        job_filter = set(args.job_ids or []) or None
        return run_scheduled_monitors(
            Path(args.schedule_config),
            at=args.at,
            as_json=args.json,
            dry_run=args.dry_run,
            notify=args.notify,
            no_notify=args.no_notify,
            job_filter=job_filter,
            force=args.force_scheduled,
            notify_success=args.notify_success,
        )

    if args.health_monitor:
        from .health_main import run_health_monitor

        return run_health_monitor(
            Path(args.health_config),
            at=args.at,
            as_json=args.json,
            dry_run=args.dry_run,
            notify=args.notify,
            no_notify=args.no_notify,
        )

    if args.writing_monitor:
        from .writing_main import run_writing_monitor

        return run_writing_monitor(
            Path(args.writing_config),
            at=args.at,
            as_json=args.json,
            dry_run=args.dry_run,
            notify=args.notify,
            no_notify=args.no_notify,
        )

    if args.ws_daemon:
        from .ws_config import load_ws_config
        from .ws_probe import run_ws_daemon

        path = Path(args.ws_config)
        if not path.is_file():
            print(f"ws config not found: {path}", file=sys.stderr)
            return 2
        run_ws_daemon(load_ws_config(path))
        return 0

    if args.ws_monitor:
        from .ws_main import run_ws_monitor

        return run_ws_monitor(
            Path(args.ws_config),
            at=args.at,
            as_json=args.json,
            dry_run=args.dry_run,
            notify=args.notify,
            no_notify=args.no_notify,
        )

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 2

    cfg = load_config(config_path)

    if args.check_elk:
        ok, msg = check_elasticsearch(cfg)
        if args.json:
            print(json.dumps({"elk_ok": ok, "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return 0 if ok else 1

    selected = set(args.task_ids or [])
    keywords = msg_keywords_from_config(cfg, selected or None)

    now = _resolve_now(cfg.timezone, args.at)

    if args.print_elk_query:
        from .time_window import resolve_query_timestamp_range

        gte, lte = resolve_query_timestamp_range(cfg, now)
        print(
            json.dumps(
                {
                    "index": default_indices(cfg),
                    "query_time_range": {"gte": gte, "lte": lte, "timezone": cfg.timezone},
                    "body": build_query_from_config(cfg, keywords, now),
                    "msg_keywords": keywords,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not keywords:
        print("no tasks matched", file=sys.stderr)
        return 2

    hits, err = search_hits(cfg, keywords, now)

    if err:
        alerts: list[Alert] = [
            Alert(
                kind=AlertKind.MISSING_LOG,
                task_id="",
                task_name="",
                message=f"ELK 查询失败: {err}",
                notify="on-call",
                severity="critical",
            )
        ]
        hit_count = 0
    else:
        alerts = run_mdimonitor_checks(cfg, hits, keywords, now)
        hit_count = len(hits)

    notify_ok: bool | None = None
    notify_msg = ""
    if alerts and not args.no_notify and should_send_notify(
        args.notify,
        args.dry_run,
        webhook_env=cfg.wecom_webhook_env,
        channel="elk",
    ):
        notify_ok, notify_msg = send_webhook(
            alerts,
            webhook_env=cfg.wecom_webhook_env,
            channel="elk",
        )

    if args.json:
        payload: dict = {
            "checked_at": now.isoformat(),
            "timezone": cfg.timezone,
            "mode": MONITOR_MODE,
            "hit_count": hit_count,
            "alert_count": len(alerts),
            "alerts": [
                {
                    "kind": a.kind.value,
                    "severity": a.severity,
                    "message": a.message,
                }
                for a in alerts
            ],
        }
        if notify_ok is not None:
            payload["wecom_notify"] = notify_ok
            payload["wecom_message"] = notify_msg
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"checked_at={now.isoformat()} hits={hit_count} alerts={len(alerts)}"
        )
        for a in alerts:
            print(f"! {a.severity} {a.kind.value}: {a.message}")
        if notify_ok is not None:
            print(f"wecom_notify={'ok' if notify_ok else 'fail'} {notify_msg}")

    return 1 if alerts else 0


def main() -> None:
    sys.exit(run_monitor(_parse_args()))


if __name__ == "__main__":
    main()
