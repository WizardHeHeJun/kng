# KNG — Knowledge-driven Next-Gen Agent Framework

基于双知识库（能力库 + 项目库）的知识驱动型 Agent 框架，以 Claude Code 插件形式运行。通过结构化的知识管理和闭环学习机制，让 AI 在特定领域持续积累经验、越用越准。

核心特性：
- **双知识库体系**：通用能力库（领域方法论 / 技能工具箱）+ 项目知识库（业务模块、历史经验、约束规范）
- **可调用技能**：能力库中的技能文件即插即用，按需匹配和组合
- **知识闭环**：输入 → 产出 → 反馈 → 演进，持续学习改进
- **领域无关框架**：同一引擎可适配 QA、前端、后端、运营等多个领域
- **双存储模式**：文件模式（YAML + Markdown）或 SQLite 模式（结构化 + FTS5 全文检索）

## 1. 前置条件

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Node.js 18+
- Python 3.10+（SQLite 模式需要）
- `lark-cli`（飞书文档抓取）+ 飞书授权：
  ```bash
  lark-cli config init --new
  lark-cli auth login --scope “drive:drive:readonly docs:document:readonly wiki:wiki:readonly”
  ```

## 2. 安装

只需一个命令即可安装：

```bash
npx kng-plugin install
```

或者在 Claude Code 里的插件市场安装：

```
/plugin marketplace add WizardHeHeJun/kng
/plugin install kng
```

安装后执行 `/reload-plugins` 激活。

安装时会自动在 `~/.kng-plugin/` 下创建数据目录（可通过 `KNG_HOME` 环境变量自定义位置）。

### 卸载

```bash
npx kng-plugin uninstall
```

## 3. 命令一览

| 命令 | 功能 |
|------|------|
| `/kng-init <project-id>` | 初始化项目知识库（支持 `--from-lark <url>` 从飞书文档自动提取模块和关系） |
| `/kng-kb list\|add\|import` | 管理知识库条目（列表 / 交互添加 / 从飞书导入，支持子文档递归） |
| `/kng-code import\|link` | 导入本地文件（源代码 / 文档）到知识库，支持文档与代码元数据互链 |
| `/kng-evolve` | 回顾产出，将反馈智能路由回知识库（学习闭环） |
| `/kng-select [project-id]` | 切换活跃项目知识库 |

## 4. 快速开始

```bash
# 1. 初始化项目（从飞书总览文档自动提取模块图谱）
/kng-init my-project --from-lark <总览文档URL>

# 2. 导入项目文档到知识库（保留原始内容 + 自动审查反馈 + 递归子文档）
/kng-kb import --from-lark <文档URL> --type project

# 3. 导入关联源代码，与策划案建立互链
/kng-code link --doc battle-skill-system.md --code "src/battle/**/*.ts"

# 4. 完成工作后，反馈学习，演进知识库
/kng-evolve
```

## 5. 双知识库架构

| 知识库 | 位置 | 用途 | 更新方式 |
|--------|------|------|----------|
| **能力库** | `~/.kng-plugin/kb/capability/` | 领域方法论、可调用技能工具箱 | 用户自行维护 / `/kng-kb add` |
| **项目库** | `~/.kng-plugin/kb/projects/<project-id>/` | 项目业务模块、历史经验、约束规范 | `/kng-kb add` / `/kng-kb import` / `/kng-code import` / `/kng-evolve` |

所有知识库数据存放在 `~/.kng-plugin/` 下（可通过 `KNG_HOME` 环境变量自定义），不受插件更新影响。项目库按项目隔离，初始化后包含：

- `project-overview.md` — 项目类型、核心系统、高风险区域
- `project-modules.yaml` — 模块注册表与知识图谱（模块 + 关系）
- `bug-patterns.md` — 历史问题模式
- `test-constraints.md` — 测试约束与规范

## 6. SQLite 存储层

安装和 `/kng-init` 时自动启用，支持结构化查询、全文检索和模块关联图谱。配置文件 `~/.kng-plugin/kng.config.json` 中的 `db_path` 字段指向数据库路径；删除该字段可退回纯文件模式。

### 数据库管理

