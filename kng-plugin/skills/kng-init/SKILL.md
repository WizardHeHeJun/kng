---
name: kng-init
description: "Initialize a new project knowledge base with template files for KNG"
argument-hint: "<project-id> [--from-lark <overview-doc-url>]"
allowed-tools: [Read, Write, Edit, Glob, Bash]
---

# KNG Project Initialization

When invoked with: $ARGUMENTS

Initialize a new project knowledge base for KNG.

Supports two modes:
- **空项目模式**: `/kng-init my-project` — 生成空模板，模块注册表为空，后续通过 `/kng-kb import` 逐步填充
- **文档驱动模式**: `/kng-init my-project --from-lark <url>` — 从项目总览文档自动分析项目类型、核心系统，生成项目概览和模块注册表

## Step 0: Resolve KNG Home

Resolve the data directory:
- `KNG_HOME` = `$KNG_HOME` (if env var set) || `$HOME/.kng-plugin`
- Read `${KNG_HOME}/kng.config.json` (if exists)
- `KB_ROOT` = config `kb_root` || `${KNG_HOME}/kb`
- `CAPABILITY_DIR` = `${KNG_HOME}/kb/capability`
- `DB_PATH` = config `db_path` (if set)
- `OUTPUT_DIR` = config `output_dir` || `./test-output` (relative to CWD)

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- `project-id` (required): Short identifier like `my-project`, `project-x`
- `--from-lark <url>` (optional): Feishu/Lark document URL for the project overview or GDD

If no `project-id` is provided, ask the user for one.

## Step 2: Check Existing State

1. Check if `${KB_ROOT}/projects/${PROJECT_ID}/` already exists. If yes, inform the user and ask whether to overwrite or skip.
2. Check if `${KNG_HOME}/kng.config.json` exists.

## Step 3: Create Project KB Directory

Create the directory structure:
```
${KB_ROOT}/projects/${PROJECT_ID}/
```

## Step 4: Document-Driven Mode (if --from-lark provided)

### 4a. Fetch the overview document

```bash
lark-cli docs +fetch --url "<url>" --as user
```

### 4b. Analyze the document content

Read the fetched document carefully and extract:

1. **项目类型**: What kind of project is this? (e.g., Web应用, 移动App, 后端服务, 游戏, 数据平台)
2. **核心工作流**: What is the project's core workflow? (e.g., 用户注册→浏览→下单→支付→配送)
3. **业务模块/系统列表**: Identify ALL distinct systems or modules mentioned in the document. Look for:
   - Section headings that name systems (e.g., "## 用户系统", "## 支付模块")
   - Feature descriptions that imply distinct modules
   - Any table of contents or system architecture diagrams described in text
4. **系统间关联关系**: This is critical — identify HOW systems interact with each other. Look for:
   - Data flow: "订单完成后触发结算" → order feeds_into settlement
   - Dependencies: "权限校验依赖用户角色" → access depends_on user
   - Shared state: "库存和商城共享商品数据" → inventory shares_state shop
   - Triggers: "注册完成触发新手引导" → registration triggers onboarding
   - Explicit architecture diagrams or flow charts in the document
   - Any mention of "调用", "依赖", "触发", "关联", "同步", "读取", "写入" between systems
5. **高风险区域**: Any mentions of complexity, known issues, or tricky interactions between systems
6. **技术栈**: Any mentioned tech stack, frameworks, or constraints

### 4c. Generate project-overview.md from real content

Write `${KB_ROOT}/projects/${PROJECT_ID}/project-overview.md` with ACTUAL content extracted from the document — not placeholder templates. Example:

```markdown
# my-project 项目概览

## 项目类型
（从文档中提取，如：Web应用、移动App、游戏、后端服务等）

## 核心工作流
（从文档中提取核心业务流程）

## 主要系统
（从文档中提取各业务模块及其职责描述）

## 高风险区域
（从文档中提取复杂度高或历史易出问题的模块）

## 技术栈 & 约束
（从文档中提取技术栈和特殊约束）
```

### 4d. Generate project-modules.yaml from discovered modules

For EACH business module/system identified in step 4b, create a module entry with:
- `id`: lowercase English identifier (e.g., `user`, `payment`, `order`)
- `name`: Name as it appears in the document (e.g., `用户系统`)
- `tags`: Extract 8-15 keywords that would appear in design documents about this module. Include:
  - The module name itself and common abbreviations
  - Core concepts of this module (e.g., for battle: 技能, 伤害, buff, 血量, ...)
  - Related terms from the overview doc
- `description`: One-line summary of what this module covers

Write `${KB_ROOT}/projects/${PROJECT_ID}/project-modules.yaml`:

```yaml
# Project Module Registry & Knowledge Graph — 项目模块索引与知识图谱
# 从项目文档自动生成，可手动补充
# 新文档导入时 (/kng-kb import) 会自动匹配模块或新增模块/关联

auto_detect: true

modules:
  # ... modules discovered from the document
  # Example:
  # - id: user
  #   name: 用户系统
  #   tags: [用户, 注册, 登录, 认证, 角色, 权限, 账号]
  #   description: 用户注册、登录、角色权限管理

# 系统关联图谱 — 模块间的依赖、数据流、触发关系
# 关系类型:
#   depends_on  — A 的逻辑依赖 B 的数据或状态
#   feeds_into  — A 的输出是 B 的输入
#   shares_state — A 和 B 读写同一份数据
#   triggers    — A 的事件触发 B 的流程
relations:
  # ... relations discovered from the document
  # Example:
  # - from: order
  #   to: payment
  #   type: feeds_into
  #   description: 订单确认触发支付流程
  #   risk_level: high
  #   test_focus: [订单金额与支付金额一致, 支付超时处理, 重复支付防护]

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

### `${KB_ROOT}/projects/${PROJECT_ID}/project-overview.md`

```markdown
# ${PROJECT_ID} 项目概览

