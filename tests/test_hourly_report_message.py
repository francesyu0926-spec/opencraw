from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.schedule_runner import _job_hourly_report_message


def test_hourly_report_includes_failure_detail() -> None:
    now = datetime(2026, 11, 4, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    text = _job_hourly_report_message(
        "health",
        {
            "exit_code": 1,
            "description": "行情 health",
            "detail": {"ok": False, "root_status": "DOWN", "check_count": 3},
        },
        now,
    )
    assert "失败" in text
    assert "exit_code=1" in text
