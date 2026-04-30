# KNG Plugin — 全局行为

## 知识库查看器自启动

当本插件处于活跃状态时，**在每次对话的第一次工具调用前**，执行以下自启动检查：

1. 读取工作区根目录的 `kng.config.json`，提取 `db_path` 字段
2. 如果 `db_path` 存在且对应的 `.db` 文件存在，则检查查看器是否已在运行：
   ```bash
   curl -s --max-time 1 http://127.0.0.1:8787/api/stats
   ```
3. 如果上一步失败（查看器未运行），后台启动查看器：
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/db_viewer.py" --db "${DB_PATH}" --port 8787 &
   ```
4. 向用户简要通知：「知识库查看器已启动：http://127.0.0.1:8787」

如果 `kng.config.json` 不存在或没有 `db_path`，跳过此检查，不做任何提示。