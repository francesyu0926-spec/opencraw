#!/usr/bin/env python3
"""Print opencraw monitor schedules (production config)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automated_writing"))

from verify.tasks import TASKS  # noqa: E402


def main() -> None:
    prod = yaml.safe_load(
        (ROOT / "config/monitor_schedule.production.yaml").read_text(encoding="utf-8")
    )
    cron = yaml.safe_load((ROOT / "config/cron_tasks.yaml").read_text(encoding="utf-8"))
    ws = yaml.safe_load((ROOT / "config/ws_monitor.yaml").read_text(encoding="utf-8"))

    print("=== 调度器 (Docker 默认 monitor_schedule.production.yaml) ===")
    print(f"时区: {prod['timezone']}")
    print(
        f"调度器触发: 每 {prod['dispatcher_interval_minutes']} 分钟 "
        "（墙钟对齐 :00/:05/:10/...）"
    )
    trial = prod.get("notify_success_trial") or {}
    if trial.get("enabled"):
        tjobs = trial.get("jobs") or "全部 job"
        trial_until = trial.get("until") or "长期"
        print(
            f"企微整点: 每 :00，{trial_until}，job={tjobs} "
            "（成功/失败均发；无 job 时 health 通道心跳）"
        )
    on_run = prod.get("notify_on_run_complete") or []
    if on_run:
        print(f"企微每次执行完: {', '.join(on_run)}（失败必发；成功受 notify_success_until 约束）")
    until_all = prod.get("notify_success_until")
    if until_all:
        print(
            f"成功企微截止: {until_all}（之后 health/ws 整点与 ELK/写稿跑完均仅失败发）"
        )
    print(
        "企微日界: health / ws 每天 **首次** 与 **末次** 执行各发一条（成败均发；"
        "与整点重复时只发整点一条）"
    )
    print()

    print("=== 四大监控 Job ===")
    for jid, j in prod["jobs"].items():
        start = j.get("active_start") or "全天"
        end = j.get("active_end") or "全天"
        en = "启用" if j.get("enabled", True) else "停用"
        desc = j.get("description", "")
        print(
            f"  {jid:8} | 每 {int(j['interval_minutes']):2d} 分钟 | "
            f"{start} ~ {end} | {en} | {desc}"
        )
    print()

    overrun = int(cron.get("overrun_after_end_threshold_minutes", 10))
    bw = cron.get("batch_window") or {}
    b_start = bw.get("start", "00:00")
    b_end = bw.get("end", "05:00")
    print("=== ELK 监控（cron_tasks.yaml）===")
    print(
        f"  调度器: 在 {b_start}~{b_end} 内，每 5 分钟看是否有任务处于监控窗口；"
        "有则跑 ELK，只查这些任务"
    )
    print("  各任务监控窗口 = 计划开始 ~ 预期结束 + overrun 分钟:")
    for t in cron["tasks"]:
        print(
            f"    {t['id']:22} {t['name']:12} "
            f"执行 {t['scheduled_start']}~{t['expected_end']} | "
            f"监控至预期结束+{overrun}min"
        )
    print()

    wmon = yaml.safe_load((ROOT / "config/writing_monitor.yaml").read_text(encoding="utf-8"))
    delay = int((wmon or {}).get("execution_delay_minutes") or 10)
    w_end = (wmon or {}).get("active_end") or "20:30"
    print("=== 写稿验证（writing job）===")
    print(
        f"  每个任务：监测到点 + {delay} 分钟，在 :00/:05/:10… 对齐时刻执行 **1 次**（slot 5min）"
    )
    for t in TASKS:
        wd = "仅工作日" if t.weekdays_only else "每天"
        h, m = t.check_time.hour, t.check_time.minute + delay
        h += m // 60
        m %= 60
        print(
            f"    {t.name:10} 到点 {t.check_time.strftime('%H:%M')} → 执行约 {h:02d}:{m:02d} | {wd}"
        )
    print()

    sw = ws.get("skip_window") or {}
    print("=== WebSocket 探活补充 ===")
    print(f"  跳过窗口: {sw.get('start')} ~ {sw.get('end')}（不探活）")
    iv = int(ws.get("interval_seconds", 600)) // 60
    print(f"  单轮维持 {ws.get('hold_seconds')}s 后断连；配置间隔 {iv} 分钟")


if __name__ == "__main__":
    main()
