# 定时任务监控（§2.1）

逻辑与 **mdimonitor** [`tests/test_quotes_es.py`](http://gitlab.sfccn.com/application/monitor_quote_system/mdimonitor/-/blob/main/tests/test_quotes_es.py) 一致：

1. 一次 ES 查询：`logstash-zxt-terminal-task-*` + `logstash-sync-mongo-*`
2. `bool.should`：对每个任务 id 做 `match(msg, keyword)`
3. 时间窗：**`now/d` ~ `now`**（覆盖 PDF 中 00:00–04:05 批任务；滚动探活可改 `now-15m`）
4. 扫 hit 解析三类日志：
   - `开始执行任务: …,执行时间：…` → 延迟启动 > 5 分钟
   - `任务执行完成:…,耗时：…秒` → 耗时 > 计划时长 + 10 分钟
   - 含 `执行失败` 且命中任务 keyword → 失败

## 运行

```powershell
pip install -r requirements-monitor.txt
$env:ELASTICSEARCH_PASSWORD = "密码"
$env:WECOM_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"

python -m scripts.cron_task_monitor --check-elk
python -m scripts.cron_task_monitor --print-elk-query
python -m scripts.cron_task_monitor --json
```

有告警且已配置 **`WECOM_WEBHOOK_URL`** 时，会**自动**推送企业微信文本消息（`msgtype: text`）。仅本地看结果可加 **`--no-notify`**。

## 配置

`config/cron_tasks.yaml` 中：

- `elasticsearch.url` / `username` + 环境变量密码
- `elasticsearch.indices`：与 mdimonitor 相同的两条 index pattern
- `tasks[].id`：作为 `msg_keywords`（对应 `data.Task` 类属性名）
- `scheduled_start` / `expected_end`：供 `calculate_time_diff_by_task` 计算计划时长

## 单测

```bash
PYTHONPATH=. python -m unittest tests.test_quotes_es -v
```
