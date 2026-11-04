# opencraw 统一监控（HTTP health / WebSocket / ELK 数据同步）
# 构建：docker build -t opencraw-monitor .
# 运行：docker compose up -d --build
# 或：docker run --rm --env-file config/elk.env ...

FROM python:3.11-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apk add --no-cache tzdata ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY requirements-monitor.txt ./
RUN pip install --no-cache-dir -r requirements-monitor.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY config/ ./config/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# 密钥勿写入镜像：运行时挂载或 --env-file
#   config/elk.env      → ELASTICSEARCH_PASSWORD 等
#   config/health.env   → QUOTES_LOGIN_CODE / QUOTES_LOGIN_PASSWORD 等
#   config/wecom.env    → WECOM_WEBHOOK_URL_ELK / _WS / _HEALTH

# 与 config/monitor_schedule.yaml 中 dispatcher_interval_minutes=5 对齐
CMD ["sh", "-c", "while true; do python -m scripts.cron_task_monitor --run-scheduled --json || true; sleep 300; done"]
