# T 版模型任务波动监控

部署 common 后端后，在服务器的项目目录执行一次：

```bash
bash scripts/install_channel_monitor_cron.sh
crontab -l | grep huixing-channel-monitor
```

安装脚本沿用项目 `.venv/bin/python`；如服务器使用其他虚拟环境，可先设置 `CHANNEL_MONITOR_PYTHON`。运行失败会在 `logs/channel-monitor.log` 留下错误并返回非零退出码。同一时刻只允许一个检查进程运行。

监控每 3 分钟读取最近 10 分钟内 T 版图像编辑模型的完成、失败任务。只有同一模型连续 3 个 `provider_failed` 才开启一条普通波动通知。通知至少保留 5 分钟；近 5 分钟没有同模型服务方失败且出现 3 个连续成功任务后自动关闭。无新任务时维持原状。每种终态单轮最多读取 2000 条，超量时跳过状态变更并记录错误。管理员手工开启的通告使用不同 `biz_key`，不会被自动流程覆盖。

停用自动监控时，从 crontab 删除包含 `huixing-channel-monitor` 的一行即可；已发布的自动通知仍需在后台关闭。该检测不依赖用户打开管理后台。
