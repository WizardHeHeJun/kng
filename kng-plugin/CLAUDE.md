# KNG Plugin — 全局行为

## KNG Home 路径约定

所有用户数据存放在 `KNG_HOME` 目录下：

- `KNG_HOME` = 环境变量 `$KNG_HOME`（如已设置）|| `$HOME/.kng-plugin`
- 配置文件：`${KNG_HOME}/kng.config.json`
- 能力库：`${KNG_HOME}/kb/capability/`
- 项目库：`${KNG_HOME}/kb/projects/<project-id>/`
- 数据库：`${KNG_HOME}/kng.db`（可选）

插件代码（脚本、Schema、技能定义）通过 `${CLAUDE_PLUGIN_ROOT}` 引用，保持只读。

## 知识库查看器自启动

当本插件处于活跃状态时，**在每次对话的第一次工具调用前**，执行以下自启动检查：

1. 解析 `KNG_HOME`（`$KNG_HOME` || `$HOME/.kng-plugin`），读取 `${KNG_HOME}/kng.config.json`，提取 `db_path` 字段
2. 如果 `db_path` 存在且对应的 `.db` 文件存在，则检查查看器是否已在运行：
   ```bash
   curl -s --max-time 1 http://127.0.0.1:8787/api/stats
   ```
3. 如果上一步失败（查看器未运行），后台启动查看器：
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/db_viewer.py" --db "${DB_PATH}" --port 8787 &
   ```
4. 向用户简要通知：「知识库查看器已启动：http://127.0.0.1:8787」

如果 `${KNG_HOME}/kng.config.json` 不存在或没有 `db_path`，跳过此检查，不做任何提示。