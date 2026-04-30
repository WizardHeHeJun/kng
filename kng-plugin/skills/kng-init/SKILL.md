---
name: kng-init
description: "Initialize a new project knowledge base with template files for KNG test design"
argument-hint: "<project-id> [--from-lark <overview-doc-url>]"
allowed-tools: [Read, Write, Glob, Bash, Skill]
---

# KNG Project Initialization

When invoked with: $ARGUMENTS

Initialize a new project knowledge base so that `/kng-test` can generate project-aware test designs.

Supports two modes:
- **空项目模式**: `/kng-init my-game` — 生成空模板，模块注册表为空，后续通过 `/kng-kb import` 逐步填充
- **文档驱动模式**: `/kng-init my-game --from-lark <url>` — 从策划案总览文档自动分析游戏类型、核心系统，生成项目概览和模块注册表

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- `project-id` (required): Short identifier like `demo-game`, `project-x`
- `--from-lark <url>` (optional): Feishu/Lark document URL for the project overview or GDD

If no `project-id` is provided, ask the user for one.

## Step 2: Check Existing State

1. Check if `./kb/projects/${PROJECT_ID}/` already exists. If yes, inform the user and ask whether to overwrite or skip.
2. Check if `kng.config.json` exists in the workspace root.

## Step 3: Create Project KB Directory

Create the directory structure:
```
./kb/projects/${PROJECT_ID}/
```

## Step 4: Document-Driven Mode (if --from-lark provided)

### 4a. Fetch the overview document

```bash
lark-cli docs +fetch --url "<url>" --as user
```

### 4b. Analyze the document content

Read the fetched document carefully and extract:

1. **游戏类型**: What kind of game is this? (e.g., MMORPG, 卡牌, SLG, 休闲, FPS, MOBA)
2. **核心循环**: What is the game's core loop? (e.g., 任务→战斗→奖励→成长)
3. **业务模块/系统列表**: Identify ALL distinct game systems or modules mentioned in the document. Look for:
   - Section headings that name systems (e.g., "## 战斗系统", "## 商城")
   - Feature descriptions that imply distinct modules
   - Any table of contents or system architecture diagrams described in text
4. **系统间关联关系**: This is critical — identify HOW systems interact with each other. Look for:
   - Data flow: "任务完成后发放奖励" → quest feeds_into reward
   - Dependencies: "伤害计算基于装备属性" → battle depends_on equipment
   - Shared state: "背包和商城共享道具库存" → inventory shares_state shop
   - Triggers: "角色升级解锁新技能" → leveling triggers battle
   - Explicit architecture diagrams or flow charts in the document
   - Any mention of "调用", "依赖", "触发", "关联", "同步", "读取", "写入" between systems
5. **高风险区域**: Any mentions of complexity, known issues, or tricky interactions between systems
6. **技术栈**: Any mentioned tech stack, frameworks, or constraints

### 4c. Generate project-overview.md from real content

Write `./kb/projects/${PROJECT_ID}/project-overview.md` with ACTUAL content extracted from the document — not placeholder templates. Example:

```markdown
# my-game 项目概览

## 游戏类型
开放世界 MMORPG

## 核心循环
探索 → 战斗 → 掉落 → 装备强化 → 挑战更高难度

## 主要系统
- 战斗系统：实时动作战斗，技能组合连招机制
- 装备系统：装备掉落、强化、附魔、套装效果
- 任务系统：主线剧情、支线任务、日常委托
- 社交系统：公会、组队副本、交易行
- 商城系统：外观道具、月卡、战令

## 高风险区域
- 战斗伤害计算：多 buff 叠加时的精度问题
- 交易行：并发挂单/购买的一致性

## 技术栈 & 约束
- 客户端：Unity
- 服务端：Go 微服务
```

### 4d. Generate project-modules.yaml from discovered modules

