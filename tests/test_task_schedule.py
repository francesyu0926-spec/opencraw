"""校验 YAML 与运维 PDF §2.1 任务时间一致。"""

from __future__ import annotations

import unittest

from scripts.cron_task_monitor.config_loader import load_config

# PDF 第二表（logstash-zxt-terminal + 更新项）
EXPECTED = {
    "CBD_PUB_BOARD_INFO": ("01:00", "01:03"),
    "CBD_BOARD_INFO": ("01:00", "01:05"),
    "CBD_QUOT_STK_ISS": ("01:00", "01:05"),
    "CBD_SECURITY_DICT": ("04:00", "04:05"),
    "CBD_TRD_DT_RECNT": ("01:00", "02:00"),
    "NC_LISTSTOCK_GLANCE": ("00:00", "00:05"),
    "NC_TQ_SK_XDRY": ("02:40", "02:45"),
    "CBD_BD_FIN_DATA": ("04:00", "04:05"),
    "CBD_QUOT_CBND_STK": ("02:00", "02:05"),
}


class TaskScheduleTests(unittest.TestCase):
    def test_schedules_match_pdf(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        by_id = {t.id: t for t in cfg.tasks}
        for task_id, (start, end) in EXPECTED.items():
            task = by_id[task_id]
            self.assertEqual(task.scheduled_start, start, task_id)
            self.assertEqual(task.expected_end, end, task_id)

    def test_batch_window_config(self) -> None:
        cfg = load_config("config/cron_tasks.yaml")
        self.assertEqual(cfg.query_time_mode, "batch_window")
        self.assertEqual(cfg.batch_window_start, "00:00")
        self.assertEqual(cfg.batch_window_end, "05:00")


if __name__ == "__main__":
    unittest.main()
