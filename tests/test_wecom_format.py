from __future__ import annotations

import unittest

from scripts.cron_task_monitor.wecom_format import (
    monitor_report_markdown,
    subtasks_display_for_job,
)


class WecomFormatSubtasksTests(unittest.TestCase):
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
