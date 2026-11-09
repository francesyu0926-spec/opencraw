#!/usr/bin/env python3
"""打印 ELK 子任务：id、计划开始、预计结束、ES index（log_index_pattern）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cron_task_monitor.config_loader import load_config


def main() -> int:
    p = argparse.ArgumentParser(description="列出 cron_tasks.yaml 中 ELK 子任务")
    p.add_argument(
        "-c",
        "--config",
        default="config/cron_tasks.yaml",
        help="任务配置路径",
    )
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        cfg_path = ROOT / args.config
    cfg = load_config(cfg_path)

    rows = [
        {
            "id": t.id,
            "name": t.name,
            "scheduled_start": t.scheduled_start,
            "expected_end": t.expected_end,
            "index": t.log_index_pattern,
            "server": t.server,
        }
        for t in cfg.tasks
    ]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    id_w = max(len(r["id"]) for r in rows) if rows else 8
    idx_w = max(len(r["index"]) for r in rows) if rows else 20
    print(f"时区: {cfg.timezone}")
    print(
        f"{'id':<{id_w}}  {'开始':<8} {'预计结束':<8} "
        f"{'index':<{idx_w}}  名称"
    )
    print("-" * (id_w + idx_w + 40))
    for r in rows:
        print(
            f"{r['id']:<{id_w}}  {r['scheduled_start']:<8} {r['expected_end']:<8} "
            f"{r['index']:<{idx_w}}  {r['name']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
