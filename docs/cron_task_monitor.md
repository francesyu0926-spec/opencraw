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

## Elasticsearch（dcelk）

`config/cron_tasks.yaml` 已配置：

- URL：`http://dcelk.sfccn.com:9200`
- 用户名：`quotemonitor`
- **密码只放在环境变量**，参考 `config/elk.env.example`

### Windows PowerShell

```powershell
cd D:\Document\CODE\opencraw
$env:ELASTICSEARCH_PASSWORD = "你的密码"

# 先测连通性
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --check-elk

# 在开发机上用 ELK 查任务日志（不依赖 Linux 上的 /data/zxt/... 路径）
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode elk --json
```

### Linux / macOS

```bash
export ELASTICSEARCH_PASSWORD='你的密码'
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --check-elk
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode elk --json
```

环境变量会 **覆盖** YAML 中的 `elasticsearch.url` / `username`（便于多环境切换）。

## ES 查询结构（与 quotemonitor 一致）

对每个任务向索引（如 `logstash-sync-mongo-*`）发起 `_search`，核心 DSL 为：

```json
{
  "query": {
    "bool": {
      "should": [
        { "match": { "msg": "CBD_PUB_BOARD_INFO" } },
        { "match": { "msg": "主题成分股" } }
      ],
      "minimum_should_match": 1,
      "filter": [
        { "range": { "@timestamp": { "gte": "now/d", "lte": "now" } } }
      ]
    }
  },
  "size": 1000,
  "sort": [{ "@timestamp": { "order": "asc" } }]
}
```

- 日志字段默认 **`msg`**（`elasticsearch.message_field`）
- 时间窗默认 **`now/d` ~ `now`**（查当天批任务）；15 分钟滚动探活可在 YAML 改为 `timestamp_gte: now-15m`
- 任务级可增加关键字：`elk_msg_keywords: ["logstash-sync", "同步完成"]`

打印某任务的 query（不访问 ES）：

```powershell
python -m scripts.cron_task_monitor --task CBD_PUB_BOARD_INFO --print-elk-query
```

## 运行模式

配置项 **`monitor_mode: elk`**（已在 `cron_tasks.yaml` 中设置）：**只查 ELK**，不会去本机找 `/usr/local/zxt/task/logs` 等路径。

| `--mode` | 说明 |
|----------|------|
| `auto`（默认） | 读 YAML 的 `monitor_mode`；未设置且配了 ES 则用 `elk` |
| `elk` | 只查 ES（办公机 / 跳板机推荐） |
| `local` | 只读本机 `log_dir`（任务服务器） |
| `both` | 本地 + ES 合并 |

退出码：`0` 无告警，`1` 有告警，`2` 配置或参数错误。

## Cron 示例（任务机）

```cron
15 2 * * * cd /opt/opencraw && python3 -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode local --notify
0 8 * * * cd /opt/opencraw && python3 -m scripts.cron_task_monitor -c config/cron_tasks.yaml --mode both --notify --json
```

## 配置说明

编辑 `config/cron_tasks.yaml`：任务 ID、计划开始/预计结束、服务器、`log_dir`、ELK 索引模式、通知人。

| 变量 | 说明 |
|------|------|
| `ELASTICSEARCH_URL` / `ES_URL` | ES 地址（可选，默认读 YAML） |
| `ELASTICSEARCH_USER` / `ES_USERNAME` | 用户名（可选，默认读 YAML） |
| `ELASTICSEARCH_PASSWORD` / `ES_PASSWORD` | **必填**（若 ES 开启认证） |
| `ELASTICSEARCH_API_KEY` | ApiKey 认证（优先于 Basic） |
| `ALERT_WEBHOOK_URL` | 告警 JSON POST 地址 |
