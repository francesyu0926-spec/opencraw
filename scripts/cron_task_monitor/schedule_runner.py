from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .env_file import load_all_monitor_env_files
from .schedule_config import ScheduledJob, load_monitor_schedule


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


def is_job_due(now: datetime, job: ScheduledJob) -> bool:
    if not job.enabled:
        return False
    if not _in_active_window(now, job.active_start, job.active_end):
        return False
    minute_of_day = now.hour * 60 + now.minute
    return minute_of_day % job.interval_minutes == 0


def _resolve_now(tz_name: str, at: str | None) -> datetime:
    tz = ZoneInfo(tz_name)
    if at:
        dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    return datetime.now(tz)


def _run_single_job(
    job: ScheduledJob,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
) -> tuple[int, str | None]:
    config_path = Path(job.config)
    if job.id == "health":
        from .health_main import run_health_monitor

        runner = run_health_monitor
    elif job.id == "ws":
        from .ws_main import run_ws_monitor

        runner = run_ws_monitor
    elif job.id == "elk":
        from . import __main__ as monitor_main

        def runner(path: Path, **kwargs):  # type: ignore[misc]
            args = argparse.Namespace(
                health_monitor=False,
                ws_monitor=False,
                ws_daemon=False,
                ws_config="config/ws_monitor.yaml",
                health_config="config/health_monitor.yaml",
                config=str(path),
                task_ids=None,
                at=kwargs.get("at"),
                json=kwargs.get("as_json", False),
                dry_run=kwargs.get("dry_run", False),
                notify=kwargs.get("notify", False),
                no_notify=kwargs.get("no_notify", False),
                check_elk=False,
                print_elk_query=False,
                run_scheduled=False,
                schedule_config="config/monitor_schedule.yaml",
                job_ids=None,
                force_scheduled=False,
            )
            return monitor_main.run_monitor(args)

    else:
        return 2, None

    if dry_run:
        return 0, None

    if as_json:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = runner(
                config_path,
                at=at,
                as_json=True,
                dry_run=False,
                notify=notify,
                no_notify=no_notify,
            )
        return code, buf.getvalue().strip() or None

    code = runner(
        config_path,
        at=at,
        as_json=False,
        dry_run=False,
        notify=notify,
        no_notify=no_notify,
    )
    return code, None


def run_scheduled_monitors(
    schedule_path: Path,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
    job_filter: set[str] | None = None,
    force: bool = False,
) -> int:
    if not schedule_path.is_file():
        print(f"schedule config not found: {schedule_path}", file=sys.stderr)
        return 2

    load_all_monitor_env_files(anchor=schedule_path)
    cfg = load_monitor_schedule(schedule_path)
    now = _resolve_now(cfg.timezone, at)

    results: dict[str, dict] = {}
    skipped: list[dict[str, str]] = []
    exit_code = 0

    for job_id, job in cfg.jobs.items():
        if job_filter and job_id not in job_filter:
            continue
        if not job.enabled:
            skipped.append({"job": job_id, "reason": "disabled"})
            continue
        due = force or is_job_due(now, job)
        if not due:
            skipped.append({"job": job_id, "reason": "not_due"})
            continue
        if not job.config:
            results[job_id] = {"exit_code": 2, "error": "missing config path"}
            exit_code = max(exit_code, 2)
            continue

        code, captured = _run_single_job(
            job,
            at=at,
            as_json=as_json,
            dry_run=dry_run,
            notify=notify,
            no_notify=no_notify,
        )
        entry: dict = {"exit_code": code, "description": job.description}
        if captured:
            try:
                entry["detail"] = json.loads(captured)
            except json.JSONDecodeError:
                entry["detail_raw"] = captured
        results[job_id] = entry
        if code != 0:
            exit_code = max(exit_code, code if code > 0 else 1)

    if as_json:
        payload = {
            "checked_at": now.isoformat(),
            "timezone": cfg.timezone,
            "mode": "scheduled_monitor",
            "dispatcher_interval_minutes": cfg.dispatcher_interval_minutes,
            "dry_run": dry_run,
            "force": force,
            "jobs_run": list(results.keys()),
            "jobs_skipped": skipped,
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"checked_at={now.isoformat()} run={list(results.keys())} "
            f"skipped={len(skipped)}"
        )
        for jid, info in results.items():
            print(f"  {jid}: exit={info['exit_code']}")
        for item in skipped:
            print(f"  skip {item['job']}: {item['reason']}")

    return exit_code
