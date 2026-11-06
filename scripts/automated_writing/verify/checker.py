from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import requests

from verify.auth import BASE_URL, AuthError
from verify.logger import get_logger
from verify.tasks import ApiType, Task, today_str

SMART_LIST_URL = f"{BASE_URL}/smartArt/view/list"
SHARE_LIST_URL = f"{BASE_URL}/article/share/list"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CheckResult:
    task: str
    status: CheckStatus
    message: str
    matched_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "status": self.status.value,
            "message": self.message,
            "matched_title": self.matched_title,
        }


def _unwrap_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        records = data.get("records")
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def _timestamp_to_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts > 1_000_000_000_000:
        ts //= 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def evaluate_smart_payload(
    payload: dict[str, Any],
    task: Task,
    date_str: str,
) -> CheckResult:
    code = payload.get("code")
    if code not in (0, "0", None):
        message = payload.get("msg") or payload.get("message") or "未知错误"
        return CheckResult(task.name, CheckStatus.ERROR, f"接口返回错误 code={code}, msg={message}")

    for item in _unwrap_records(payload.get("data")):
        crt = item.get("crt")
        if isinstance(crt, str) and date_str in crt:
            title = item.get("title") or item.get("name")
            return CheckResult(
                task.name,
                CheckStatus.PASSED,
                f"找到今日稿件（crt={crt}）",
                matched_title=str(title) if title else None,
            )

    return CheckResult(task.name, CheckStatus.FAILED, f"未找到 crt 包含 {date_str} 的稿件")


def evaluate_share_payload(
    payload: dict[str, Any],
    task: Task,
    date_str: str,
) -> CheckResult:
    code = payload.get("code")
    if code in (1001, "1001"):
        message = payload.get("msg") or payload.get("message") or "当前用户没有此权限"
        return CheckResult(
            task.name,
            CheckStatus.SKIPPED,
            f"无接口权限，跳过 live 验证（{message}）。请使用 mock 测试：python verify.py test",
        )
    if code not in (0, "0", None):
        message = payload.get("msg") or payload.get("message") or "未知错误"
        return CheckResult(task.name, CheckStatus.ERROR, f"接口返回错误 code={code}, msg={message}")

    for item in _unwrap_records(payload.get("data")):
        item_date = _timestamp_to_date(item.get("updateTime"))
        if item_date == date_str:
            title = item.get("title")
            update_time = item.get("updateTime")
            return CheckResult(
                task.name,
                CheckStatus.PASSED,
                f"找到今日推送（updateTime={update_time}）",
                matched_title=str(title) if title else None,
            )

    return CheckResult(task.name, CheckStatus.FAILED, f"未找到 updateTime 为 {date_str} 的推送记录")


def _parse_api_payload(response: requests.Response) -> dict[str, Any]:
    if response.status_code in (401, 403):
        raise AuthError(f"HTTP {response.status_code} 未授权，会话可能已失效")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("接口返回格式异常")
    code = payload.get("code")
    if code not in (0, "0", None):
        message = payload.get("msg") or payload.get("message") or "未知错误"
        raise ValueError(f"接口返回错误 code={code}, msg={message}")
    return payload


def check_smart_article(
    session: requests.Session,
    task: Task,
    bearer_token: str | None = None,
    date_str: str | None = None,
    timeout: int = 30,
) -> CheckResult:
    if not task.key:
        return CheckResult(task.name, CheckStatus.ERROR, "缺少 key 参数")

    date_str = date_str or today_str()
    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    logger = get_logger()
    logger.info("请求 smartArt/list，任务=%s，key=%s，日期=%s", task.name, task.key, date_str)

    response = session.get(
        SMART_LIST_URL,
        params={"key": task.key, "pageNo": 1, "pageSize": 10},
        headers=headers or None,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = _parse_api_payload(response)
    result = evaluate_smart_payload(payload, task, date_str)
    logger.info("smartArt/list 返回 %s 条记录，结果=%s", len(_unwrap_records(payload.get("data"))), result.status.value)
    return result


def check_share_push(
    session: requests.Session,
    task: Task,
    date_str: str | None = None,
    timeout: int = 30,
) -> CheckResult:
    if task.share_type is None:
        return CheckResult(task.name, CheckStatus.ERROR, "缺少 share type 参数")

    date_str = date_str or today_str()
    logger = get_logger()
    logger.info("请求 share/list，任务=%s，type=%s，日期=%s", task.name, task.share_type, date_str)

    response = session.get(
        SHARE_LIST_URL,
        params={"type": task.share_type, "pageNo": 1, "pageSize": 10},
        timeout=timeout,
    )
    if response.status_code in (401, 403):
        raise AuthError(f"HTTP {response.status_code} 未授权，会话可能已失效")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("接口返回格式异常") from exc
    if not isinstance(payload, dict):
        raise ValueError("接口返回格式异常")
    result = evaluate_share_payload(payload, task, date_str)
    logger.info("share/list 返回 %s 条记录，结果=%s", len(_unwrap_records(payload.get("data"))), result.status.value)
    return result


def check_task_from_payload(
    task: Task,
    payload: dict[str, Any],
    date_str: str | None = None,
) -> CheckResult:
    date_str = date_str or today_str()
    if task.api == ApiType.SMART:
        return evaluate_smart_payload(payload, task, date_str)
    if task.api == ApiType.SHARE:
        return evaluate_share_payload(payload, task, date_str)
    return CheckResult(task.name, CheckStatus.ERROR, f"未知接口类型: {task.api}")


def check_task(
    session: requests.Session,
    task: Task,
    bearer_token: str | None,
    date_str: str | None = None,
    timeout: int = 30,
) -> CheckResult:
    try:
        if task.api == ApiType.SMART:
            return check_smart_article(session, task, bearer_token, date_str, timeout)
        if task.api == ApiType.SHARE:
            return check_share_push(session, task, date_str, timeout)
        return CheckResult(task.name, CheckStatus.ERROR, f"未知接口类型: {task.api}")
    except AuthError as exc:
        return CheckResult(task.name, CheckStatus.ERROR, str(exc))
    except requests.RequestException as exc:
        return CheckResult(task.name, CheckStatus.ERROR, f"请求失败: {exc}")
    except ValueError as exc:
        return CheckResult(task.name, CheckStatus.ERROR, str(exc))
