from __future__ import annotations

import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class HealthEnvLoadReport:
    repo_root: str
    health_env_path: str
    health_env_exists: bool
    health_env_keys_loaded: int
    wecom_env_path: str
    wecom_env_exists: bool
    wecom_env_keys_loaded: int


def load_health_monitor_env_files(
    repo_root: Path | None = None,
) -> HealthEnvLoadReport:
    """Load config/health.env then config/wecom.env from the repository root."""
    root = repo_root or find_repo_root()
    health_path = root / "config" / "health.env"
    wecom_path = root / "config" / "wecom.env"
    health_n = load_env_file(health_path)
    wecom_n = load_env_file(wecom_path)
    return HealthEnvLoadReport(
        repo_root=str(root),
        health_env_path=str(health_path),
        health_env_exists=health_path.is_file(),
        health_env_keys_loaded=health_n,
        wecom_env_path=str(wecom_path),
        wecom_env_exists=wecom_path.is_file(),
        wecom_env_keys_loaded=wecom_n,
    )


def credential_env_hint(
    report: HealthEnvLoadReport,
    *,
    login_code_env: str,
    login_password_env: str,
    token_env: str,
) -> str:
    """User-facing hint when login/token env vars are still missing (no secrets)."""
    code_ok = bool(os.environ.get(login_code_env, "").strip())
    pass_ok = bool(os.environ.get(login_password_env, "").strip())
    token_ok = bool(os.environ.get(token_env, "").strip())
    if code_ok and pass_ok or token_ok:
        return ""

    parts: list[str] = []
    if not report.health_env_exists:
        parts.append(
            f"未找到 {report.health_env_path}：请从 config/health.env.example 复制为 "
            "config/health.env 并保存（Ctrl+S），勿只改 example 文件。"
        )
    elif report.health_env_keys_loaded == 0:
        parts.append(
            f"已找到 {report.health_env_path} 但未从中加载任何变量："
            "请确认文件已保存、键名无误，且 shell 中无覆盖用的非空同名变量。"
        )
    else:
        parts.append(
            f"已从 {report.health_env_path} 加载 {report.health_env_keys_loaded} 个变量，"
            f"但 {login_code_env}/{login_password_env} 仍不完整；请检查该行是否有值。"
        )
    parts.append(f"仓库根目录解析为 {report.repo_root}。")
    return " ".join(parts)
