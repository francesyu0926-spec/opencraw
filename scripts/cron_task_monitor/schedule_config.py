from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


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

    return MonitorScheduleConfig(
        timezone=str(data.get("timezone") or "Asia/Shanghai").strip(),
        dispatcher_interval_minutes=max(
            1, int(data.get("dispatcher_interval_minutes") or 5)
        ),
        jobs=jobs,
    )