## 项目类型
<!-- 使用 /kng-init ${PROJECT_ID} --from-lark <总览文档URL> 自动填充 -->

## 核心工作流
<!-- 例如：注册 → 浏览 → 下单 → 支付 → 配送 -->

## 主要系统
<!-- 通过 /kng-kb import 导入项目文档后自动发现 -->

## 高风险区域
<!-- 历史上容易出问题的模块 -->

## 技术栈 & 约束
<!-- 客户端引擎、服务端框架、特殊限制等 -->
```

### `${KB_ROOT}/projects/${PROJECT_ID}/project-modules.yaml`

```yaml
# Project Module Registry & Knowledge Graph — 项目模块索引与知识图谱
# 模块和关联均为空 — 通过以下方式填充：
# 1. /kng-init ${PROJECT_ID} --from-lark <总览文档URL>  从文档批量发现模块+关联
# 2. /kng-kb import --from-lark <URL> --type project    逐步发现新模块+跨系统引用
# 3. /kng-evolve                                        跨系统 bug 反馈自动添加关联

auto_detect: true

modules: []

relations: []

fallback_module: general
```

## Step 6: Generate Common Template Files (both modes)

These files are always generated as templates, regardless of mode:

### `${KB_ROOT}/projects/${PROJECT_ID}/bug-patterns.md`

```markdown
# ${PROJECT_ID} 历史问题模式

<!-- 随着 /kng-evolve 反馈积累，此文件会自动按模块拆分为:
     {module}-bug-patterns.md -->

## 通用问题模式
<!-- 跨模块的常见问题 -->

## 关注重点
<!-- 基于历史问题，重点关注哪些方面 -->
```

### `${KB_ROOT}/projects/${PROJECT_ID}/test-constraints.md`

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

**Always** set the newly created project as the active project in `${KNG_HOME}/kng.config.json`.

If `${KNG_HOME}/kng.config.json` does not exist, create it:

```json
{
  "active_project": "${PROJECT_ID}",
  "kb_root": "${KNG_HOME}/kb",
  "output_dir": "./test-output",
  "db_path": "${KNG_HOME}/kng.db"
}
```

If it already exists, update the `active_project` field to `${PROJECT_ID}` using Edit tool. Preserve all other fields. If there is a legacy `default_project` field, update it as well to keep in sync. If `db_path` is not yet present, add it with value `"${KNG_HOME}/kng.db"`.

This ensures that subsequent `/kng-kb`, `/kng-evolve` invocations automatically use the newly created project without requiring `--project`.

## Step 7a: Auto-generate Capability Index

Automatically generate `skill-registry.yaml` and `synonym-aliases.yaml` from the capability skill files. This ensures the toolbox is properly indexed regardless of which skills the user has provided.

### 7a-1. Generate skill-registry.yaml

Run the registry generator to scan all `.md` files in the capability directory, identify callable skills (by `可调用技能` or `## 触发条件` markers), and extract metadata:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_registry.py" \
  "${KNG_HOME}/kb/capability" \
  --verbose
```

This produces `skill-registry.yaml` with a `skills:` section auto-populated from the skill files. If the file already existed and contained a `scenarios:` section, those scenarios are preserved.

### 7a-2. Generate synonym-aliases.yaml

Read the generated `skill-registry.yaml` and collect all `tags` across all skills. Then generate `synonym-aliases.yaml` by expanding each tag group into synonyms:

1. Read the `tags` from all skills in the generated registry
2. For each semantically distinct concept, create a synonym group with:
   - The original Chinese term
   - Common Chinese synonyms and abbreviations
   - English equivalent(s) if applicable
3. Merge groups that overlap semantically

Write the result to `${KNG_HOME}/kb/capability/synonym-aliases.yaml` in this format:

```yaml
# Synonym/Alias Groups for KB Retrieval
# 由 /kng-init 从 skill-registry.yaml 的 tags 自动生成
# Used by retrieve_kb.py to bridge vocabulary gaps in queries

groups:
  - name: group_name
    terms: [term1, term2, term3, english_term]
```

**Guidelines for synonym generation**:
- Each group should have 3-6 terms
- Include both formal and colloquial terms (e.g., 网络操作 ↔ 联网 ↔ network)
- Include English translations for technical terms
- Don't create groups for overly generic terms (e.g., "设计", "测试")
- Focus on domain-specific vocabulary that users might search with

If `synonym-aliases.yaml` already exists, regenerate it from the current tags (the file is always derivable from the skills).

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
     --capability-dir "${KNG_HOME}/kb/capability" \
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
  | user      | 用户系统   | 10      |
  | order     | 订单系统   | 8       |

  发现 {M} 条系统关联：
  order ──feeds_into──▶ payment    [HIGH] 订单确认触发支付
  user  ──depends_on──▶ auth       [HIGH] 用户操作依赖认证
  ```
- Next steps:
  - Document-driven: "模块和关联图谱已从文档自动提取。使用 `/kng-kb import` 导入更多项目文档时，系统会自动匹配模块、发现新模块和新的系统关联。"
  - Empty mode: "使用 `/kng-init ${PROJECT_ID} --from-lark <总览文档URL>` 从项目文档自动发现模块和系统关联图谱，或使用 `/kng-kb import` 逐步积累。"

## Step 9: 启动知识库查看器

初始化完成后，后台启动 Web 查看器，方便用户浏览数据库内容：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/db_viewer.py" --db "${DB_PATH}" --port 8787 &
```

向用户通知：「知识库查看器已启动：http://127.0.0.1:8787」
