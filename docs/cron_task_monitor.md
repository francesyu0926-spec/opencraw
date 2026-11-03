# 定时任务监控（§2.1）

**只查 Elasticsearch（dcelk）**，不登录任务服务器、不读取 `/usr/local/zxt/task/logs` 等本地路径。

## 能力

- 通过 ES `bool` + `match(msg)` 查询任务日志
- 告警：延迟启动、执行失败、超时、ELK 无命中
- 可选 Webhook：`ALERT_WEBHOOK_URL`

## 安装与运行

```bash
pip install -r requirements-monitor.txt
```

### Windows PowerShell

```powershell
cd D:\Document\CODE\opencraw
git pull origin cursor/cron-task-monitor-af56

$env:ELASTICSEARCH_PASSWORD = "实际密码"

python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --check-elk
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml --json
```

无需 `--mode` 参数；脚本固定走 ELK。

### 打印 ES Query（不调 ES）

```powershell
python -m scripts.cron_task_monitor --task CBD_PUB_BOARD_INFO --print-elk-query
```

## Elasticsearch 配置

`config/cron_tasks.yaml`：

```yaml
elasticsearch:
  url: http://dcelk.sfccn.com:9200
  username: quotemonitor
  message_field: msg
  timestamp_gte: now/d
  timestamp_lte: now
```

密码：`ELASTICSEARCH_PASSWORD`（见 `config/elk.env.example`）。

## 任务配置说明

| 字段 | 用途 |
|------|------|
| `log_index_pattern` | **ELK 索引**，如 `logstash-sync-mongo-*` |
| `elk_msg_keywords` | 可选，覆盖默认 match；只取**第一个**关键字 |
| `log_dir` / `server` | 仅文档对照，**脚本不使用** |

## 推荐日志打点

```text
[TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=start ts=2025-11-03T01:00:01+08:00
[TASK_MONITOR] task=CBD_PUB_BOARD_INFO event=end status=success ts=2025-11-03T01:02:59+08:00
```

## 退出码

`0` 无告警，`1` 有告警，`2` 配置错误。
