from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elk_subtask_eval import evaluate_elk_subtasks

CFG = load_config("config/cron_tasks.yaml")
TZ = ZoneInfo("Asia/Shanghai")


def _hit(msg: str) -> dict:
    return {"_source": {"msg": msg}}


def test_long_task_before_plan_end_not_in_scope() -> None:
    """未到预计结束 → 不进入评估列表。"""
    ref = datetime(2026, 11, 9, 1, 5, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE_2,执行时间：01:00:05"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["NC_LISTSTOCK_GLANCE_2"], ref
    )
    assert code == 0
    assert results == []


def test_short_task_passed_when_complete_and_no_violations() -> None:
    ref = datetime(2026, 11, 9, 1, 5, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: CBD_PUB_BOAR_INFO,执行时间：01:00:01"),
        _hit("任务执行完成:CBD_PUB_BOAR_INFO,耗时：120秒"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_PUB_BOAR_INFO"], ref
    )
    assert code == 0
    assert results[0]["status"] == "passed"


def test_passed_when_peer_task_late_but_self_ok() -> None:
    """同批日志里其它任务延迟启动，不应把本子任务判失败。"""
    ref = datetime(2026, 11, 9, 1, 5, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE_2,执行时间：01:30:00"),
        _hit("开始执行任务: CBD_PUB_BOAR_INFO,执行时间：01:00:01"),
        _hit("任务执行完成:CBD_PUB_BOAR_INFO,耗时：120秒"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_PUB_BOAR_INFO"], ref
    )
    assert code == 0
    assert results[0]["status"] == "passed"


def test_before_plan_end_not_evaluated() -> None:
    ref = datetime(2026, 11, 9, 1, 2, tzinfo=TZ)
    hits = [_hit("CBD_BOAR_INFO 执行失败")]
    results, code = evaluate_elk_subtasks(CFG, hits, ["CBD_BOAR_INFO"], ref)
    assert code == 0
    assert results == []


def test_grace_without_start_log_is_failed_not_in_progress() -> None:
    ref = datetime(2026, 11, 9, 2, 15, tzinfo=TZ)
    results, code = evaluate_elk_subtasks(
        CFG, [], ["CBD_SECURITY_DICT_2"], ref
    )
    assert code == 1
    assert results[0]["status"] == "failed"
    assert "未见「开始执行任务」日志" in results[0]["issues"][0]


def test_in_progress_in_grace_is_pending_not_fail() -> None:
    """预计结束后的宽限期内 → exit 2，不算未通过。"""
    ref = datetime(2026, 11, 9, 2, 15, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: CBD_SECURITY_DICT_2,执行时间：02:00:01"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_SECURITY_DICT_2"], ref
    )
    assert code == 2
    assert results[0]["status"] == "in_progress"
    assert results[0]["unresolved"] is False
    assert results[0]["in_grace"] is True


def test_in_progress_after_monitor_end_is_failed() -> None:
    """超过预计结束+宽限仍未完成 → 未通过。"""
    ref = datetime(2026, 11, 9, 2, 12, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE_2,执行时间：01:00:05"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["NC_LISTSTOCK_GLANCE_2"], ref
    )
    assert code == 1
    assert results[0]["status"] == "failed"
    assert results[0]["unresolved"] is True


def test_failed_when_execution_failed_in_log() -> None:
    ref = datetime(2026, 11, 9, 1, 6, tzinfo=TZ)
    hits = [_hit("CBD_BOAR_INFO 执行失败")]
    results, code = evaluate_elk_subtasks(CFG, hits, ["CBD_BOAR_INFO"], ref)
    assert code == 1
    assert results[0]["status"] == "failed"


def test_failure_in_grace_not_in_progress() -> None:
    ref = datetime(2026, 11, 9, 2, 10, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: CBD_SECURITY_DICT_2,执行时间：02:00:01"),
        _hit("CBD_SECURITY_DICT_2 执行失败，请检查"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_SECURITY_DICT_2"], ref
    )
    assert code == 1
    assert results[0]["status"] == "failed"
    assert results[0]["unresolved"] is True


def test_complete_before_plan_end_not_evaluated() -> None:
    ref = datetime(2026, 11, 9, 1, 2, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: CBD_PUB_BOAR_INFO,执行时间：01:00:01"),
        _hit("任务执行完成:CBD_PUB_BOAR_INFO,耗时：60秒"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_PUB_BOAR_INFO"], ref
    )
    assert code == 0
    assert results == []
