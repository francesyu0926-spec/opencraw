from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

from scripts.cron_task_monitor.env_file import apply_writing_wecom_webhook
from scripts.cron_task_monitor.schedule_config import load_monitor_schedule


REPO_ROOT = Path(__file__).resolve().parents[1]
AW_ROOT = REPO_ROOT / "scripts" / "automated_writing"


def test_production_schedule_includes_writing_job() -> None:
    cfg = load_monitor_schedule(REPO_ROOT / "config" / "monitor_schedule.production.yaml")
    assert "writing" in cfg.jobs
    job = cfg.jobs["writing"]
    assert job.enabled
    assert job.interval_minutes == 5
    assert job.active_start == "07:00"
    assert job.active_end == "20:30"


def test_apply_writing_wecom_webhook_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SFC_WECHAT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("WECOM_WEBHOOK_URL_WRITING", "https://example.com/hook")
    apply_writing_wecom_webhook()
    assert os.environ["SFC_WECHAT_WEBHOOK_URL"] == "https://example.com/hook"


def test_automated_writing_tasks_count() -> None:
    if str(AW_ROOT) not in sys.path:
        sys.path.insert(0, str(AW_ROOT))
    from verify.tasks import TASKS

    assert len(TASKS) == 7


def test_writing_monitor_yaml_exists() -> None:
    path = REPO_ROOT / "config" / "writing_monitor.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["timezone"] == "Asia/Shanghai"
