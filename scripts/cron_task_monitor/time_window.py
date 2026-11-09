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


def resolve_query_timestamp_range(
    cfg: MonitorConfig,
    ref: datetime | None = None,
    *,
    query_end: datetime | None = None,
) -> tuple[str, str]:
    """
    返回 ES @timestamp range 的 gte、lte（ISO8601，含时区偏移）。

    rolling_in_batch（默认）：在 batch_window 内，每轮只查最近 schedule_interval_minutes
    （默认 15 分钟），与「0–5 点每 15 分钟跑一次」一致。

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
        return gte_dt.isoformat(), lte_dt.isoformat()

    if mode == "batch_window":
        start_dt, end_dt = _batch_bounds(cfg, end_dt_wall, tz)
        lte_dt = min(end_dt_wall, end_dt) if end_dt_wall < end_dt else end_dt
        return start_dt.isoformat(), lte_dt.isoformat()

    es = cfg.elasticsearch
    gte = (es.timestamp_gte if es else None) or "now/d"
    lte = (es.timestamp_lte if es else None) or "now"
    return gte, lte
