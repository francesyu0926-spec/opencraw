# 定时任务监控（§2.1）

## 能力

- 解析任务日志中的 **开始 / 结束 / 成功 / 失败**（结构化打点 + 关键字兜底）
- 告警规则（与运维文档一致）：
  - 计划开始后 **>5 分钟** 仍无启动 → `no_start` / `late_start`
  - 日志标记 **failure** → `execution_failed`
  - 预计结束后 **>10 分钟** 仍未成功完成 → `execution_overtime`
- 可选对接 **Elasticsearch**（`logstash-sync-mongo-*`、`logstash-zxt-task-*`）
- 可选 **Webhook** 通知（`ALERT_WEBHOOK_URL`）

## 推荐日志打点（开发侧）

任务开始与结束各打一行，便于 ELK 与本地文件统一解析：

```text
[TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=start ts=2025-11-03T01:00:01+08:00
[TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=end status=success ts=2025-11-03T01:02:59+08:00
```

失败示例：

```text
[TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=end status=failure message=sync timeout
```

## 安装

```bash
pip install -r requirements-monitor.txt
```

## 运行

在仓库根目录：

```bash
# 本机日志目录（需在对应服务器上执行，或挂载相同 log_dir）
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode local --json

# 合并 ELK（需环境变量）
export ELASTICSEARCH_URL=https://es.example.com:9200
export ELASTICSEARCH_API_KEY=...
python -m scripts.cron_task_monitor --mode both --notify

# 仅检查单个任务 / 模拟时间（联调）
python -m scripts.cron_task_monitor --task CBD_PUB_BOARD_INFO --at 2025-11-03T01:06:00+08:00 --json
```

退出码：`0` 无告警，`1` 有告警，`2` 配置或参数错误。

## Cron 示例

在 **124.220.0.191** / **116.199.203** 等任务机上，于关键任务预计结束之后再跑一轮（文档要求 9 点前批任务完成，可在 02:15、08:00 等多次巡检）：

```cron
15 2 * * * cd /opt/opencraw && /usr/bin/python3 -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode local --notify >> /var/log/cron_task_monitor.log 2>&1
0 8 * * * cd /opt/opencraw && /usr/bin/python3 -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode both --notify --json >> /var/log/cron_task_monitor.log 2>&1
```

## 配置

编辑 `config/cron_tasks.yaml`：任务 ID、计划开始/预计结束、服务器、`log_dir`、ELK 索引模式、通知人。

环境变量：

| 变量 | 说明 |
|------|------|
| `ELASTICSEARCH_URL` / `ES_URL` | ES 地址 |
| `ELASTICSEARCH_API_KEY` | ApiKey 认证（优先） |
| `ELASTICSEARCH_USER` / `ELASTICSEARCH_PASSWORD` | Basic 认证 |
| `ALERT_WEBHOOK_URL` | 告警 JSON POST 地址 |
