from __future__ import annotations

import os
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent


def find_repo_root(hint: Path | None = None) -> Path:
    """Return the opencraw repository root (directory that contains config/)."""
    candidates: list[Path] = []
    if hint is not None:
        p = hint.resolve()
        if p.is_file():
            p = p.parent
        candidates.append(p)
        if p.name == "config":
            candidates.append(p.parent)
    candidates.append(_MODULE_DIR.parents[1])

    seen: set[Path] = set()
    for start in candidates:
        for directory in (start, *start.parents):
            if directory in seen:
                continue
            seen.add(directory)
            if (directory / "config").is_dir() and (
                directory / "scripts" / "cron_task_monitor"
            ).is_dir():
                return directory

    return _MODULE_DIR.parents[1]


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _should_apply_env_value(key: str) -> bool:
    """True when os.environ has no meaningful value for key."""
    if key not in os.environ:
        return True
    return not os.environ[key].strip()


def load_env_file(path: Path) -> int:
    """Load KEY=VALUE lines from path into os.environ.

    Skips blank lines and # comments. Does not log values.
    Fills missing keys and replaces keys that are set but empty/whitespace
    (common when a shell profile exports QUOTES_*= without values).
    Returns the number of variables set.
    """
    if not path.is_file():
        return 0

    set_count = 0
    text = path.read_text(encoding="utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        if not _should_apply_env_value(key):
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())
        set_count += 1
    return set_count


def load_health_monitor_env_files(repo_root: Path | None = None) -> Path:
    """Load config/health.env then config/wecom.env from the repository root."""
    root = repo_root or find_repo_root()
    for name in ("health.env", "wecom.env"):
        load_env_file(root / "config" / name)
    return root
