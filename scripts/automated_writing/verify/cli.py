from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from verify.auth import AuthError, SessionContext, ensure_session, is_auth_error_message, login_session
from verify.checker import CheckResult, CheckStatus, check_task
from verify.lock import acquire_daemon_lock
from verify.logger import get_logger, log_section, log_task_result, setup_logging
from verify.notify import notify_failure
from verify.offline import run_mock_task, run_offline_tests
from verify.tasks import TASKS, Task, get_task, is_due, now, pending_message, should_run_task, today_str


def _format_time(value: datetime.time) -> str:
    return value.strftime("%H:%M")


def cmd_list(_: argparse.Namespace) -> int:
    rows = []
    for task in TASKS:
        rows.append(
            {
                "name": task.name,
                "check_time": _format_time(task.check_time),
                "api": task.api.value,
                "key": task.key,
                "share_type": task.share_type,
                "weekdays_only": task.weekdays_only,
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def _select_tasks(args: argparse.Namespace) -> list[Task]:
    if args.task:
        return [get_task(args.task)]
    return list(TASKS)


def _prepare_task(task: Task, args: argparse.Namespace) -> CheckResult | None:
    if not should_run_task(task):
        return CheckResult(task.name, CheckStatus.SKIPPED, "非工作日，跳过监测")
    if not args.force and not is_due(task):
        return CheckResult(task.name, CheckStatus.SKIPPED, pending_message(task))
    if args.skip_share and task.name == "早报推送":
        return CheckResult(
            task.name,
            CheckStatus.SKIPPED,
            "已跳过 share/list live 验证（无权限账号）。请用 python verify.py test 做离线测试",
        )
    return None


def _log_summary(results: list[CheckResult]) -> None:
    passed = sum(1 for item in results if item.status == CheckStatus.PASSED)
    failed = sum(1 for item in results if item.status == CheckStatus.FAILED)
    skipped = sum(1 for item in results if item.status == CheckStatus.SKIPPED)
    errors = sum(1 for item in results if item.status == CheckStatus.ERROR)
    logger = get_logger()
    logger.info("-" * 50)
    logger.info(
        "监测汇总: 共 %d 项 | 通过 %d | 失败 %d | 跳过 %d | 错误 %d",
        len(results),
        passed,
        failed,
        skipped,
        errors,
    )


def cmd_run(args: argparse.Namespace) -> int:
    setup_logging(verbose=args.verbose)
    load_dotenv()
    logger = get_logger()

    mode = "mock" if args.mock else "live"
    log_section(f"开始任务监测 [{mode}] 日期={today_str()} 时间={now().strftime('%H:%M:%S')}")

    tasks = _select_tasks(args)
    if args.task:
        candidates = tasks
        logger.info("执行模式: 单任务 (%s)", args.task)
    elif args.all:
        candidates = [task for task in tasks if should_run_task(task)]
        logger.info("执行模式: 全部适用任务 (%d 项)", len(candidates))
    else:
        candidates = [task for task in tasks if is_due(task)]
        logger.info("执行模式: 已到监测时间 (%d 项)", len(candidates))

    results: list[CheckResult] = []
    session_ctx: SessionContext | None = None

    for task in candidates:
        logger.info("处理任务: %s (监测 %s)", task.name, _format_time(task.check_time))
        prepared = _prepare_task(task, args)
        if prepared is not None:
            results.append(prepared)
            log_task_result(prepared.task, prepared.status.value, prepared.message)
            continue

        if args.mock:
            result = run_mock_task(task.name, args.fixture, args.date)
            results.append(result)
            log_task_result(result.task, result.status.value, result.message, matched_title=result.matched_title)
            continue

        session_ctx = _ensure_session(session_ctx)
        result = check_task(session_ctx.session, task, session_ctx.bearer_token)
        if result.status == CheckStatus.ERROR and _is_auth_error(result.message):
            logger.info("会话失效，重新登录")
            session_ctx = login_session(reason="会话失效")
            result = check_task(session_ctx.session, task, session_ctx.bearer_token)
        results.append(result)
        log_task_result(result.task, result.status.value, result.message, matched_title=result.matched_title)
        if (
            not args.no_notify
            and result.status in (CheckStatus.FAILED, CheckStatus.ERROR)
        ):
            notify_failure(result, source="run")

    if not results:
        logger.info("当前没有需要执行的任务")
        print(json.dumps({"message": "当前没有需要执行的任务", "results": []}, ensure_ascii=False))
        return 0

    _log_summary(results)

    payload = {
        "checked_at": now().isoformat(),
        "mode": mode,
        "results": [item.to_dict() for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    failed = any(item.status in (CheckStatus.FAILED, CheckStatus.ERROR) for item in results)
    return 1 if failed else 0


def cmd_test(_: argparse.Namespace) -> int:
    results = run_offline_tests()
    payload = {
        "mode": "offline",
        "results": [{"case": label, **result.to_dict()} for label, result in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    failed = any(result.status == CheckStatus.ERROR for _, result in results)
    return 1 if failed else 0


def _seconds_until(target: datetime) -> float:
    return max(0.0, (target - now()).total_seconds())


def _is_auth_error(message: str) -> bool:
    return is_auth_error_message(message)


def _ensure_session(ctx: SessionContext | None) -> SessionContext:
    return ensure_session(ctx)


def cmd_daemon(args: argparse.Namespace) -> int:
    setup_logging(verbose=args.verbose)
    load_dotenv()
    acquire_daemon_lock()
    logger = get_logger()
    log_section("启动监测守护进程 (Asia/Shanghai)")

    completed: set[str] = set()
    current_date = now().date()
    session_ctx: SessionContext | None = None

    while True:
        dt = now()
        if dt.date() != current_date:
            completed.clear()
            current_date = dt.date()
            session_ctx = None

        for task in TASKS:
            if task.name in completed:
                continue
            if not should_run_task(task, dt):
                continue

            check_dt = datetime.combine(dt.date(), task.check_time, tzinfo=dt.tzinfo)
            if dt < check_dt:
                continue

            session_ctx = _ensure_session(session_ctx)
            logger.info("触发监测: %s", task.name)
            result = check_task(session_ctx.session, task, session_ctx.bearer_token)
            if result.status == CheckStatus.ERROR and _is_auth_error(result.message):
                logger.info("会话失效，重新登录")
                session_ctx = login_session(reason="会话失效")
                result = check_task(session_ctx.session, task, session_ctx.bearer_token)
            log_task_result(result.task, result.status.value, result.message, matched_title=result.matched_title)
            print(json.dumps(result.to_dict(), ensure_ascii=False), flush=True)
            completed.add(task.name)

            if result.status in (CheckStatus.FAILED, CheckStatus.ERROR):
                logger.error("[ALERT] %s 监测失败: %s", task.name, result.message)
                if not args.no_notify:
                    notify_failure(result, source="daemon")

        upcoming = []
        for task in TASKS:
            if task.name in completed or not should_run_task(task, dt):
                continue
            check_dt = datetime.combine(dt.date(), task.check_time, tzinfo=dt.tzinfo)
            if check_dt > dt:
                upcoming.append((check_dt, task.name))

        if upcoming:
            upcoming.sort(key=lambda item: item[0])
            sleep_for = _seconds_until(upcoming[0][0])
            sleep_for = min(sleep_for, 60.0)
            logger.debug("下次监测: %s (%ds 后)", upcoming[0][1], int(sleep_for))
        else:
            sleep_for = 60.0
            logger.debug("今日任务已全部处理，%ds 后重新检查", int(sleep_for))

        time.sleep(sleep_for)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="自动化写稿任务验证")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出全部任务及监测时间")
    list_parser.set_defaults(func=cmd_list)

    run_parser = subparsers.add_parser("run", help="执行验证")
    run_group = run_parser.add_mutually_exclusive_group()
    run_group.add_argument("--due", action="store_true", help="执行已到监测时间的任务（默认）")
    run_group.add_argument("--all", action="store_true", help="列出今日全部适用任务，未到监测时间的标记为 skipped")
    run_parser.add_argument("--task", help="仅执行指定任务")
    run_parser.add_argument("--force", action="store_true", help="忽略监测时间限制，强制执行")
    run_parser.add_argument("--mock", action="store_true", help="使用 fixture 离线模拟，不请求真实接口")
    run_parser.add_argument("--skip-share", action="store_true", help="live 模式下跳过早报推送")
    run_parser.add_argument("--fixture", help="mock 模式使用的 fixture 文件名")
    run_parser.add_argument("--date", help="mock/验证使用的日期，如 2026-09-07")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="输出 DEBUG 级别日志")
    run_parser.add_argument("--no-notify", action="store_true", help="失败时不发送企微通知")
    run_parser.set_defaults(func=cmd_run)

    test_parser = subparsers.add_parser("test", help="离线逻辑测试（无需账号权限）")
    test_parser.set_defaults(func=cmd_test)

    daemon_parser = subparsers.add_parser("daemon", help="守护进程模式，按监测时间自动执行")
    daemon_parser.add_argument("-v", "--verbose", action="store_true", help="输出 DEBUG 级别日志")
    daemon_parser.add_argument("--no-notify", action="store_true", help="失败时不发送企微通知")
    daemon_parser.set_defaults(func=cmd_daemon)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run" and not args.all and not args.task:
        args.due = True

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
