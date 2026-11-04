#!/usr/bin/env bash
# 统一监控调度（Linux cron）。建议每 5 分钟执行一次。
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH=.

set -a
[[ -f config/elk.env ]] && . config/elk.env
[[ -f config/health.env ]] && . config/health.env
[[ -f config/wecom.env ]] && . config/wecom.env
[[ -f config/writing.env ]] && . config/writing.env
set +a

exec python3 -m scripts.cron_task_monitor --run-scheduled --json "$@"
