from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .config_loader import load_config
from .elk_task_schedule import active_elk_task_ids, is_elk_job_due
from .writing_task_schedule import is_writing_job_due
from .env_file import load_all_monitor_env_files, load_writing_monitor_env_files
from .notifier import send_markdown_message
from .wecom_format import JOB_LABELS, failure_note_for_job, monitor_report_markdown
from .wecom_diag import warn_missing_webhooks
from .schedule_config import (
    ScheduledJob,
    load_monitor_schedule,
    notify_success_trial_active,
    success_wecom_allowed,
)

_JOB_NOTIFY_CHANNEL: dict[str, str] = {
    "elk": "elk",
    "ws": "ws",
    "health": "health",
    "writing": "writing",
}


def _job_hourly_report_message(job_id: str, info: dict, now: datetime) -> str:
    code = int(info.get("exit_code", 1))
    passed = code == 0
    note = failure_note_for_job(job_id, info) if not passed else ""
    return monitor_report_markdown(
        checked_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        passed=passed,
        monitor_item=JOB_LABELS.get(job_id, job_id),
        note=note,
    )


def _run_result_skipped(info: dict) -> bool:
    detail = info.get("detail")
    if isinstance(detail, dict) and detail.get("skipped"):
        return True
    return bool(info.get("skipped"))


def _notify_job_run_reports(
    results: dict[str, dict],
    *,
    now: datetime,
    no_notify: bool,
    dry_run: bool,
    allow_success: bool = True,
) -> dict[str, dict]:
    """向各 job 对应企微发送执行结果；allow_success=False 时仅失败发送。"""
    if no_notify or dry_run or not results:
        return {}
    out: dict[str, dict] = {}
    for job_id, info in results.items():
        if _run_result_skipped(info):
            continue
        passed = int(info.get("exit_code", 1)) == 0
        if passed and not allow_success:
            continue
        channel = _JOB_NOTIFY_CHANNEL.get(job_id, "elk")
        ok_send, msg = send_markdown_message(
            _job_hourly_report_message(job_id, info, now),
            channel=channel,
        )
        out[job_id] = {
            "ok": ok_send,
            "message": msg,
            "channel": channel,
            "exit_code": int(info.get("exit_code", 1)),
        }
        if not ok_send:
            print(
                f"WARN: 企微发送失败 job={job_id} channel={channel}: {msg}",
                file=sys.stderr,
            )
    return out


def _notify_trial_hourly_reports(
    results: dict[str, dict],
    *,
    now: datetime,
    no_notify: bool,
    dry_run: bool,
    job_ids: tuple[str, ...],
    allow_success: bool = True,
) -> dict[str, dict]:
    """整点向指定 job 发送本轮结果。"""
    if not job_ids:
        filtered = results
    else:
        filtered = {k: v for k, v in results.items() if k in job_ids}
    return _notify_job_run_reports(
        filtered,
        now=now,
        no_notify=no_notify,
        dry_run=dry_run,
        allow_success=allow_success,
    )


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


