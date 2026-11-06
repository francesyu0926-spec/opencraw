#!/usr/bin/env bash
# 生产监控调度（config/monitor_schedule.production.yaml）
# cron 示例（先 cd 到仓库根，再用相对路径）：
# */5 * * * * cd /path/to/opencraw && ./scripts/run_monitor_production.sh >> var/log/opencraw_monitors.log 2>&1
# 企微策略见 monitor_schedule.production.yaml（health/ws 整点；elk/writing 跑完；success_until）
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

exec python3 -m scripts.cron_task_monitor \
  --run-scheduled \
  --schedule-config config/monitor_schedule.production.yaml \
  --json \
  "$@"
