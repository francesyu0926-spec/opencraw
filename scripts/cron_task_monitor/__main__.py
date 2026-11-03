from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config_loader import load_config
from .elk_client import check_elasticsearch, query_task_from_elk
from .elk_query import build_task_search_body
from .evaluator import evaluate_task
from .models import Alert, TaskRunRecord
from .notifier import send_webhook

MONITOR_MODE = "elk"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="§2.1 定时任务监控（仅 Elasticsearch，不读任务机本地日志）",
    )
    p.add_argument(
        "-c",
        "--config",
        default="config/cron_tasks.yaml",
        help="任务配置文件路径",
    )
    p.add_argument(
        "--task",
        action="append",
        dest="task_ids",
        help="仅检查指定 task id，可重复",
    )
    p.add_argument(
        "--at",
        help="模拟当前时间 ISO8601（用于测试），如 2025-11-03T01:06:00+08:00",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="JSON 输出（供 ELK / 调度系统采集）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="不发送 Webhook",
    )
    p.add_argument(
        "--notify",
        action="store_true",
        help="有告警时 POST ALERT_WEBHOOK_URL",
    )
    p.add_argument(
        "--check-elk",
        action="store_true",
        help="检测 Elasticsearch 连通性与认证（不执行任务监控）",
    )
    p.add_argument(
        "--print-elk-query",
        action="store_true",
        help="打印 ES 查询 JSON（bool + match(msg)），不发起请求",
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


def _fetch_elk_record(cfg, task, now: datetime) -> TaskRunRecord:
    elk_rec = query_task_from_elk(cfg, task, now)
    if elk_rec is not None:
        return elk_rec
    record = TaskRunRecord(task_id=task.id, source="elk", status="missing_log")
    record.raw_messages.append("未配置 Elasticsearch 或缺少 log_index_pattern")
    return record


def run_monitor(args: argparse.Namespace) -> int:
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
    tasks = [t for t in cfg.tasks if not selected or t.id in selected]
    if args.print_elk_query:
        out = {
            task.id: {
                "index": task.log_index_pattern,
                "body": build_task_search_body(cfg, task),
            }
            for task in tasks
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    now = _resolve_now(cfg.timezone, args.at)

    if not tasks:
        print("no tasks matched", file=sys.stderr)
        return 2

    all_alerts: list[Alert] = []
    report_rows: list[dict] = []

    for task in tasks:
        record = _fetch_elk_record(cfg, task, now)
        alerts = evaluate_task(cfg, task, record, now, monitor_mode=MONITOR_MODE)
        all_alerts.extend(alerts)
        report_rows.append(
            {
                "task_id": task.id,
                "task_name": task.name,
                "scheduled_start": task.scheduled_start,
                "expected_end": task.expected_end,
                "log_index": task.log_index_pattern,
                "started_at": record.started_at.isoformat() if record.started_at else None,
                "ended_at": record.ended_at.isoformat() if record.ended_at else None,
                "status": record.status,
                "source": record.source,
                "alerts": [
                    {
                        "kind": a.kind.value,
                        "severity": a.severity,
                        "message": a.message,
                        "notify": a.notify,
                    }
                    for a in alerts
                ],
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "checked_at": now.isoformat(),
                    "timezone": cfg.timezone,
                    "mode": MONITOR_MODE,
                    "alert_count": len(all_alerts),
                    "tasks": report_rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"checked_at={now.isoformat()} tasks={len(tasks)} alerts={len(all_alerts)}")
        for row in report_rows:
            flag = "OK" if not row["alerts"] else "ALERT"
            print(
                f"[{flag}] {row['task_id']} status={row['status']} "
                f"start={row['started_at']} end={row['ended_at']}"
            )
            for a in row["alerts"]:
                print(f"    ! {a['severity']} {a['kind']}: {a['message']}")

    if all_alerts and args.notify and not args.dry_run:
        send_webhook(all_alerts)

    return 1 if all_alerts else 0


def main() -> None:
    sys.exit(run_monitor(_parse_args()))


if __name__ == "__main__":
    main()
