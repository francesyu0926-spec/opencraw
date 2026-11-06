from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.schedule_runner import _job_hourly_report_message


def test_hourly_report_markdown_failure_without_counts() -> None:
    now = datetime(2026, 11, 4, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    text = _job_hourly_report_message(
        "health",
        {
            "exit_code": 1,
            "description": "行情 health",
            "detail": {
                "ok": False,
                "root_status": "DOWN",
                "check_count": 3,
                "error": "根路径不可用",
            },
        },
        now,
    )
    assert "### 行情 HTTP 探活监控测试报告" in text
    assert "> 时间：2026-11-04 19:00:00" in text
    assert "监控项" not in text
    assert "未通过" in text
    assert "根路径不可用" in text
    assert "check_count" not in text
    assert "exit_code" not in text


def test_hourly_report_markdown_success() -> None:
    now = datetime(2026, 11, 4, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    text = _job_hourly_report_message(
        "elk",
        {"exit_code": 0, "description": "ELK", "detail": {"hit_count": 99}},
        now,
    )
    assert "### ELK 数据同步监控测试报告" in text
    assert "通过" in text
    assert "监控项" not in text
    assert "hit_count" not in text
