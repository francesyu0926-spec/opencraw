#!/usr/bin/env sh
# 统一调度循环：按 wall-clock 对齐 dispatcher 间隔（默认 5 分钟），避免 sleep 300 相位漂移导致 job 永远 not_due。
set -eu

SCHEDULE="${MONITOR_SCHEDULE_CONFIG:-config/monitor_schedule.production.yaml}"
INTERVAL="${DISPATCHER_INTERVAL_MINUTES:-5}"

while true; do
  python -m scripts.cron_task_monitor --run-scheduled \
    --schedule-config "$SCHEDULE" \
    --json || true

  python - <<'PY'
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

interval = max(1, int(os.environ.get("DISPATCHER_INTERVAL_MINUTES", "5")))
tz_name = os.environ.get("TZ", "Asia/Shanghai")
tz = ZoneInfo(tz_name)
now = datetime.now(tz)
mod = now.minute % interval
sec = now.second + now.microsecond / 1e6
if mod == 0 and sec < 2.0:
    wait = interval * 60 - sec
else:
    wait = ((interval - mod) % interval) * 60 - sec
    if wait <= 0.5:
        wait += interval * 60
time.sleep(wait)
PY
done
