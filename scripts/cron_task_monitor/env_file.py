from __future__ import annotations

import os
from pathlib import Path


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def load_env_file(path: Path) -> int:
    """Load KEY=VALUE lines from path into os.environ (missing keys only).

    Skips blank lines and # comments. Does not log values.
    Returns the number of variables set.
    """
    if not path.is_file():
        return 0

    set_count = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())
        set_count += 1
    return set_count


def load_health_monitor_env_files() -> None:
    """Load config/health.env then config/wecom.env from the current working directory."""
    for rel in (Path("config/health.env"), Path("config/wecom.env")):
        load_env_file(rel)
