from __future__ import annotations

import json
import unittest

from scripts.cron_task_monitor.models import Alert, AlertKind
from scripts.cron_task_monitor.notifier import (
    DEFAULT_WEBHOOK_ENV_ELK,
    DEFAULT_WEBHOOK_ENV_WS,
    _build_payload,
    format_alert_text,
    resolve_webhook_url,
    resolve_webhook_url_ws,
)
import os


class NotifierTests(unittest.TestCase):
    def test_wecom_payload(self) -> None:
        url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        alerts = [
            Alert(
                kind=AlertKind.LATE_START,
                task_id="CBD_QUOT_CBND_STK_2",
                task_name="同步可转债",
                message="以下任务未按时启动",
                notify="阳祥风",
                severity="critical",
            )
        ]
        payload = _build_payload(url, alerts)
        self.assertEqual(payload["msgtype"], "text")
        self.assertIn("同步可转债", payload["text"]["content"])
        self.assertEqual(json.loads(json.dumps(payload))["msgtype"], "text")

    def test_format_alert_text(self) -> None:
        alerts = [
            Alert(
                kind=AlertKind.EXECUTION_FAILED,
                task_id="T1",
                task_name="任务A",
                message="执行失败",
                notify="张三",
                severity="critical",
            )
        ]
        text = format_alert_text(alerts)
        self.assertIn("任务A", text)
        self.assertIn("执行失败", text)


    def test_separate_webhook_env(self) -> None:
        os.environ["WECOM_WEBHOOK_URL_ELK"] = "https://example.com/elk"
        os.environ["WECOM_WEBHOOK_URL_WS"] = "https://example.com/ws"
        try:
            self.assertEqual(
                resolve_webhook_url(DEFAULT_WEBHOOK_ENV_ELK),
                "https://example.com/elk",
            )
            self.assertEqual(resolve_webhook_url_ws(None), "https://example.com/ws")
        finally:
            os.environ.pop("WECOM_WEBHOOK_URL_ELK", None)
            os.environ.pop("WECOM_WEBHOOK_URL_WS", None)


if __name__ == "__main__":
    unittest.main()
