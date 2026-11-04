from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml


@dataclass(frozen=True)
class NotifySuccessTrial:
    """Temporary policy: send WeCom when jobs succeed (e.g. on the hour for 7 days)."""

    enabled: bool = False
    on_hour_only: bool = True
    until: str | None = None  # YYYY-MM-DD in schedule timezone (inclusive)


@dataclass(frozen=True)
class ScheduledJob:
    id: str
    enabled: bool
    interval_minutes: int
    config: str
    description: str = ""
    active_start: str | None = None
    active_end: str | None = None


@dataclass(frozen=True)
class MonitorScheduleConfig:
    timezone: str
    dispatcher_interval_minutes: int
    jobs: dict[str, ScheduledJob]
    notify_success_trial: NotifySuccessTrial | None = None


def _parse_notify_success_trial(data: dict) -> NotifySuccessTrial | None:
    raw = data.get("notify_success_trial")
    if not isinstance(raw, dict):
        return None
    until = raw.get("until")
    return NotifySuccessTrial(
        enabled=bool(raw.get("enabled", False)),
        on_hour_only=bool(raw.get("on_hour_only", True)),
        until=str(until).strip() if until else None,
    )


def notify_success_trial_active(
    now: datetime,
    trial: NotifySuccessTrial | None,
) -> bool:
    if trial is None or not trial.enabled:
        return False
    if trial.on_hour_only and now.minute != 0:
        return False
    if trial.until:
        try:
            end = date.fromisoformat(trial.until.strip())
        except ValueError:
            return False
        if now.date() > end:
            return False
    return True


def load_monitor_schedule(path: str | Path) -> MonitorScheduleConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("monitor schedule must be a mapping")

    jobs_raw = data.get("jobs") or {}
    if not isinstance(jobs_raw, dict):
        raise ValueError("jobs must be a mapping")

    jobs: dict[str, ScheduledJob] = {}
    for job_id, item in jobs_raw.items():
        if not isinstance(item, dict):
            raise ValueError(f"job {job_id!r} must be a mapping")
        sched = item.get("schedule") or {}
        active_start = item.get("active_start") or sched.get("active_start")
        active_end = item.get("active_end") or sched.get("active_end")
        jobs[job_id] = ScheduledJob(
            id=str(job_id),
            enabled=bool(item.get("enabled", True)),
            interval_minutes=max(1, int(item.get("interval_minutes") or 5)),
            config=str(item.get("config") or "").strip(),
            description=str(item.get("description") or "").strip(),
            active_start=str(active_start).strip() if active_start else None,
            active_end=str(active_end).strip() if active_end else None,
        )

    tz_name = str(data.get("timezone") or "Asia/Shanghai").strip()
    return MonitorScheduleConfig(
        timezone=tz_name,
        dispatcher_interval_minutes=max(
            1, int(data.get("dispatcher_interval_minutes") or 5)
        ),
        jobs=jobs,
        notify_success_trial=_parse_notify_success_trial(data),
    )
