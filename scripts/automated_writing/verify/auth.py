from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests

from verify.logger import get_logger
from verify.tasks import now

BASE_URL = "https://zxtop.sfccn.com/console"
LOGIN_URL = f"{BASE_URL}/admin/login"
DEFAULT_TIMEOUT = 30
DEFAULT_SESSION_MAX_AGE = timedelta(minutes=int(os.getenv("SFC_SESSION_MAX_AGE_MINUTES", "45")))


class AuthError(Exception):
    pass


@dataclass
class SessionContext:
    session: requests.Session
    bearer_token: str | None
    login_at: datetime

    def age(self) -> timedelta:
        return now() - self.login_at

    def is_stale(self, max_age: timedelta | None = None) -> bool:
        return self.age() >= (max_age or DEFAULT_SESSION_MAX_AGE)


def _extract_token(payload: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        payload.get("token"),
        payload.get("accessToken"),
        payload.get("authorization"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("token"),
                data.get("accessToken"),
                data.get("authorization"),
                data.get("bearerToken"),
            ]
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def login_session(
    admin_code: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    reason: str = "登录",
) -> SessionContext:
    """登录后台，返回带登录时间的会话上下文。"""
    admin_code = admin_code or os.getenv("SFC_ADMIN_CODE", "")
    password = password or os.getenv("SFC_ADMIN_PASSWORD", "")
    bearer_token = bearer_token or os.getenv("SFC_BEARER_TOKEN")

    if not admin_code or not password:
        raise AuthError("请设置 SFC_ADMIN_CODE 和 SFC_ADMIN_PASSWORD 环境变量")

    logger = get_logger()
    logger.info("正在登录后台，账号: %s（%s）", admin_code, reason)

    session = requests.Session()
    response = session.post(
        LOGIN_URL,
        data={"adminCode": admin_code, "password": password},
        timeout=timeout,
    )
    response.raise_for_status()

    if "JSESSIONID" not in session.cookies:
        raise AuthError("登录失败：未获取到 JSESSIONID Cookie")

    logger.info("登录成功，已获取 JSESSIONID")

    if not bearer_token:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            bearer_token = _extract_token(payload)

    return SessionContext(session=session, bearer_token=bearer_token, login_at=now())


def ensure_session(
    ctx: SessionContext | None,
    *,
    force: bool = False,
    reason: str = "登录",
) -> SessionContext:
    if ctx is None or force or ctx.is_stale():
        if ctx is not None and ctx.is_stale() and not force:
            get_logger().info(
                "会话已超过 %d 分钟，主动刷新",
                int(DEFAULT_SESSION_MAX_AGE.total_seconds() // 60),
            )
            reason = "会话刷新"
        return login_session(reason=reason)
    return ctx


def is_auth_error_message(message: str) -> bool:
    if "没有此权限" in message or "code=1001" in message:
        return False
    lowered = message.lower()
    return any(
        token in lowered
        for token in ("401", "403", "未授权", "未登录", "登录失败", "jsessionid", "session")
    )
