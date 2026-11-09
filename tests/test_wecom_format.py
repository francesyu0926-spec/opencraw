from __future__ import annotations

import unittest

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.wecom_format import (
    exit_code_to_report_passed,
    grace_note_for_job,
    monitor_report_markdown,
    report_checked_at_for_job,
    subtasks_display_for_job,
)


class WecomFormatSubtasksTests(unittest.TestCase):
    def test_grace_exit_code_shows_pending_verdict(self) -> None:
        body = monitor_report_markdown(
            checked_at="2026-11-09 02:15:00",
            passed=exit_code_to_report_passed(2),
            monitor_item="ELK 数据同步",
            note=grace_note_for_job(
                "elk",
                {
                    "detail": {
                        "subtask_results": [
                            {
                                "task_id": "CBD_SECURITY_DICT",
                                "name": "字典表同步",
                                "status": "in_progress",
                            }
                        ]
                    }
                },
            ),
        )
        self.assertIn("进行中", body)
        self.assertNotIn("未通过", body)
        self.assertIn("宽限观察中", body)

    def test_elk_subtasks_empty_when_only_failed_results(self) -> None:
        info = {
            "exit_code": 1,
            "detail": {
                "subtask_results": [
                    {"task_id": "NC_LISTSTOCK_GLANCE", "name": "上市股票一览表", "status": "in_progress"},
                ],
                "monitored_tasks": [
                    {"id": "NC_LISTSTOCK_GLANCE", "name": "上市股票一览表"},
                ],
            },
        }
        self.assertEqual(subtasks_display_for_job("elk", info), "")

    def test_elk_subtasks_from_monitored_tasks(self) -> None:
        info = {
            "exit_code": 0,
            "detail": {
                "monitored_tasks": [
                    {"id": "CBD_BOAR_INFO", "name": "主题"},
                    {"id": "CBD_PUB_BOAR_INFO", "name": "主题成分股"},
                ]
            },
        }
        self.assertEqual(
            subtasks_display_for_job("elk", info),
            "CBD_BOAR_INFO（主题）、CBD_PUB_BOAR_INFO（主题成分股）",
        )

    def test_writing_subtasks_from_results(self) -> None:
        info = {
            "exit_code": 0,
            "detail": {
                "results": [
                    {"task": "盘前情报", "status": "passed", "message": "ok"},
                ]
            },
        }
        self.assertEqual(subtasks_display_for_job("writing", info), "盘前情报")

    def test_writing_subtasks_from_monitored_tasks(self) -> None:
        info = {
            "exit_code": 0,
            "detail": {"monitored_tasks": [{"name": "盘前情报"}]},
        }
        self.assertEqual(subtasks_display_for_job("writing", info), "盘前情报")

    def test_elk_report_time_uses_query_lte(self) -> None:
        info = {
            "detail": {
                "query_time_range": {
                    "lte": "2026-11-09T01:05:23+08:00",
                    "gte": "2026-11-09T00:50:23+08:00",
                }
            }
        }
        fb = datetime(2026, 11, 9, 1, 5, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(
            report_checked_at_for_job("elk", info, fb),
            "2026-11-09 01:05:23",
        )

    def test_markdown_subtasks_before_conclusion(self) -> None:
        body = monitor_report_markdown(
            checked_at="2026-11-09 07:40:00",
            passed=True,
            monitor_item="自动化写稿",
            subtasks="盘前情报",
        )
        self.assertIn("> 子任务：盘前情报", body)
        sub_i = body.index("子任务")
        concl_i = body.index("结论")
        self.assertLess(sub_i, concl_i)


if __name__ == "__main__":
    unittest.main()