```bash
# 初始化数据库
python kng-plugin/scripts/db.py init --db ~/.kng-plugin/kng.db

# 导入现有知识
python kng-plugin/scripts/kb_import.py \
  --db ~/.kng-plugin/kng.db \
  --capability-dir ~/.kng-plugin/kb/capability \
  --project-dir ~/.kng-plugin/kb/projects/my-project \
  --project-id my-project --verbose

# 查看统计
python kng-plugin/scripts/db.py stats --db ~/.kng-plugin/kng.db
```

### Web 可视化

```bash
# 启动 Web 查看器（默认 http://127.0.0.1:8787）
python kng-plugin/scripts/db_viewer.py --db ~/.kng-plugin/kng.db
```

功能：Dashboard 总览、数据浏览（分页）、全文搜索（中文 LIKE 回退）、模块关联图谱可视化、JSON API。

配置了 `db_path` 后，插件在每次对话启动时会自动检测并后台启动查看器。

### 知识检索

```bash
# 文件模式
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --capability-dir ~/.kng-plugin/kb/capability \
  --project-dir ~/.kng-plugin/kb/projects/my-project

# DB 模式（关键词 / 全文检索）
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --db ~/.kng-plugin/kng.db --project my-project --mode fts
```

### 数据库 Schema

| 表 | 用途 |
|----|------|
| `projects` | 项目元数据 |
| `modules` | 业务模块注册 |
| `module_relations` | 模块间关联图谱（depends_on / feeds_into / shares_state / triggers） |
| `kb_entries` + `kb_entries_fts` | 知识条目 + FTS5 全文索引 |
| `skills` / `skill_scenarios` | 技能注册表 + 场景模板 |
| `synonyms` | 同义词/别名组 |
| `test_designs` | 测试设计产出追踪 |
| `learning_feedback` | 学习反馈记录 |

## 7. 配置文件

`~/.kng-plugin/kng.config.json`：

```json
{
  “active_project”: “my-project”,
  “kb_root”: “~/.kng-plugin/kb”,
  “output_dir”: “./test-output”,
  “db_path”: “~/.kng-plugin/kng.db”
}
```

- `active_project`：当前活跃项目，所有命令默认使用该项目
- `kb_root`：知识库根目录（默认 `~/.kng-plugin/kb`）
- `output_dir`：产出输出目录（相对于当前工作目录）
- `db_path`：默认启用，指向 SQLite 数据库路径；删除该字段可退回纯文件模式

可通过 `KNG_HOME` 环境变量自定义数据目录位置（默认 `~/.kng-plugin`）。

## 8. 项目结构

```text
~/.kng-plugin/                    # 用户数据目录 (KNG_HOME)
  kng.config.json                 # 全局配置
  kng.db                          # SQLite 数据库（可选）
  kb/
    capability/                   # 能力库（用户自行维护，插件更新不影响）
      skill-registry.yaml         # 技能注册表（自动生成）
      synonym-aliases.yaml        # 同义词配置
    projects/
      <project-id>/               # 项目知识库（按项目隔离）

kng-plugin/                       # 插件包（npm 安装，只读）
  scripts/
    db.py                         # SQLite 数据库管理
    db_viewer.py                  # Web 可视化查看器
    kb_import.py                  # 批量导入工具
    retrieve_kb.py                # 知识检索引擎（文件/DB 双模式）
    generate_registry.py          # 能力库索引自动生成
  skills/
    kng-init/                     # 项目初始化
    kng-kb/                       # 知识库管理（飞书文档导入）
    kng-code/                     # 本地代码/文件导入 + 文档互链
    kng-evolve/                   # 反馈学习进化
    kng-select/                   # 项目切换
  schemas/
    test_design.schema.json       # 测试设计 JSON Schema
bin/
  cli.js                          # 安装/卸载 CLI 入口
```

## 9. 知识闭环

```
能力库 + 项目库 → AI 产出 → 实际验证 → /kng-evolve → 知识库更新 → 下次更准确
```

1. 通过 `/kng-kb import` 导入飞书文档、`/kng-code import` 导入本地代码，持续积累项目知识
2. 通过 `/kng-code link` 将策划案与实现代码互链，形成完整的设计-实现知识对
3. AI 基于双知识库上下文完成任务，产出结构化结果
4. 实际执行中发现遗漏或新问题
5. `/kng-evolve` 回顾产出，反馈智能路由到对应知识文件
6. 知识库自动更新，下次任务时自动受益 — 越用越准

## License

MIT
