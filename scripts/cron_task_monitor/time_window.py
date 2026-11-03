from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import MonitorConfig


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def resolve_query_timestamp_range(
    cfg: MonitorConfig,
    ref: datetime | None = None,
) -> tuple[str, str]:
    """
    返回 ES @timestamp range 的 gte、lte（ISO8601，含时区偏移）。

    batch_window：配置时区下「当日 00:00–05:00」；若 ref 仍在该窗口内，lte 为 ref（便于凌晨多次巡检）。
    否则使用 elasticsearch.timestamp_gte / timestamp_lte（如 now/d、now）。
    """
    tz = ZoneInfo(cfg.timezone)
    now = (ref or datetime.now(tz)).astimezone(tz)

    mode = (cfg.query_time_mode or "batch_window").strip().lower()
    if mode == "batch_window":
        start_t = _parse_hhmm(cfg.batch_window_start or "00:00")
        end_t = _parse_hhmm(cfg.batch_window_end or "05:00")
        start_dt = datetime.combine(now.date(), start_t, tzinfo=tz)
        end_dt = datetime.combine(now.date(), end_t, tzinfo=tz)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if now < start_dt:
            start_dt -= timedelta(days=1)
            end_dt -= timedelta(days=1)
        lte_dt = min(now, end_dt) if now < end_dt else end_dt
        return start_dt.isoformat(), lte_dt.isoformat()

    es = cfg.elasticsearch
    gte = (es.timestamp_gte if es else None) or "now/d"
    lte = (es.timestamp_lte if es else None) or "now"
    return gte, lte
