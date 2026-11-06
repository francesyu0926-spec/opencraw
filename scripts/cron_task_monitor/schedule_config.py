from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml


@dataclass(frozen=True)
class NotifySuccessTrial:
    """On the hour, WeCom report per listed job (success or failure)."""

    enabled: bool = False
    on_hour_only: bool = True
    until: str | None = None  # YYYY-MM-DD in schedule timezone (inclusive)
    heartbeat_if_no_jobs: bool = True
    jobs: tuple[str, ...] = ()  # empty = all jobs (legacy)


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
    notify_on_run_complete: tuple[str, ...] = ()
    notify_success_until: str | None = None  # YYYY-MM-DD inclusive; after: no success WeCom


def _parse_notify_success_trial(data: dict) -> NotifySuccessTrial | None:
    raw = data.get("notify_success_trial")
    if not isinstance(raw, dict):
        return None
    until = raw.get("until")
    jobs_raw = raw.get("jobs")
    jobs: tuple[str, ...] = ()
    if isinstance(jobs_raw, list):
        jobs = tuple(str(j).strip() for j in jobs_raw if str(j).strip())
    return NotifySuccessTrial(
        enabled=bool(raw.get("enabled", False)),
        on_hour_only=bool(raw.get("on_hour_only", True)),
        until=str(until).strip() if until else None,
        heartbeat_if_no_jobs=bool(raw.get("heartbeat_if_no_jobs", True)),
        jobs=jobs,
    )


def _parse_notify_on_run_complete(data: dict) -> tuple[str, ...]:
    raw = data.get("notify_on_run_complete")
    if not isinstance(raw, list):
        return ()
    return tuple(str(j).strip() for j in raw if str(j).strip())


def is_on_hour_tick(now: datetime, *, grace_seconds: int = 45) -> bool:
    """True on clock hour (:00), including runs that finish within grace before :00."""
    if now.minute == 0:
        return True
    secs_to_next_hour = (60 - now.minute) * 60 - now.second
    return 0 < secs_to_next_hour <= grace_seconds


def _until_date(until: str | None) -> date | None:
    if not until:
        return None
    try:
        return date.fromisoformat(until.strip())
    except ValueError:
        return None


def success_wecom_allowed(now: datetime, cfg: MonitorScheduleConfig) -> bool:
    """Whether success outcomes may trigger WeCom (failures always allowed)."""
    until = cfg.notify_success_until
    end = _until_date(until)
    if end is None:
        return True
    return now.date() <= end


def notify_success_trial_active(
    now: datetime,
    trial: NotifySuccessTrial | None,
) -> bool:
    if trial is None or not trial.enabled:
        return False
    if trial.on_hour_only and not is_on_hour_tick(now):
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
    until_raw = data.get("notify_success_until")
    notify_success_until = (
        str(until_raw).strip() if until_raw is not None and str(until_raw).strip() else None
    )
    return MonitorScheduleConfig(
        timezone=tz_name,
        dispatcher_interval_minutes=max(
            1, int(data.get("dispatcher_interval_minutes") or 5)
        ),
        jobs=jobs,
        notify_success_trial=_parse_notify_success_trial(data),
        notify_on_run_complete=_parse_notify_on_run_complete(data),
        notify_success_until=notify_success_until,
    )
