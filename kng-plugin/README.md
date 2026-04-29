# KNG — Knowledge-driven Test Generator

双知识库驱动的游戏测试设计工具，Claude Code 插件。

## 安装

### 一键安装

```bash
npx kng-plugin install
```

### 手动安装

在 Claude Code 中执行（替换 `your-org/kng` 为你的 GitHub 用户名/仓库名）：

```bash
/plugin marketplace add your-org/kng
/plugin install kng@kng-marketplace
```

### 卸载

```bash
npx kng-plugin uninstall
```

**前置要求**：
- Python 3.10+（KB 检索脚本）
- `lark-cli` 已安装并完成认证（飞书文档抓取）

## 快速开始

### 首次使用：自动引导

首次使用任何 KNG 命令时，插件会自动检测并引导你完成项目知识库的设置：

- **没有项目** → 自动引导创建（调用 `/kng-init`）
- **只有一个项目** → 自动选中
- **多个项目** → 列出所有项目，请你选择

选择后持久化到 `kng.config.json`，后续所有命令自动使用该项目，无需每次指定 `--project`。

### 1. 初始化项目知识库

```
/kng-init my-game                           # 空模板
/kng-init my-game --from-lark <总览文档URL>  # 从策划案自动提取模块和关联
```

创建 `kb/projects/my-game/` 并自动设为当前活跃项目。

### 2. 生成测试设计

```
/kng-test https://example.feishu.cn/docx/xxx
```

自动使用活跃项目的知识库，无需 `--project`。输出到 `test-output/`：
- `*-source.md` — 原始文档
- `*-test-design.json` — 结构化 JSON
- `*-test-design.md` — 可读 Markdown

### 3. 管理知识库

```
/kng-kb list                                    # 查看所有知识库文件
/kng-kb add --type project                      # 添加项目知识条目
/kng-kb import --from-lark <url> --type project  # 从飞书导入
```

### 4. 切换项目

```
/kng-select other-game     # 切换到另一个项目
/kng-select --list         # 查看所有可用项目
/kng-select                # 交互式选择
```

## 架构

### 双知识库体系

| 知识库 | 位置 | 用途 | 更新方式 |
|--------|------|------|----------|
| **基础能力库** | 插件目录 `kb/capability/` | 通用测试方法论、脚本规范、质量门禁 | 随插件更新 / `/kng-kb add` |
| **项目知识库** | 工作目录 `kb/projects/<id>/` | 游戏玩法、系统设计、历史缺陷 | `/kng-kb add` / `/kng-kb import` / 手动编辑 |

### 项目上下文

插件维护一个**活跃项目**概念——所有命令默认使用活跃项目的知识库，无需每次指定 `--project`。

- 首次使用任何 KNG 命令时自动引导选择或创建
- `/kng-init` 创建新项目后自动设为活跃
- `/kng-select` 可随时切换活跃项目
- `--project <id>` 参数可临时覆盖（不改变活跃项目）

### 新项目复用

切换到新项目只需：
1. `/kng-init new-project` — 自动成为活跃项目
2. 填充项目知识（或用 `--from-lark` 自动提取）
3. `/kng-test <url>` — 自动使用新项目

基础能力库自动共享，无需重复配置。

## 命令一览

| 命令 | 说明 |
|------|------|
| `/kng-test <url> [--project <id>]` | 从飞书文档生成测试设计 |
| `/kng-init <project-id> [--from-lark <url>]` | 初始化新项目知识库（自动设为活跃） |
| `/kng-select [<project-id> \| --list]` | 切换活跃项目知识库 |
| `/kng-kb list` | 列出所有知识库文件 |
| `/kng-kb add --type <type>` | 交互式添加知识条目 |
| `/kng-kb import --from-lark <url>` | 从飞书文档导入知识条目 |
| `/kng-evolve [--source <file>]` | 回顾测试产出，将反馈沉淀到知识库 |

## 学习闭环

```
飞书文档 → /kng-test → 测试设计 → 实际执行 → /kng-evolve → 知识库更新 → 下次更准
```

每次使用 `/kng-test` 后，用 `/kng-evolve` 回顾产出：
- 遗漏了哪些场景？→ 补充到能力库或项目库
- 发现了新 bug 模式？→ 沉淀到 `bug-patterns.md`
- 测试方法有改进？→ 更新能力库规范

知识库会随着团队使用不断进化，新人加入时直接受益于前人积累。

## 配置

配置文件 `kng.config.json`（由 `/kng-init` 自动创建，`/kng-select` 更新）：

```json
{
  "active_project": "my-game",
  "kb_root": "./kb",
  "output_dir": "./test-output"
}
```

`active_project` 是所有 KNG 命令的默认项目。首次使用时自动设置，也可通过 `/kng-select` 切换。

## 知识库编写指南

### 项目知识库文件建议

| 文件 | 内容 |
|------|------|
| `project-overview.md` | 游戏类型、核心循环、主要系统、高风险区域 |
| `bug-patterns.md` | 历史缺陷模式、按类型分类（奖励/配置/状态） |
| `test-constraints.md` | 环境要求、数据准备、回归策略、验收标准 |
| `<system-name>.md` | 具体系统的详细设计文档（按需添加） |

### 写作建议

- 使用 Markdown 格式，清晰的标题层级
- 重点写**测试相关**的信息：边界值、异常场景、历史踩坑
- 保持文件精练，每个文件聚焦一个主题
- 关键词丰富有助于检索命中

## 输出格式

参考 `schemas/test_design.schema.json`，输出包含：
- `feature_name` — 功能名称
- `test_points` — 测试点（含类型：functional/boundary/exception/state/permission/compatibility）
- `test_cases` — 测试用例（含前置条件、步骤、预期、优先级）
- `risks` — 风险项（含等级和原因）
- `clarifications` — 待确认问题
- `source_refs` — 引用的知识来源
