from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from .env_file import find_repo_root, load_writing_monitor_env_files


def _ensure_verify_import_path(repo_root: Path) -> Path:
    aw_root = repo_root / "scripts" / "automated_writing"
    aw_str = str(aw_root)
    if aw_str not in sys.path:
        sys.path.insert(0, aw_str)
    return aw_root


def run_writing_monitor(
    config_path: Path,
    *,
    at: str | None,
    as_json: bool,
    dry_run: bool,
    notify: bool,
    no_notify: bool,
    *,
    writing_use_window: bool = True,
    writing_force_all: bool = False,
) -> int:
    """Run automated_writing verify (due tasks only). Failures notify via SFC_WECHAT_WEBHOOK_URL."""
    _ = notify  # verify CLI notifies on failure when webhook is set
    repo_root = find_repo_root(config_path)
    load_writing_monitor_env_files(repo_root=repo_root)
    aw_root = _ensure_verify_import_path(repo_root)
    if not (aw_root / "verify").is_dir():
        print(f"automated_writing verify package not found: {aw_root / 'verify'}", file=sys.stderr)
        return 2

    if dry_run:
        if as_json:
            print('{"mode":"writing_monitor","dry_run":true,"message":"skipped"}')
        else:
            print("writing_monitor dry_run: skipped")
        return 0

    from verify.cli import main as verify_main

    from .writing_task_schedule import load_writing_schedule_settings

    delay, slot, active_end = load_writing_schedule_settings(config_path)
    os.environ["WRITING_EXECUTION_DELAY_MINUTES"] = str(delay)
    os.environ["WRITING_EXECUTION_SLOT_MINUTES"] = str(slot)
    if active_end is not None:
        os.environ["WRITING_ACTIVE_END"] = active_end.strftime("%H:%M")
    else:
        os.environ.pop("WRITING_ACTIVE_END", None)
    if at:
        os.environ["WRITING_MONITOR_AT"] = at
    else:
        os.environ.pop("WRITING_MONITOR_AT", None)

    if writing_force_all:
        argv = ["run", "--all", "--force"]
    elif writing_use_window:
        from .writing_task_schedule import active_writing_task_names

        if at:
            from zoneinfo import ZoneInfo
            from datetime import datetime

            dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        else:
            from verify.tasks import now as writing_now

            dt = writing_now()
        names = active_writing_task_names(
            dt, config_path=config_path, repo_root=repo_root
        )
        if not names:
            if as_json:
                print(
                    json.dumps(
                        {
                            "mode": "writing_monitor",
                            "skipped": True,
                            "reason": "no_task_in_monitor_window",
                            "checked_at": dt.isoformat(),
                        },
                        ensure_ascii=False,
                    )
                )
            return 0
        argv = ["run", "--window"]
    else:
        argv = ["run", "--due"]
    if no_notify:
        argv.append("--no-notify")

    if as_json:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = verify_main(argv)
        text = buf.getvalue().strip()
        if text:
            print(text)
        return code

    return verify_main(argv)
