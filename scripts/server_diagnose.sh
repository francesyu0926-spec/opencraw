#!/usr/bin/env sh
# 生产机快速排查：调度是否在整点跑、整点企微是否应发（不修改服务）。
# 用法：在仓库根目录执行  sh scripts/server_diagnose.sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH=.

echo "=== 时间 / 时区 ==="
date
echo "TZ=${TZ:-<unset>}"

echo ""
echo "=== Docker（若用 compose 部署）==="
if command -v docker >/dev/null 2>&1; then
  docker compose ps 2>/dev/null || docker ps -a --filter name=opencraw-monitor 2>/dev/null || true
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx opencraw-monitor; then
    echo "--- 最近 3 小时日志（含 checked_at / wecom / trial）---"
    docker logs opencraw-monitor --since 3h 2>&1 \
      | grep -E 'checked_at|wecom_|notify_success_trial|WARN: 企微' \
      | tail -40 || true
    echo "--- 10:00 前后 checked_at（应有 :00 而非仅 :05）---"
    docker logs opencraw-monitor --since 24h 2>&1 \
      | grep -E '"checked_at".*T10:0[0-5]' | tail -10 || echo "(无匹配)"
  fi
else
  echo "docker 未安装或不可用"
fi

echo ""
echo "=== cron（若未用 Docker）==="
crontab -l 2>/dev/null | grep -E 'opencraw|run_monitor|run_dispatcher' || echo "(当前用户无相关 crontab)"

echo ""
echo "=== 企微 webhook 是否配置 ==="
python -m scripts.cron_task_monitor --check-wecom 2>&1 || true

echo ""
echo "=== 模拟今天 10:00 整点调度（dry-run，不发企微）==="
TODAY=$(date +%Y-%m-%d)
python -m scripts.cron_task_monitor --run-scheduled \
  --schedule-config config/monitor_schedule.production.yaml \
  --at "${TODAY}T10:00:00+08:00" \
  --dry-run --json 2>&1 \
  | grep -E 'notify_success_trial|wecom_|jobs_run|checked_at' || true

echo ""
echo "说明：整点企微只在调度器在 :00（或 :59 后 45s 内）执行时触发；"
echo "若日志里只有 10:05/10:10 没有 10:00，多为容器重启或未在跑。"
