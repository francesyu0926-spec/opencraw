from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MonitorConfig


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def _batch_bounds(cfg: MonitorConfig, now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_t = _parse_hhmm(cfg.batch_window_start or "00:00")
    end_t = _parse_hhmm(cfg.batch_window_end or "05:00")
    start_dt = datetime.combine(now.date(), start_t, tzinfo=tz)
    end_dt = datetime.combine(now.date(), end_t, tzinfo=tz)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    if now < start_dt:
        start_dt -= timedelta(days=1)
        end_dt -= timedelta(days=1)
    return start_dt, end_dt


def _widen_gte_for_task_window(
    cfg: MonitorConfig,
    ref: datetime,
    task_ids: list[str],
    query_end: datetime,
    gte_iso: str,
) -> str:
    """收尾轮评估时，gte 至少覆盖各子任务计划开始，避免 15 分钟滚动窗漏掉完成日志。"""
    if not task_ids:
        return gte_iso
    tz = ZoneInfo(cfg.timezone)
    end_dt = query_end.astimezone(tz)
    try:
        gte_dt = datetime.fromisoformat(gte_iso.replace("Z", "+00:00"))
        if gte_dt.tzinfo is None:
            gte_dt = gte_dt.replace(tzinfo=tz)
        else:
            gte_dt = gte_dt.astimezone(tz)
    except ValueError:
        return gte_iso

    from .elk_task_schedule import task_monitor_window

    by_id = {t.id: t for t in cfg.tasks}
    earliest: datetime | None = None
    for tid in task_ids:
        task = by_id.get(tid)
        if task is None:
            continue
        start, _ = task_monitor_window(cfg, task, ref)
        earliest = start if earliest is None else min(earliest, start)
    if earliest is None:
        return gte_iso

    batch_start, _ = _batch_bounds(cfg, end_dt, tz)
    widened = min(gte_dt, earliest)
    widened = max(widened, batch_start)
    return widened.isoformat()


def resolve_query_timestamp_range(
    cfg: MonitorConfig,
    ref: datetime | None = None,
    *,
    query_end: datetime | None = None,
    task_ids: list[str] | None = None,
) -> tuple[str, str]:
    """
    返回 ES @timestamp range 的 gte、lte（ISO8601，含时区偏移）。

    rolling_in_batch（默认）：在 batch_window 内，每轮只查最近 schedule_interval_minutes
    （默认 5 分钟），与 ELK 巡检间隔一致；有 task_ids 时会前扩至子任务计划开始。

    batch_window：当日 00:00 至 min(当前, 05:00)，凌晨多次跑时窗口随当前时间变长。

    elastic：使用 elasticsearch.timestamp_gte / timestamp_lte（如 now-15m、now/d）。
    """
    tz = ZoneInfo(cfg.timezone)
    ref_dt = (ref or datetime.now(tz)).astimezone(tz)
    end_dt_wall = (query_end or ref_dt).astimezone(tz)
    mode = (cfg.query_time_mode or "rolling_in_batch").strip().lower()

    if mode in ("rolling_in_batch", "rolling"):
        start_dt, end_dt = _batch_bounds(cfg, end_dt_wall, tz)
        # 批窗口外（如白天手动跑）：仍只查最近 schedule_interval 分钟
        if end_dt_wall >= end_dt:
            interval = max(1, int(cfg.schedule_interval_minutes or 15))
            rolling_start = end_dt_wall - timedelta(minutes=interval)
            return rolling_start.isoformat(), end_dt_wall.isoformat()
        # 尚未到 00:00：仍查「上一段」批窗口
        if end_dt_wall < start_dt:
            prev_start = start_dt - timedelta(days=1)
            prev_end = end_dt - timedelta(days=1)
            return prev_start.isoformat(), prev_end.isoformat()
        interval = max(1, int(cfg.schedule_interval_minutes or 15))
        rolling_start = end_dt_wall - timedelta(minutes=interval)
        gte_dt = max(start_dt, rolling_start)
        lte_dt = end_dt_wall
        gte_iso = gte_dt.isoformat()
        lte_iso = lte_dt.isoformat()
        if task_ids and ref is not None:
            gte_iso = _widen_gte_for_task_window(
                cfg, ref.astimezone(tz), task_ids, end_dt_wall, gte_iso
            )
        return gte_iso, lte_iso

    if mode == "batch_window":
        start_dt, end_dt = _batch_bounds(cfg, end_dt_wall, tz)
        lte_dt = min(end_dt_wall, end_dt) if end_dt_wall < end_dt else end_dt
        return start_dt.isoformat(), lte_dt.isoformat()

    es = cfg.elasticsearch
    gte = (es.timestamp_gte if es else None) or "now/d"
    lte = (es.timestamp_lte if es else None) or "now"
    return gte, lte