For EACH business module/system identified in step 4b, create a module entry with:
- `id`: lowercase English identifier (e.g., `battle`, `equipment`, `quest`)
- `name`: Chinese name as it appears in the document (e.g., `战斗系统`)
- `tags`: Extract 8-15 keywords that would appear in design documents about this module. Include:
  - The module name itself and common abbreviations
  - Core concepts of this module (e.g., for battle: 技能, 伤害, buff, 血量, ...)
  - Related terms from the overview doc
- `description`: One-line summary of what this module covers

Write `./kb/projects/${PROJECT_ID}/project-modules.yaml`:

```yaml
# Project Module Registry & Knowledge Graph — 项目模块索引与知识图谱
# 从策划案文档自动生成，可手动补充
# 新文档导入时 (/kng-kb import) 会自动匹配模块或新增模块/关联

auto_detect: true

modules:
  - id: battle
    name: 战斗系统
    tags: [战斗, 技能, 伤害, buff, debuff, 血量, 攻击, 防御, PVP, PVE, 连招, 闪避]
    description: 实时动作战斗，技能组合连招机制

  - id: equipment
    name: 装备系统
    tags: [装备, 强化, 附魔, 套装, 掉落, 品质, 词条, 分解]
    description: 装备掉落、强化、附魔、套装效果

  # ... more modules discovered from the document

# 系统关联图谱 — 模块间的依赖、数据流、触发关系
# 关系类型:
#   depends_on  — A 的逻辑依赖 B 的数据或状态
#   feeds_into  — A 的输出是 B 的输入
#   shares_state — A 和 B 读写同一份数据
#   triggers    — A 的事件触发 B 的流程
relations:
  - from: battle
    to: equipment
    type: depends_on
    description: 战斗伤害计算依赖装备属性加成
    risk_level: high
    test_focus: [属性加成实时生效, 装备更换后数值刷新, 套装效果叠加]

  - from: quest
    to: reward
    type: feeds_into
    description: 任务完成触发奖励发放
    risk_level: high
    test_focus: [完成条件准确判定, 奖励正确发放, 重复领取防护]

  # ... more relations discovered from the document

fallback_module: general
```

**Important for modules**: The tags must come from the actual document content — use the document's own terminology, don't guess.

**Important for relations**: 
- Extract EVERY cross-system interaction mentioned in the document. Common patterns:
  - Core loop itself defines a chain of relations (e.g., 战斗→掉落→装备→强化→战斗)
  - "高风险区域" often describes risky cross-system boundaries
  - Look for verbs like "调用/依赖/触发/同步/读取/写入/发放/消耗/扣除" — these indicate edges
- Set `risk_level` based on:
  - `high`: involves currency/items/state mutation across systems, or mentioned as problematic
  - `medium`: data flows across systems but is read-only or low-frequency
  - `low`: loose coupling, mostly UI-level interaction
- `test_focus` should list 2-4 specific test scenarios at this system boundary

## Step 5: Empty Mode (if --from-lark NOT provided)

Generate template files with placeholder content.

### `./kb/projects/${PROJECT_ID}/project-overview.md`

```markdown
# ${PROJECT_ID} 项目概览

## 游戏类型
<!-- 使用 /kng-init ${PROJECT_ID} --from-lark <总览文档URL> 自动填充 -->

## 核心循环
<!-- 例如：任务 → 战斗 → 奖励 → 成长 -->

## 主要系统
<!-- 通过 /kng-kb import 导入策划案后自动发现 -->

## 高风险区域
<!-- 历史上容易出问题的模块 -->

## 技术栈 & 约束
<!-- 客户端引擎、服务端框架、特殊限制等 -->
```

### `./kb/projects/${PROJECT_ID}/project-modules.yaml`

```yaml
# Project Module Registry & Knowledge Graph — 项目模块索引与知识图谱
# 模块和关联均为空 — 通过以下方式填充：
# 1. /kng-init ${PROJECT_ID} --from-lark <总览文档URL>  批量发现模块+关联
# 2. /kng-kb import --from-lark <URL> --type project    逐步发现新模块+跨系统引用
# 3. /kng-evolve                                        跨系统 bug 反馈自动添加关联

auto_detect: true

modules: []

relations: []

fallback_module: general
```

