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

    Skips blank lines and # comments. Does not override non-empty env vars.
    Empty or whitespace-only values already in the environment are replaced.
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
        key = key.strip().lstrip("\ufeff")
        if not key:
            continue
        if not _should_apply_env_value(key):
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())
        set_count += 1
    return set_count


def apply_writing_wecom_webhook() -> None:
    """Map opencraw WECOM_WEBHOOK_URL_WRITING → verify SFC_WECHAT_WEBHOOK_URL."""
    if os.getenv("SFC_WECHAT_WEBHOOK_URL", "").strip():
        return
    alt = os.getenv("WECOM_WEBHOOK_URL_WRITING", "").strip()
    if alt:
        os.environ["SFC_WECHAT_WEBHOOK_URL"] = alt


def load_writing_monitor_env_files(
    *,
    config_path: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Load config/writing.env, wecom.env; apply writing webhook alias."""
    if repo_root is not None:
        load_env_file(repo_root / "config" / "writing.env")
        load_env_file(repo_root / "config" / "wecom.env")
        apply_writing_wecom_webhook()
        return repo_root
    root = find_repo_root(config_path)
    load_env_file(root / "config" / "writing.env")
    load_env_file(root / "config" / "wecom.env")
    apply_writing_wecom_webhook()
    return root


def load_all_monitor_env_files(
    *,
    anchor: Path | None = None,
    include_elk: bool = True,
) -> Path:
    """Load elk.env, health.env, wecom.env from repository root (in that order)."""
    root = find_repo_root(anchor)
    names: list[str] = []
    if include_elk:
        names.append("elk.env")
    names.extend(("health.env", "wecom.env", "writing.env"))
    for name in names:
        load_env_file(root / "config" / name)
    apply_writing_wecom_webhook()
    return root


def load_health_monitor_env_files(
    *,
    config_path: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Load config/health.env then config/wecom.env from the repository root."""
    if repo_root is not None:
        for name in ("health.env", "wecom.env"):
            load_env_file(repo_root / "config" / name)
        return repo_root
    return load_all_monitor_env_files(anchor=config_path, include_elk=False)
