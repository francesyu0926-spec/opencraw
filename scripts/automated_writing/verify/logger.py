from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _log_dir() -> Path:
    return Path(os.getenv("SFC_LOG_DIR", "logs"))


def daily_log_file(date_str: str | None = None) -> Path:
    custom = os.getenv("SFC_LOG_FILE")
    if custom:
        return Path(custom)
    date_str = date_str or datetime.now(TZ).strftime("%Y-%m-%d")
    return _log_dir() / f"verify-{date_str}.log"


class DailyFileHandler(logging.Handler):
    """按打印日期写入独立日志文件，跨日自动切换。"""

    def __init__(self, log_dir: Path):
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: str | None = None
        self._stream = None

    def _open_for_date(self, date_str: str) -> None:
        if self._stream:
            self._stream.close()
        log_path = daily_log_file(date_str)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = log_path.open("a", encoding="utf-8")
        self._current_date = date_str

    def emit(self, record: logging.LogRecord) -> None:
        if os.getenv("SFC_LOG_FILE"):
            if self._stream is None:
                log_path = daily_log_file()
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = log_path.open("a", encoding="utf-8")
        else:
            date_str = datetime.now(TZ).strftime("%Y-%m-%d")
            if date_str != self._current_date:
                self._open_for_date(date_str)

        try:
            msg = self.format(record)
            assert self._stream is not None
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()


def setup_logging(verbose: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    log_stream = sys.stderr if os.getenv("VERIFY_CONSOLE_STDERR") else sys.stdout
    console_handler = logging.StreamHandler(log_stream)
    console_handler.setFormatter(formatter)

    file_handler = DailyFileHandler(_log_dir())
    file_handler.setFormatter(formatter)

    logger = logging.getLogger("verify")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    _CONFIGURED = True

    logger.info("日志文件: %s", daily_log_file().resolve())


def get_logger() -> logging.Logger:
    setup_logging()
    return logging.getLogger("verify")


def log_section(title: str) -> None:
    get_logger().info("=" * 50)
    get_logger().info(title)
    get_logger().info("=" * 50)


def log_task_result(task: str, status: str, message: str, **extra: Any) -> None:
    logger = get_logger()
    line = f"[{task}] {status.upper()} - {message}"
    if status in ("failed", "error"):
        logger.error(line)
    elif status == "skipped":
        logger.warning(line)
    else:
        logger.info(line)
    for key, value in extra.items():
        if value is not None:
            logger.info(f"  {key}: {value}")