def is_job_due(
    now: datetime,
    job: ScheduledJob,
    dispatcher_interval_minutes: int = 5,
) -> bool:
    """Job due on exact interval minute, or once on a dispatcher tick shortly after a missed slot."""
    if not job.enabled:
        return False
    if not _in_active_window(now, job.active_start, job.active_end):
        return False
    interval = max(1, job.interval_minutes)
    dispatcher = max(1, dispatcher_interval_minutes)
    minute_of_day = now.hour * 60 + now.minute
    remainder = minute_of_day % interval
    if remainder == 0:
        return True
    if remainder > dispatcher:
        return False
    return now.minute % dispatcher == 0


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
    elk_force_all_tasks: bool = False,
    writing_force_all: bool = False,
    suppress_job_wecom: bool = False,
) -> tuple[int, str | None]:
    config_path = Path(job.config)
    if job.id == "health":
        from .health_main import run_health_monitor

        runner = run_health_monitor
    elif job.id == "ws":
        from .ws_main import run_ws_monitor

        runner = run_ws_monitor
    elif job.id == "writing":
        from .writing_main import run_writing_monitor

        def runner(path: Path, **kwargs):  # type: ignore[misc]
            return run_writing_monitor(
                path,
                at=kwargs.get("at"),
                as_json=bool(kwargs.get("as_json", False)),
                dry_run=bool(kwargs.get("dry_run", False)),
                notify=bool(kwargs.get("notify", False)),
                no_notify=bool(kwargs.get("no_notify", False))
                or bool(kwargs.get("suppress_job_wecom", False)),
                writing_use_window=not kwargs.get("writing_force_all", False),
                writing_force_all=bool(kwargs.get("writing_force_all", False)),
            )
    elif job.id == "elk":
        from . import __main__ as monitor_main

        def runner(path: Path, **kwargs):  # type: ignore[misc]
            cron_cfg = load_config(path)
            at_val = kwargs.get("at")
            tz = ZoneInfo(cron_cfg.timezone)
            if at_val:
                probe = datetime.fromisoformat(at_val.replace("Z", "+00:00"))
                if probe.tzinfo is None:
                    probe = probe.replace(tzinfo=tz)
                else:
                    probe = probe.astimezone(tz)
            else:
                probe = datetime.now(tz)
            task_ids = active_elk_task_ids(cron_cfg, probe)
            if kwargs.get("elk_force_all_tasks"):
                task_ids = None  # --force：检全部任务（联调）
            elif not task_ids:
                if kwargs.get("as_json"):
                    print(
                        json.dumps(
                            {
                                "mode": "elk",
                                "skipped": True,
                                "reason": "no_task_in_monitor_window",
                                "checked_at": probe.isoformat(),
                            },
                            ensure_ascii=False,
                        )
                    )
                return 0
            args = monitor_main.namespace_for_elk_run(
                config=str(path),
                at=at_val,
                as_json=bool(kwargs.get("as_json", False)),
                dry_run=bool(kwargs.get("dry_run", False)),
                notify=bool(kwargs.get("notify", False)),
                no_notify=bool(kwargs.get("no_notify", False))
                or bool(kwargs.get("suppress_job_wecom", False)),
                task_ids=task_ids,
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
                elk_force_all_tasks=elk_force_all_tasks,
                writing_force_all=writing_force_all,
                suppress_job_wecom=suppress_job_wecom,
            )
        return code, buf.getvalue().strip() or None

    code = runner(
        config_path,
        at=at,
        as_json=False,
        dry_run=False,
        notify=notify,
        no_notify=no_notify,
        elk_force_all_tasks=elk_force_all_tasks,
        writing_force_all=writing_force_all,
        suppress_job_wecom=suppress_job_wecom,
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
    notify_success: bool = False,
) -> int:
    if not schedule_path.is_file():
        print(f"schedule config not found: {schedule_path}", file=sys.stderr)
        return 2

    repo_root = load_all_monitor_env_files(anchor=schedule_path)
    load_writing_monitor_env_files(repo_root=repo_root)
    cfg = load_monitor_schedule(schedule_path)
    tz = ZoneInfo(cfg.timezone)
    now = _resolve_now(cfg.timezone, at)
    elk_cron_cfg = None
    elk_job = cfg.jobs.get("elk")
    if elk_job and elk_job.config:
        elk_path = Path(elk_job.config)
        if not elk_path.is_file():
            elk_path = repo_root / elk_job.config
        if elk_path.is_file():
            elk_cron_cfg = load_config(elk_path)

    writing_cfg_path: Path | None = None
    writing_job = cfg.jobs.get("writing")
    if writing_job and writing_job.config:
        w_path = Path(writing_job.config)
        if not w_path.is_file():
            w_path = repo_root / writing_job.config
        if w_path.is_file():
            writing_cfg_path = w_path

    results: dict[str, dict] = {}
    skipped: list[dict[str, str]] = []
    exit_code = 0
    notify_on_run = set(cfg.notify_on_run_complete)
    trial_job_ids: tuple[str, ...] = ()
    if cfg.notify_success_trial and cfg.notify_success_trial.jobs:
        trial_job_ids = cfg.notify_success_trial.jobs

    for job_id, job in cfg.jobs.items():
        if job_filter and job_id not in job_filter:
            continue
        if not job.enabled:
            skipped.append({"job": job_id, "reason": "disabled"})
            continue
        if force and job_id in ("elk", "writing"):
            due = True
        elif job_id == "elk" and elk_cron_cfg is not None:
            due = is_elk_job_due(
                now,
                cron_cfg=elk_cron_cfg,
                dispatcher_interval_minutes=cfg.dispatcher_interval_minutes,
                job_enabled=job.enabled,
            )
        elif job_id == "writing" and writing_cfg_path is not None:
            due = is_writing_job_due(
                now,
                config_path=writing_cfg_path,
                repo_root=repo_root,
                dispatcher_interval_minutes=cfg.dispatcher_interval_minutes,
                job_enabled=job.enabled,
            )
        else:
            due = is_job_due(now, job, cfg.dispatcher_interval_minutes)
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
            elk_force_all_tasks=force and job_id == "elk",
            writing_force_all=force and job_id == "writing",
            suppress_job_wecom=job_id in notify_on_run,
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

        if (
            job_id in notify_on_run
            and not no_notify
            and not dry_run
            and not _run_result_skipped(entry)
        ):
            end_stamp = datetime.now(tz) if at is None else now
            run_notifies = _notify_job_run_reports(
                {job_id: entry},
                now=end_stamp,
                no_notify=no_notify,
                dry_run=dry_run,
                allow_success=allow_success_wecom,
            )
            if run_notifies.get(job_id):
                entry["wecom_run_notify"] = run_notifies[job_id]

    success_notify_ok: bool | None = None
    success_notify_msg = ""
    end_now = datetime.now(tz) if at is None else now
    allow_success_wecom = success_wecom_allowed(end_now, cfg)
    trial_hourly_active = notify_success_trial_active(
        end_now, cfg.notify_success_trial
    ) or notify_success_trial_active(now, cfg.notify_success_trial)
    job_hourly_notifies: dict[str, dict] = {}
    trial_skip_reason: str | None = None
    if cfg.notify_success_trial and cfg.notify_success_trial.enabled:
        if not trial_hourly_active:
            trial_skip_reason = (
                f"not_on_hour (start={now.strftime('%H:%M:%S')}, "
                f"end={end_now.strftime('%H:%M:%S')})"
            )
        elif not results:
            trial_skip_reason = "no_jobs_ran"
        elif no_notify:
            trial_skip_reason = "no_notify"
        elif dry_run:
            trial_skip_reason = "dry_run"
    hourly_heartbeat: dict | None = None
    if trial_hourly_active and not no_notify and not dry_run:
        warn_missing_webhooks()
    if trial_hourly_active:
        hourly_targets = {
            k: v
            for k, v in results.items()
            if not trial_job_ids or k in trial_job_ids
        }
        if hourly_targets:
            job_hourly_notifies = _notify_trial_hourly_reports(
                hourly_targets,
                now=end_now,
                no_notify=no_notify,
                dry_run=dry_run,
                job_ids=trial_job_ids,
                allow_success=allow_success_wecom,
            )
        elif (
            allow_success_wecom
            and not no_notify
            and not dry_run
            and cfg.notify_success_trial
            and cfg.notify_success_trial.heartbeat_if_no_jobs
        ):
            body = monitor_report_markdown(
                title="终端接口监控测试报告",
                checked_at=end_now.strftime("%Y-%m-%d %H:%M:%S"),
                passed=True,
                monitor_item="统一调度",
                note="本轮无到期 health/ws 任务，调度器正常",
            )
            ok, msg = send_markdown_message(body, channel="health")
            hourly_heartbeat = {"ok": ok, "message": msg, "channel": "health"}
            trial_skip_reason = None

    all_run_ok = bool(results) and all(
        int(info.get("exit_code", 1)) == 0 for info in results.values()
    )
    if (
        notify_success
        and allow_success_wecom
        and not trial_hourly_active
        and not no_notify
        and not dry_run
        and all_run_ok
        and exit_code == 0
    ):
        ran = "、".join(JOB_LABELS.get(j, j) for j in results.keys()) or "无"
        body = monitor_report_markdown(
            checked_at=now.strftime("%Y-%m-%d %H:%M:%S"),
            passed=True,
            monitor_item=f"统一调度（{ran}）",
        )
        success_notify_ok, success_notify_msg = send_markdown_message(
            body,
            channel="elk",
        )

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
        if success_notify_ok is not None:
            payload["wecom_success_notify"] = success_notify_ok
            payload["wecom_success_message"] = success_notify_msg
        if job_hourly_notifies:
            payload["wecom_job_hourly_notifies"] = job_hourly_notifies
            payload["notify_success_trial_hourly"] = True
        run_complete = {
            jid: info["wecom_run_notify"]
            for jid, info in results.items()
            if isinstance(info.get("wecom_run_notify"), dict)
        }
        if run_complete:
            payload["wecom_job_run_notifies"] = run_complete
        if trial_skip_reason:
            payload["notify_success_trial_skipped"] = trial_skip_reason
        if hourly_heartbeat is not None:
            payload["wecom_hourly_heartbeat"] = hourly_heartbeat
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
