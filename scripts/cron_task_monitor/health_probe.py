from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .health_config import HealthMonitorConfig

_MISSING = object()
_JWT_RE = re.compile(
    r"^[A-Za-z0-9_-]+=*(?:\.[A-Za-z0-9_-]+=*){2}$"
)
_SECRET_RE = re.compile(
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"|\b[0-9a-fA-F]{32,}\b"
    r"|\b1\d{10}\b"
)
_PREFERRED_TOKEN_PATHS = (
    ("token",),
    ("data", "token"),
    ("data", "accessToken"),
    ("accessToken",),
    ("access_token",),
    ("data", "access_token"),
    ("data", "jwt"),
    ("result", "token"),
    ("result", "accessToken"),
    ("result", "access_token"),
    ("data",),
)
_TOKEN_KEY_RANK = {
    "token": 0,
    "accesstoken": 1,
    "access_token": 2,
    "jwt": 3,
    "authorization": 4,
    "id_token": 5,
    "idtoken": 6,
}


@dataclass
class HealthProbeResult:
    ok: bool
    error: str = ""
    http_status: int | None = None
    root_status: str = ""
    down_checks: list[str] = field(default_factory=list)
    check_count: int = 0
    raw_snippet: str = ""


def _collect_status_issues(
    body: Any,
    *,
    expected: str,
) -> tuple[str, list[str], int]:
    """Return (root_status, down_check_ids, check_count)."""
    if not isinstance(body, dict):
        raise ValueError("health JSON 根节点须为 object")

    root = str(body.get("status") or "")
    down: list[str] = []
    checks = body.get("checks")
    count = 0
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            count += 1
            cid = str(item.get("id") or f"check#{count}")
            st = str(item.get("status") or "")
            if st != expected:
                down.append(f"{cid}={st or '(missing)'}")

    return root, down, count


def _normalize_token(value: str) -> str:
    text = value.strip()
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    return text


def _is_jwt(value: str) -> bool:
    return bool(_JWT_RE.fullmatch(value))


def _get_ci(obj: Any, key: str) -> Any:
    if not isinstance(obj, dict):
        return _MISSING
    if key in obj:
        return obj[key]
    wanted = key.lower()
    for name, value in obj.items():
        if str(name).lower() == wanted:
            return value
    return _MISSING


def _dig(body: Any, path: tuple[str, ...]) -> Any:
    current = body
    for key in path:
        current = _get_ci(current, key)
        if current is _MISSING:
            return _MISSING
    return current


def _jwt_from_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = _normalize_token(value)
    if _is_jwt(token):
        return token
    return None


def _walk_jwts(
    node: Any,
    depth: int,
    found: list[tuple[int, int, str]],
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            token = _jwt_from_value(value)
            if token:
                rank = _TOKEN_KEY_RANK.get(str(key).lower(), 50)
                found.append((rank, depth, token))
            else:
                _walk_jwts(value, depth + 1, found)
    elif isinstance(node, list):
        for item in node:
            _walk_jwts(item, depth + 1, found)


def extract_login_token(body: Any) -> str | None:
    """Pick the JWT from a login JSON body. Never logs the value."""
    if not isinstance(body, dict):
        return None
    for path in _PREFERRED_TOKEN_PATHS:
        token = _jwt_from_value(_dig(body, path))
        if token:
            return token
    found: list[tuple[int, int, str]] = []
    _walk_jwts(body, 0, found)
    if not found:
        return None
    found.sort(key=lambda item: (item[0], item[1]))
    return found[0][2]


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return _SECRET_RE.sub("[redacted]", cleaned)


def _public_message(body: Any, secrets: tuple[str, ...]) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("message", "msg", "error", "errorMsg"):
        value = body.get(key)
        if not isinstance(value, str):
            continue
        text = _redact(" ".join(value.split()), secrets).strip()
        if not text or text == "[redacted]":
            continue
        if len(text) > 80:
            text = text[:80] + "..."
        return text
    return ""


def _fetch_login_token(
    cfg: HealthMonitorConfig,
    login_code: str,
    password: str,
) -> tuple[str | None, str]:
    """Return (token, error). error is empty on success and never includes secrets."""
    form = urllib.parse.urlencode(
        {"loginCode": login_code, "password": password}
    ).encode("utf-8")
    req = urllib.request.Request(
        cfg.login_url,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    secrets = (login_code, password)
    try:
        with urllib.request.urlopen(req, timeout=cfg.request_timeout_seconds) as resp:
            http_status = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return None, f"登录失败 HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = _redact(str(e), secrets)
        return None, f"登录请求失败: {reason}"[:200]

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"登录响应非 JSON（HTTP {http_status}）"

    token = extract_login_token(body)
    if not token:
        hint = _public_message(body, secrets)
        if hint:
            return None, f"登录响应中未找到 Token（{hint}）"
        return None, "登录响应中未找到 Token"
    return token, ""


def _resolve_token(cfg: HealthMonitorConfig) -> tuple[str | None, str]:
    login_code = os.environ.get(cfg.login_code_env, "").strip()
    password = os.environ.get(cfg.login_password_env, "").strip()
    if login_code or password:
        if not login_code or not password:
            missing = cfg.login_code_env if not login_code else cfg.login_password_env
            return None, f"未配置环境变量 {missing}"
        return _fetch_login_token(cfg, login_code, password)

    token = os.environ.get(cfg.token_env, "").strip()
    if not token:
        return None, (
            f"未配置环境变量 {cfg.login_code_env} 与 {cfg.login_password_env}，"
            f"且未配置 {cfg.token_env}"
        )
    return token, ""


def run_health_probe(cfg: HealthMonitorConfig) -> HealthProbeResult:
    token, token_error = _resolve_token(cfg)
    if not token:
        return HealthProbeResult(
            ok=False,
            error=token_error or "未取得 Token",
        )

    headers = {
        "Token": token,
        "Content-Type": "application/json; charset=utf-8",
    }
    req = urllib.request.Request(
        cfg.url,
        data=b"",
        headers=headers,
        method=cfg.method,
    )

    try:
        with urllib.request.urlopen(req, timeout=cfg.request_timeout_seconds) as resp:
            http_status = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = _redact(
            e.read().decode("utf-8", errors="replace")[:500],
            (token,),
        )
        return HealthProbeResult(
            ok=False,
            error=f"HTTP {e.code}: {detail}",
            http_status=e.code,
            raw_snippet=detail,
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return HealthProbeResult(ok=False, error=_redact(str(e), (token,)))

    snippet = _redact(raw[:800], (token,))
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return HealthProbeResult(
            ok=False,
            error=f"响应非 JSON: {e}",
            http_status=http_status,
            raw_snippet=snippet,
        )

    try:
        root, down, count = _collect_status_issues(
            body, expected=cfg.expected_status
        )
    except ValueError as e:
        return HealthProbeResult(
            ok=False,
            error=str(e),
            http_status=http_status,
            raw_snippet=snippet,
        )

    result = HealthProbeResult(
        ok=True,
        http_status=http_status,
        root_status=root,
        down_checks=down,
        check_count=count,
        raw_snippet=snippet,
    )

    if root != cfg.expected_status:
        result.ok = False
        result.error = (
            f"总状态 {root or '(missing)'} != {cfg.expected_status}"
        )
        return result

    if down:
        result.ok = False
        result.error = "以下组件非 UP: " + ", ".join(down)
        return result

    return result
