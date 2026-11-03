from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import ElasticsearchConfig, MonitorConfig, TaskDefinition


def load_config(path: str | Path) -> MonitorConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")

    tasks: list[TaskDefinition] = []
    for item in data.get("tasks") or []:
        tasks.append(
            TaskDefinition(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                scheduled_start=str(item["scheduled_start"]),
                expected_end=str(item["expected_end"]),
                log_index_pattern=str(item.get("log_index_pattern") or ""),
                server=str(item.get("server") or ""),
                log_dir=str(item.get("log_dir") or ""),
                log_glob=str(item.get("log_glob") or "*.log"),
                notify=str(item.get("notify") or ""),
                extra={k: v for k, v in item.items() if k not in {
                    "id", "name", "scheduled_start", "expected_end",
                    "log_index_pattern", "server", "log_dir", "log_glob", "notify",
                }},
            )
        )

    es_raw = data.get("elasticsearch") or {}
    elasticsearch: ElasticsearchConfig | None = None
    if isinstance(es_raw, dict) and (es_raw.get("url") or es_raw.get("username")):
        elasticsearch = ElasticsearchConfig(
            url=str(es_raw.get("url") or es_raw.get("es_url") or "").strip(),
            username=str(
                es_raw.get("username") or es_raw.get("es_username") or ""
            ).strip(),
        )

    return MonitorConfig(
        timezone=str(data.get("timezone") or "Asia/Shanghai"),
        late_start_threshold_minutes=int(data.get("late_start_threshold_minutes", 5)),
        overrun_after_end_threshold_minutes=int(
            data.get("overrun_after_end_threshold_minutes", 10)
        ),
        monitor_log_prefix=str(data.get("monitor_log_prefix") or "[TASK_MONITOR]"),
        tasks=tasks,
        elasticsearch=elasticsearch,
    )


def config_to_public_dict(cfg: MonitorConfig) -> dict[str, Any]:
    return {
        "timezone": cfg.timezone,
        "late_start_threshold_minutes": cfg.late_start_threshold_minutes,
        "overrun_after_end_threshold_minutes": cfg.overrun_after_end_threshold_minutes,
        "task_count": len(cfg.tasks),
    }
