# KNG — Knowledge-driven Next-Gen Test Agent

基于双知识库（能力库 + 项目库）的智能测试设计系统，以 Claude Code 插件形式运行。输入飞书策划案文档，自动匹配知识库上下文，生成结构化测试设计。

核心特性：
- **双知识库体系**：通用能力库（测试方法论）+ 项目知识库（业务模块、bug 模式、测试约束）
- **可调用技能**：预定义的测试技能工具箱（功能路径、边界值、异常容错、状态流转、权限安全、接口自动化）
- **知识闭环**：生成 → 执行 → 反馈 → 演进，持续学习改进
- **领域无关框架**：同一引擎可适配 QA、前端、后端等多个领域
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

### npm 全局安装（推荐）

```bash
npm install -g kng-plugin
kng-plugin install
```

### 一次性安装（无需全局）

```bash
npx kng-plugin install
```

### 从 GitHub 安装

```bash
npx kng-plugin install --from-github
# 或直接
npx github:WizardHeHeJun/kng install
```

### 手动安装

在 Claude Code 中执行：

```bash
# 第一步：添加 marketplace
/plugin marketplace add WizardHeHeJun/kng

# 第二步：安装插件
/plugin install kng@kng-marketplace
```

安装后执行 `/reload-plugins` 激活。

安装时会自动在 `~/.kng-plugin/` 下创建数据目录（可通过 `KNG_HOME` 环境变量自定义位置）。

### 卸载

```bash
kng-plugin uninstall
# 如果全局安装了，还需移除全局包：
npm uninstall -g kng-plugin
```

## 3. 命令一览

| 命令 | 功能 |
|------|------|
| `/kng-init <project-id>` | 初始化项目知识库（支持 `--from-lark <url>` 从飞书文档自动提取模块和关系） |
| `/kng-test <feishu-url>` | 从飞书文档生成结构化测试设计（JSON + Markdown） |
| `/kng-kb list\|add\|import` | 管理知识库条目（列表 / 交互添加 / 从飞书导入） |
| `/kng-evolve` | 回顾测试产出，将反馈智能路由回知识库 |
| `/kng-select [project-id]` | 切换活跃项目知识库 |

## 4. 快速开始

```bash
# 1. 初始化项目（从飞书总览文档自动提取模块图谱）
/kng-init my-game --from-lark <总览文档URL>

# 2. 导入策划案到项目知识库（保留原始内容 + 自动审查反馈）
/kng-kb import --from-lark <策划案URL> --type project

# 3. 从策划案生成测试设计
/kng-test <策划案URL>

# 4. 执行测试后，反馈学习，演进知识库
/kng-evolve
```

## 5. 双知识库架构

| 知识库 | 位置 | 用途 | 更新方式 |
|--------|------|------|----------|
| **能力库** | `~/.kng-plugin/kb/capability/` | 通用测试方法论、技能工具箱 | 用户自行维护 / `/kng-kb add` |
| **项目库** | `~/.kng-plugin/kb/projects/<project-id>/` | 项目业务模块、架构设计、历史问题 | `/kng-kb add` / `/kng-kb import` / `/kng-evolve` |

所有知识库数据存放在 `~/.kng-plugin/` 下（可通过 `KNG_HOME` 环境变量自定义），不受插件更新影响。项目库按项目隔离，初始化后包含：

- `project-overview.md` — 项目类型、核心系统、高风险区域
- `project-modules.yaml` — 模块注册表与知识图谱（模块 + 关系）
- `bug-patterns.md` — 历史问题模式
- `test-constraints.md` — 测试约束与规范

## 6. SQLite 存储层（可选）

在 `~/.kng-plugin/kng.config.json` 中配置 `db_path` 即可启用，支持结构化查询、全文检索和模块关联图谱。

### 数据库管理

```bash
# 初始化数据库
python kng-plugin/scripts/db.py init --db ~/.kng-plugin/kng.db

# 导入现有知识
python kng-plugin/scripts/kb_import.py \
  --db ~/.kng-plugin/kng.db \
  --capability-dir ~/.kng-plugin/kb/capability \
  --project-dir ~/.kng-plugin/kb/projects/demo-game \
  --project-id demo-game --verbose

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
  --project-dir ~/.kng-plugin/kb/projects/demo-game

# DB 模式（关键词 / 全文检索）
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --db ~/.kng-plugin/kng.db --project demo-game --mode fts
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
  “active_project”: “demo-game”,
  “kb_root”: “~/.kng-plugin/kb”,
  “output_dir”: “./test-output”,
  “db_path”: “~/.kng-plugin/kng.db”
}
```

- `active_project`：当前活跃项目，所有命令默认使用该项目
- `kb_root`：知识库根目录（默认 `~/.kng-plugin/kb`）
- `output_dir`：测试输出目录（相对于当前工作目录）
- `db_path`：可选，存在且文件有效时启用 SQLite 模式，否则使用文件模式

可通过 `KNG_HOME` 环境变量自定义数据目录位置（默认 `~/.kng-plugin`）。

## 8. 输出

默认输出到 `test-output/`：

| 文件 | 内容 |
|------|------|
| `*-source.md` | 抓取到的原始文档 |
| `*-test-design.json` | 结构化测试产出（测试点、用例、风险、待确认事项） |
| `*-test-design.md` | 可读版测试设计报告 |

## 9. 项目结构

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
    kng-test/                     # 测试设计生成
    kng-kb/                       # 知识库管理
    kng-evolve/                   # 反馈学习进化
    kng-select/                   # 项目切换
    test-design-methodology/      # 测试设计方法论（自动加载）
  schemas/
    test_design.schema.json       # 测试设计 JSON Schema
bin/
  cli.js                          # 安装/卸载 CLI 入口
```

## 10. 知识闭环

```
策划文档 → /kng-test → 测试设计 → 实际执行 → /kng-evolve → 知识库更新 → 下次更准确
```

1. `/kng-test` 生成初始测试设计
2. 按设计执行测试，发现遗漏或新问题
3. `/kng-evolve` 回顾产出，反馈智能路由到对应知识文件
4. 知识库自动更新，下次 `/kng-test` 时自动受益

## License

MIT
