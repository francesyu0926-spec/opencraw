from __future__ import annotations

import json
from pathlib import Path

from verify.checker import CheckResult, CheckStatus, check_task_from_payload
from verify.tasks import ApiType, get_task

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"fixture 格式错误: {name}")
    return payload


def run_offline_tests() -> list[tuple[str, CheckResult]]:
    cases: list[tuple[str, str, str, CheckStatus]] = [
        ("smart_list_pass.json", "盘前情报", "2026-09-07", CheckStatus.PASSED),
        ("smart_list_pass.json", "盘前情报", "2026-09-05", CheckStatus.FAILED),
        ("share_list_pass.json", "早报推送", "2026-09-07", CheckStatus.PASSED),
        ("share_list_fail.json", "早报推送", "2026-09-07", CheckStatus.FAILED),
        ("share_list_no_permission.json", "早报推送", "2026-09-07", CheckStatus.SKIPPED),
    ]

    results: list[tuple[str, CheckResult]] = []
    for fixture_name, task_name, date_str, expected in cases:
        task = get_task(task_name)
        payload = _load_fixture(fixture_name)
        result = check_task_from_payload(task, payload, date_str)
        label = f"{fixture_name} / {task_name} / {date_str}"
        if result.status != expected:
            result = CheckResult(
                task.name,
                CheckStatus.ERROR,
                f"期望 {expected.value}，实际 {result.status.value}（{result.message}）",
            )
        results.append((label, result))
    return results


def run_mock_task(task_name: str, fixture_name: str | None = None, date_str: str | None = None) -> CheckResult:
    task = get_task(task_name)
    if fixture_name is None:
        if task.api == ApiType.SHARE:
            fixture_name = "share_list_pass.json"
        else:
            fixture_name = "smart_list_pass.json"
    payload = _load_fixture(fixture_name)
    return check_task_from_payload(task, payload, date_str or "2026-09-07")
