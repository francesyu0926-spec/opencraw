from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.cron_task_monitor.config_loader import load_config
from scripts.cron_task_monitor.elk_subtask_eval import evaluate_elk_subtasks

CFG = load_config("config/cron_tasks.yaml")
TZ = ZoneInfo("Asia/Shanghai")


def _hit(msg: str) -> dict:
    return {"_source": {"msg": msg}}


def test_long_task_in_progress_at_0105() -> None:
    """01:05 仅启动、未到 02:00 结束 → 进行中，不算成功。"""
    ref = datetime(2026, 11, 9, 1, 5, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE,执行时间：01:00:05"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["NC_LISTSTOCK_GLANCE"], ref
    )
    assert code == 0
    assert len(results) == 1
    assert results[0]["status"] == "in_progress"
    assert results[0]["unresolved"] is False


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
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE,执行时间：01:30:00"),
        _hit("开始执行任务: CBD_PUB_BOAR_INFO,执行时间：01:00:01"),
        _hit("任务执行完成:CBD_PUB_BOAR_INFO,耗时：120秒"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_PUB_BOAR_INFO"], ref
    )
    assert code == 0
    assert results[0]["status"] == "passed"


def test_failure_log_before_plan_end_is_in_progress() -> None:
    """计划结束前即便有失败日志，也不套告警规则。"""
    ref = datetime(2026, 11, 9, 1, 2, tzinfo=TZ)
    hits = [_hit("CBD_BOAR_INFO 执行失败")]
    results, code = evaluate_elk_subtasks(CFG, hits, ["CBD_BOAR_INFO"], ref)
    assert code == 0
    assert results[0]["status"] == "in_progress"
    assert results[0]["unresolved"] is False
    assert results[0]["issues"] == []


def test_in_progress_after_plan_end_counts_unresolved() -> None:
    """超过预计结束仍未完成 → 算未通过。"""
    ref = datetime(2026, 11, 9, 2, 1, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: NC_LISTSTOCK_GLANCE,执行时间：01:00:05"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["NC_LISTSTOCK_GLANCE"], ref
    )
    assert code == 1
    assert results[0]["status"] == "in_progress"
    assert results[0]["unresolved"] is True


def test_failed_when_execution_failed_in_log() -> None:
    ref = datetime(2026, 11, 9, 1, 6, tzinfo=TZ)
    hits = [_hit("CBD_BOAR_INFO 执行失败")]
    results, code = evaluate_elk_subtasks(CFG, hits, ["CBD_BOAR_INFO"], ref)
    assert code == 1
    assert results[0]["status"] == "failed"


def test_complete_before_plan_end_stays_in_progress() -> None:
    ref = datetime(2026, 11, 9, 1, 2, tzinfo=TZ)
    hits = [
        _hit("开始执行任务: CBD_PUB_BOAR_INFO,执行时间：01:00:01"),
        _hit("任务执行完成:CBD_PUB_BOAR_INFO,耗时：60秒"),
    ]
    results, code = evaluate_elk_subtasks(
        CFG, hits, ["CBD_PUB_BOAR_INFO"], ref
    )
    assert code == 0
    assert results[0]["status"] == "in_progress"
    assert results[0]["unresolved"] is False
