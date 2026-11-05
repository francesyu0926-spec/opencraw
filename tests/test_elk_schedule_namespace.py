from __future__ import annotations

from scripts.cron_task_monitor import __main__ as monitor_main


def test_namespace_for_elk_run_has_writing_monitor_flag() -> None:
    args = monitor_main.namespace_for_elk_run(config="config/cron_tasks.yaml")
    assert hasattr(args, "writing_monitor")
    assert args.writing_monitor is False
    assert hasattr(args, "check_wecom")
    assert args.check_wecom is False
