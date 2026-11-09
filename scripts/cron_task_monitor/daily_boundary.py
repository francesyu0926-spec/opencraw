from __future__ import annotations

from datetime import datetime, time

from .schedule_config import ScheduledJob


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(x) for x in value.strip().split(":", 1))
    return time(hour, minute)


def _in_active_window(now: datetime, start_hhmm: str | None, end_hhmm: str | None) -> bool:
    if not start_hhmm and not end_hhmm:
        return True
    start_t = _parse_hhmm(start_hhmm or "00:00")
    end_t = _parse_hhmm(end_hhmm or "23:59")
    t = now.time().replace(second=0, microsecond=0)
    if start_t <= end_t:
        return start_t <= t <= end_t
    return t >= start_t or t <= end_t


def _minute_of_day(now: datetime) -> int:
    return now.hour * 60 + now.minute


def _due_slot_minutes(job: ScheduledJob) -> list[int]:
    """Canonical due minutes (interval-aligned) within active window."""
    if not job.enabled:
        return []
    interval = max(1, job.interval_minutes)
    start = job.active_start or "00:00"
    end = job.active_end or "23:59"
    start_t = _parse_hhmm(start)
    end_t = _parse_hhmm(end)
    start_m = start_t.hour * 60 + start_t.minute
    end_m = end_t.hour * 60 + end_t.minute

    due: list[int] = []
    for m in range(24 * 60):
        t = time(m // 60, m % 60)
        if start_t <= end_t:
            if not (start_t <= t <= end_t):
                continue
        else:
            if not (t >= start_t or t <= end_t):
                continue
        if m % interval == 0:
            due.append(m)
    return due


def scheduled_slot_minute(now: datetime, interval_minutes: int) -> int:
    """Align current time to the job interval slot (matches catch-up runs)."""
    interval = max(1, interval_minutes)
    m = _minute_of_day(now)
    return (m // interval) * interval


def minute_of_day(now: datetime) -> int:
    return now.hour * 60 + now.minute


def is_before_first_daily_slot(now: datetime, job: ScheduledJob) -> bool:
    """当日首个计划时刻之前（相对 interval 对齐的 due 列表）。"""
    slots = _due_slot_minutes(job)
    if not slots:
        return False
    return minute_of_day(now) < slots[0]


def is_after_last_daily_slot(now: datetime, job: ScheduledJob) -> bool:
    """当日末个计划时刻之后。"""
    slots = _due_slot_minutes(job)
    if not slots:
        return False
    return minute_of_day(now) > slots[-1]


def daily_boundary_kind(now: datetime, job: ScheduledJob) -> str | None:
    """
    Return 'first' or 'last' if `now` is the first/last due slot of the day for this job.
    """
    if not job.enabled or not _in_active_window(
        now, job.active_start, job.active_end
    ):
        return None
    slots = _due_slot_minutes(job)
    if not slots:
        return None
    slot = scheduled_slot_minute(now, job.interval_minutes)
    if slot not in slots:
        return None
    if slot == slots[0]:
        return "first"
    if slot == slots[-1]:
        return "last"
    return None
