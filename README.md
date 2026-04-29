# KNG — Knowledge-driven Next-Gen Test Agent

基于双知识库（能力库 + 项目库）的智能测试设计系统。输入飞书策划案文档，自动匹配知识库上下文，生成结构化测试设计。

支持两种存储模式：
- **文件模式**：YAML + Markdown 扁平文件，适合小型项目
- **SQLite 模式**：结构化数据库 + FTS5 全文检索，适合大型项目（百级策划案、多模块关联）

## 1. 前置条件

- Python 3.10+（SQLite 为 stdlib，无需额外安装）
- `lark-cli`（飞书文档抓取）
- 飞书授权（建议 user 身份）：
  ```bash
  lark-cli config init --new
  lark-cli auth login --scope “drive:drive:readonly docs:document:readonly wiki:wiki:readonly”
  ```

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. Claude Code 插件安装

### 一键安装（推荐）

```bash
npx kng-plugin install
```

### 手动安装

在 Claude Code 中执行（替换 `your-org/kng` 为你的 GitHub 用户名/仓库名）：

```bash
# 第一步：添加 marketplace
/plugin marketplace add your-org/kng

# 第二步：安装插件
/plugin install kng@kng-marketplace
```

### 卸载

```bash
npx kng-plugin uninstall
```

安装后通过 slash command 驱动：

| 命令 | 功能 |
|------|------|
| `/kng-init <project-id>` | 初始化项目知识库 + 数据库 |
| `/kng-test <feishu-url>` | 从飞书文档生成测试设计 |
| `/kng-kb list\|add\|import` | 管理知识库条目 |
| `/kng-evolve` | 反馈学习，进化知识库 |
| `/kng-select <project-id>` | 切换当前活跃项目 |

### 快速开始

```bash
# 1. 初始化项目（自动创建 DB）
/kng-init my-game --from-lark <总览文档URL>

# 2. 导入策划案
/kng-kb import --from-lark <策划案URL> --type project

# 3. 生成测试设计
/kng-test <策划案URL>

# 4. 反馈学习
/kng-evolve
```

## 4. 独立脚本使用

### 4.1 单文档版本

```bash
python tools/lark_test_agent.py --url “https://your-domain.feishu.cn/docx/xxxxxxxx”
```

### 4.2 双知识库版本

```bash
python tools/dual_kb_test_agent.py --project-id demo-game --url “https://your-domain.feishu.cn/docx/xxxxxxxx”
```

### 4.3 一键验证

```bash
validate_run.bat demo-game “https://your-domain.feishu.cn/docx/xxxxxxxx”
```

## 5. SQLite 存储层

大型项目推荐启用 SQLite 模式，支持结构化查询、全文检索和模块关联图谱。

### 数据库管理

```bash
# 初始化数据库
python kng-plugin/scripts/db.py init --db ./kng.db

# 导入现有知识
python kng-plugin/scripts/kb_import.py \
  --db ./kng.db \
  --capability-dir kng-plugin/kb/capability \
  --project-dir kb/projects/demo-game \
  --project-id demo-game --verbose

# 查看统计
python kng-plugin/scripts/db.py stats --db ./kng.db
```

### 知识检索（双模式）

```bash
# 文件模式
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --capability-dir kng-plugin/kb/capability \
  --project-dir kb/projects/demo-game

# DB 模式（关键词匹配）
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --db ./kng.db --project demo-game --mode keyword

# DB 模式（全文检索）
python kng-plugin/scripts/retrieve_kb.py \
  --query “并发 幂等” \
  --db ./kng.db --project demo-game --mode fts
```

### 数据库 Schema（10 张表）

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

## 6. 配置文件

`kng.config.json`（工作区根目录）：

```json
{
  “active_project”: “demo-game”,
  “kb_root”: “./kb”,
  “output_dir”: “./test-output”,
  “db_path”: “./kng.db”
}
```

- `db_path` 为可选字段，存在且文件有效时启用 SQLite 模式，否则使用文件模式

## 7. 输出

默认输出到 `test-output/`：

- `*-source.md`：抓取到的原始文档内容
- `*-test-design.json`：结构化测试产出
- `*-test-design.md`：可读版测试设计

## 8. 项目目录

```text
kng-plugin/
  kb/capability/                # 通用测试能力库（跨项目复用）
    skill-registry.yaml         # 技能注册表
    synonym-aliases.yaml        # 同义词配置
    test-design-guidelines.md   # 测试设计规范
    api-test-script-playbook.md # 接口脚本手册
  scripts/
    retrieve_kb.py              # 知识检索引擎（文件/DB 双模式）
    db.py                       # SQLite 数据库抽象层
    kb_import.py                # 批量导入工具
  skills/
    kng-test/                   # 测试设计生成
    kng-kb/                     # 知识库管理
    kng-evolve/                 # 反馈学习进化
    kng-init/                   # 项目初始化
    kng-select/                 # 项目切换
kb/
  projects/
    demo-game/                  # 项目知识库（按项目隔离）
schemas/
  test_design.schema.json       # 测试设计 JSON Schema
tools/
  lark_test_agent.py            # 单文档版本
  dual_kb_test_agent.py         # 双知识库版本
validate_run.bat                # 一键验证入口
```
