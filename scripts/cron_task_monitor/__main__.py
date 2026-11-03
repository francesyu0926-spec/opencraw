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
from .notifier import send_webhook
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
    p.add_argument("--notify", action="store_true")
    p.add_argument("--check-elk", action="store_true")
    p.add_argument("--print-elk-query", action="store_true")
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

    if args.print_elk_query:
        print(
            json.dumps(
                {
                    "index": default_indices(cfg),
                    "body": build_query_from_config(cfg, keywords),
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

    now = _resolve_now(cfg.timezone, args.at)
    hits, err = search_hits(cfg, keywords)

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

    if args.json:
        print(
            json.dumps(
                {
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
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"checked_at={now.isoformat()} hits={hit_count} alerts={len(alerts)}"
        )
        for a in alerts:
            print(f"! {a.severity} {a.kind.value}: {a.message}")

    if alerts and args.notify and not args.dry_run:
        send_webhook(alerts)

    return 1 if alerts else 0


def main() -> None:
    sys.exit(run_monitor(_parse_args()))


if __name__ == "__main__":
    main()
