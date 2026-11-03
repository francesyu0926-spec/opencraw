from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AlertKind(str, Enum):
    LATE_START = "late_start"
    EXECUTION_FAILED = "execution_failed"
    OVERTIME = "execution_overtime"
    NO_START = "no_start"
    MISSING_LOG = "missing_log"


@dataclass
class TaskDefinition:
    id: str
    name: str
    scheduled_start: str  # HH:MM
    expected_end: str  # HH:MM
    log_index_pattern: str
    server: str
    log_dir: str
    log_glob: str = "*.log"
    notify: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskRunRecord:
    task_id: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str | None = None  # success | failure | running | unknown
    source: str = "local"  # local | elk
    raw_messages: list[str] = field(default_factory=list)


@dataclass
class Alert:
    kind: AlertKind
    task_id: str
    task_name: str
    message: str
    notify: str
    severity: str  # warning | critical


@dataclass
class MonitorConfig:
    timezone: str
    late_start_threshold_minutes: int
    overrun_after_end_threshold_minutes: int
    monitor_log_prefix: str
    tasks: list[TaskDefinition]
