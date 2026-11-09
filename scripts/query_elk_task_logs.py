#!/usr/bin/env python3
"""按任务关键词查询 Elasticsearch 当日（或指定日）日志。

用法（容器内 /app 为工作目录）::

    python scripts/query_elk_task_logs.py NC_TQ_SK_XDRY
    python scripts/query_elk_task_logs.py NC_TQ_SK_XDRY --date 2026-11-09

宿主机::

    docker exec opencraw-monitor python scripts/query_elk_task_logs.py NC_TQ_SK_XDRY
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elasticsearch_settings import auth_headers, resolve_elasticsearch
from scripts.cron_task_monitor.env_file import load_all_monitor_env_files
from scripts.cron_task_monitor.models import TaskDefinition
from scripts.cron_task_monitor.quotes_es import default_indices


def _keywords_for_task(cfg_tasks: list[TaskDefinition], task_id: str) -> list[str]:
    for t in cfg_tasks:
        if t.id == task_id or task_id in (t.name,):
            out = [t.id]
            if t.name and t.name not in out:
                out.append(t.name)
            return out
    return [task_id]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="查询 ES 中含任务关键词的日志")
    p.add_argument(
        "keyword",
        nargs="?",
        default="NC_TQ_SK_XDRY",
        help="任务 ID 或中文名（默认 NC_TQ_SK_XDRY）",
    )
    p.add_argument(
        "--config",
        default="config/cron_tasks.yaml",
        help="监控任务配置",
    )
    p.add_argument(
        "--date",
        default="",
        help="日期 YYYY-MM-DD（默认当天 Asia/Shanghai）",
    )
    p.add_argument("--size", type=int, default=100, help="最多返回条数")
    args = p.parse_args(argv)

    load_all_monitor_env_files()
    cfg = load_config(args.config)
    settings = resolve_elasticsearch(cfg)
    if not settings:
        print("未配置 Elasticsearch（elk.env / cron_tasks.yaml）", file=sys.stderr)
        return 2
    if not settings.password and not __import__("os").environ.get("ELASTICSEARCH_API_KEY"):
        print("未设置 ELASTICSEARCH_PASSWORD", file=sys.stderr)
        return 2

    tz = ZoneInfo(cfg.timezone)
    if args.date:
        day = date.fromisoformat(args.date)
    else:
        day = datetime.now(tz).date()
    day_start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz).isoformat()

    keywords = _keywords_for_task(cfg.tasks, args.keyword)
    field = (cfg.elasticsearch.message_field if cfg.elasticsearch else None) or "msg"
    indices = default_indices(cfg)

    should = [{"match_phrase": {field: kw}} for kw in keywords if kw]
    body = {
        "query": {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": day_start,
                                "lte": "now",
                                "time_zone": cfg.timezone,
                            }
                        }
                    }
                ],
            }
        },
        "size": max(1, min(args.size, 1000)),
        "sort": [{"@timestamp": {"order": "asc"}}],
        "track_total_hits": True,
    }

    url = settings.url.rstrip("/") + "/" + ",".join(indices) + "/_search"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=auth_headers(settings),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:600]}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"连接 ES 失败: {e}", file=sys.stderr)
        return 1

    hits = result.get("hits", {})
    total = hits.get("total", {})
    n = total.get("value", total) if isinstance(total, dict) else int(total or 0)
    rows = hits.get("hits") or []

    print(f"date={day.isoformat()} keywords={keywords}")
    print(f"indices={','.join(indices)}")
    print(f"total_hits={n} shown={len(rows)}")
    for i, h in enumerate(rows):
        src = h.get("_source") or {}
        ts = src.get("@timestamp", "")
        msg = src.get(field) or src.get("message") or ""
        idx = h.get("_index", "")
        print(f"\n--- [{i + 1}] {idx} {ts} ---")
        print(str(msg)[:800])

    return 0 if n > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