## Step 6: Generate Common Template Files (both modes)

These files are always generated as templates, regardless of mode:

### `./kb/projects/${PROJECT_ID}/bug-patterns.md`

```markdown
# ${PROJECT_ID} 历史缺陷模式

<!-- 随着 /kng-evolve 反馈积累，此文件会自动按模块拆分为:
     {module}-bug-patterns.md (如 battle-bug-patterns.md) -->

## 通用缺陷模式
<!-- 跨模块的常见问题 -->

## 测试关注点
<!-- 基于历史缺陷，测试重点关注哪些方面 -->
```

### `./kb/projects/${PROJECT_ID}/test-constraints.md`

```markdown
# ${PROJECT_ID} 测试约束与规范

## 环境要求
<!-- 测试环境配置、账号要求、特殊工具 -->

## 数据准备
<!-- 测试数据生成方式、重置策略 -->

## 回归策略
<!-- 每次发版必须回归的核心场景 -->

## 验收标准
<!-- 项目特有的质量门禁 -->
```

## Step 7: Create or Update Config & Activate Project

**Always** set the newly created project as the active project in `kng.config.json`.

If `kng.config.json` does not exist, create it:

```json
{
  "active_project": "${PROJECT_ID}",
  "kb_root": "./kb",
  "output_dir": "./test-output",
  "db_path": "./kng.db"
}
```

If it already exists, update the `active_project` field to `${PROJECT_ID}` using Edit tool. Preserve all other fields. If there is a legacy `default_project` field, update it as well to keep in sync. If `db_path` is not yet present, add it with value `"./kng.db"`.

This ensures that subsequent `/kng-test`, `/kng-kb`, `/kng-evolve` invocations automatically use the newly created project without requiring `--project`.

## Step 7b: Initialize & Populate Database

Initialize the SQLite database and import all flat KB files into it. This enables faster retrieval and structured queries for large projects.

1. **Initialize the database**:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/db.py" init --db "${DB_PATH}"
   ```

2. **Import capability KB** (universal test methodology):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --capability-dir "${CLAUDE_PLUGIN_ROOT}/kb/capability" \
     --verbose
   ```

3. **Import project KB** (newly created project files):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
     --project-id "${PROJECT_ID}" \
     --verbose
   ```

4. **Verify** with stats:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/db.py" stats --db "${DB_PATH}"
   ```

If any step fails, warn the user but do NOT block the init — the flat files are always the source of truth and file mode will still work.

## Step 8: Report

Print a summary:
- Created directory path
- List of files generated
- Database status: initialized at `${DB_PATH}`, number of imported entries
- **If document-driven mode**: show discovered modules and relations:
  ```
  发现 {N} 个业务模块：
  | 模块 ID    | 名称      | 关键词数 |
  |-----------|----------|---------|
  | battle    | 战斗系统   | 12      |
  | equipment | 装备系统   | 8       |

  发现 {M} 条系统关联：
  battle ──depends_on──▶ equipment  [HIGH] 伤害计算依赖装备属性
  quest  ──feeds_into──▶ reward     [HIGH] 任务完成触发奖励发放
  shop   ──shares_state─▶ inventory [MED]  共享道具库存数据
  ```
- Next steps:
  - Document-driven: "模块和关联图谱已从文档自动提取。使用 `/kng-kb import` 导入更多策划案时，系统会自动匹配模块、发现新模块和新的系统关联。"
  - Empty mode: "使用 `/kng-init ${PROJECT_ID} --from-lark <总览文档URL>` 从策划案自动发现模块和系统关联图谱，或使用 `/kng-kb import` 逐步积累。"

## Step 9: 启动知识库查看器

初始化完成后，后台启动 Web 查看器，方便用户浏览数据库内容：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/db_viewer.py" --db "${DB_PATH}" --port 8787 &
```

向用户通知：「知识库查看器已启动：http://127.0.0.1:8787」
