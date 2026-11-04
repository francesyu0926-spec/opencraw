# automated_writing（写稿任务验证）

自 [automated_writing](https://gitlab.com/) 项目 vendored 的 `verify` 包，由 opencraw 统一调度（job `writing`）或单独运行：

```powershell
python -m scripts.cron_task_monitor --writing-monitor --json
```

环境变量见 `config/writing.env.example`。任务时刻见 `verify/tasks.py`（工作日 7:30–20:00 共 7 项）。
