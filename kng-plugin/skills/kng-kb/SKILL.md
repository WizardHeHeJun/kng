---
name: kng-kb
description: "Manage KNG knowledge base entries: list, add, or import from Feishu/Lark documents"
argument-hint: "<list|add|import> [--type capability|project] [--project <id>] [--from-lark <url>]"
allowed-tools: [Read, Write, Glob, Grep, Bash, Skill]
---

# KNG Knowledge Base Manager

When invoked with: $ARGUMENTS

Manage the dual knowledge base (capability KB + project KB).

## Step 0: Resolve Project Context

Before parsing sub-commands, resolve the active project knowledge base.

### Project Context Protocol (shared across all KNG skills)

Resolve the data directory:
- `KNG_HOME` = `$KNG_HOME` (if env var set) || `$HOME/.kng-plugin`
- Read `${KNG_HOME}/kng.config.json` (if exists)
- `KB_ROOT` = config `kb_root` || `${KNG_HOME}/kb`
- `CAPABILITY_DIR` = `${KNG_HOME}/kb/capability`
- `DB_PATH` = config `db_path` (if set)

### Storage Mode Detection

Read `${KNG_HOME}/kng.config.json`. If `db_path` is set AND the file exists → **DB mode**. Otherwise → **file mode**.
In DB mode, list/add/import operations go through `db.py` and `kb_import.py` scripts instead of direct file manipulation. The flat KB files still exist as source-of-truth for version control; the DB is a derived index.

**If `--project <id>` was provided in any sub-command:**
- Use that project for THIS invocation only (do NOT update `active_project` in config).
- Verify `${KB_ROOT}/projects/<id>/` exists. If not, ask user whether to create it via `/kng-init <id>`.

**If `--project` was NOT provided**, resolve the active project:

1. **Read config**: Check if `${KNG_HOME}/kng.config.json` exists.
   - If it has `active_project` (or legacy `default_project`) AND `${KB_ROOT}/projects/${active_project}/` exists → use it. Display: `📂 当前项目知识库: {project_id}` and proceed.

2. **No config or no active project set** → auto-detect:
   a. Use Glob to list subdirectories in `${KB_ROOT}/projects/` that contain `.md` or `.yaml` files.
   b. **ZERO projects found**: Inform user "尚未创建任何项目知识库" and invoke `/kng-init` via Skill tool. After creation, the new project becomes active (kng-init handles this). Re-read config and proceed.
   c. **ONE project found**: Auto-select it. Write/update `${KNG_HOME}/kng.config.json` with `active_project` set to this project ID. Display: `📂 已自动选择项目知识库: {project_id}`
   d. **MULTIPLE projects found**: List all projects with brief info (module count, file count). Ask user to choose. Write/update `${KNG_HOME}/kng.config.json` with their choice. Display: `📂 已选择项目知识库: {project_id}`

3. After resolving, set `PROJECT_ID` to the resolved value and continue to sub-command parsing.

---

Parse the sub-command from `$ARGUMENTS`: `list`, `add`, or `import`.

---

## Sub-command: `list`

List all knowledge base files.

### Arguments
- `--project <id>` (optional): Only show files for this project. If omitted, show all projects.
- `--type capability|project` (optional): Filter by KB type.

### Steps

#### File mode:

1. **Capability KB**: Use Glob to find all files in `${KNG_HOME}/kb/capability/`. List each file with its size and first-line summary.

2. **Project KB**: Read `${KNG_HOME}/kng.config.json` to find `kb_root`. Use Glob to find all files under `${KB_ROOT}/projects/`. Group by project.

3. **Module index**: If `project-modules.yaml` exists for a project, read it and show the registered modules.

#### DB mode:

1. Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/db.py" stats --db "${DB_PATH}"` to get counts.
2. Query the DB programmatically or list entries via the script output. The DB stores KB entries with `kb_type` (capability/project), `module_id`, `entry_type`, and `source_file`.
3. Module index is read from the `modules` table in the DB.

#### Output (both modes):
   ```
   ## 基础能力库 (${KNG_HOME}/kb/capability/)
   - test-design-guidelines.md (23 lines) — 测试设计通用规范
   - api-test-script-playbook.md (23 lines) — 接口自动化脚本作业手册

   ## 项目知识库
   ### my-project (./kb/projects/my-project/)
   已注册模块: battle(战斗系统), reward(奖励系统), shop(商城系统)
   - project-overview.md (14 lines) — 项目概览
   - battle-skill-system.md (45 lines) — [battle] 技能系统设计
   - reward-daily-checkin.md (30 lines) — [reward] 签到奖励
   - bug-patterns.md (17 lines) — [general] 历史缺陷模式
   ```

---

## Sub-command: `add`

Interactively create a new knowledge base entry.

### Arguments
- `--type capability|project` (required): Which KB to add to.
- `--project <id>` (required if type=project): Target project.
- `--module <id>` (optional, project type only): Target module (e.g., `battle`, `reward`). If omitted, auto-detect from content.

### Steps

1. Ask the user what topic the KB entry covers.
2. Ask the user to describe the content (or provide reference material).
3. **Module detection** (project type only):
   a. Read `${KB_ROOT}/projects/<project-id>/project-modules.yaml`. If not found, skip module tagging.
   b. If `--module` was provided, use that directly.
   c. Otherwise, extract keywords from the user's topic + description, and match against each module's `tags` in `project-modules.yaml`. Pick the module with the highest tag overlap. If no module scores ≥ 2 keyword hits, use `fallback_module` (typically `general`).
   d. Confirm the detected module with the user: "检测到该内容属于 **{module.name}** 模块，是否正确？"
4. Generate a well-structured Markdown file based on the user's input.
5. Determine the file name: use module prefix for project entries (e.g., `battle-skill-system.md`, `reward-settlement.md`). For `general` module, no prefix needed.
6. Write the file:
   - capability → `${KNG_HOME}/kb/capability/<filename>.md`
   - project → `${KB_ROOT}/projects/<project-id>/<filename>.md`
7. **DB mode sync**: If in DB mode, after writing the file, re-import it into the database:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --capability-dir "${KNG_HOME}/kb/capability" \
     --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
     --project-id "${PROJECT_ID}" --force
   ```
   This keeps the DB index in sync with the flat files.
8. Confirm the file was created, show its path and detected module.

---

## Sub-command: `import`

Import a Feishu/Lark document as a KB entry. **When importing to project KB, automatically discovers which module the document belongs to and updates the module registry if needed.**

### Arguments
- `--from-lark <url>` (required): Feishu document URL.
- `--type capability|project` (required): Target KB.
- `--project <id>` (required if type=project): Target project.
- `--module <id>` (optional, project type only): Force assignment to a specific module. If omitted, auto-detect.

### Steps

1. **Fetch the document**:
   ```bash
   lark-cli docs +fetch --url "<url>" --as user
   ```

2. **Analyze document content**:
   - Extract a meaningful title from the first heading.
   - Identify the document's **主题域 (subject domain)**: what business system or module does this document describe?
   - Look at: section headings, key terminology, the overall topic.

3. **Module matching & discovery** (project type only):

   a. Read `${KB_ROOT}/projects/<project-id>/project-modules.yaml`.

   b. If `--module` was explicitly provided, use it. If that module id doesn't exist in the registry yet, add it (see step 3e).

   c. **Match against existing modules**: For each module in the registry, check if the document's content contains that module's `tags`. Use substring matching (Chinese text has no word boundaries). Pick the module with the highest tag hit count.

   d. **If a good match is found** (≥ 3 tag hits): use that module. Inform the user:
      ```
      检测到文档属于 [battle] 战斗系统 (命中 tags: 战斗, 技能, 伤害, buff)
      ```

   e. **If NO good match** (< 3 tag hits) — this means the document describes a module not yet in the registry. **Auto-discover the new module**:
      1. Analyze the document to determine what system/module it covers.
      2. Generate a new module entry:
         - `id`: English lowercase identifier derived from the system name (e.g., `guild`, `auction`, `pet`)
         - `name`: Chinese name as it appears in the document (e.g., `公会系统`)
         - `tags`: Extract 8-15 keywords from the document that characterize this module. Pick terms that would also appear in other documents about the same system (not just this one).
         - `description`: One-line summary
      3. Inform the user:
         ```
         未找到匹配模块，发现新模块: [guild] 公会系统
         tags: [公会, 帮会, 会长, 成员, 捐献, 公会战, 公会商店, 等级]
         ```
      4. **Append the new module to `project-modules.yaml`** using Edit tool. Add it to the `modules:` list.

4. **Generate file name**: `{module_id}-{title-slug}.md` (e.g., `battle-skill-system.md`, `guild-architecture.md`). For `general` module, no prefix.

5. **Detect cross-system references** (knowledge graph edges):

   While analyzing the document content, look for references to OTHER systems/modules:
   - Does the document mention calling, depending on, consuming from, or writing to another module?
   - Look for verbs/patterns: "调用XX系统", "依赖XX", "触发XX", "同步到XX", "从XX获取", "写入XX", "扣除XX的YY"
   - Check if the mentioned system matches any existing module in `project-modules.yaml`

   For each cross-system reference found:
   a. Determine the relation type: `depends_on`, `feeds_into`, `shares_state`, or `triggers`
   b. Assess `risk_level`: `high` if it involves currency/item/state mutation, `medium` for data reads, `low` for UI-level
   c. Extract 2-4 `test_focus` scenarios at this boundary
   d. Check if this relation already exists in `project-modules.yaml` `relations:` — if not, append it using Edit tool
   e. If it already exists, check if there are new `test_focus` items to add

   Example: A document about "任务系统" mentions "任务完成后通过奖励系统发放道具" → add relation:
   ```yaml
   - from: quest
     to: reward
     type: feeds_into
     description: 任务完成触发奖励发放
     risk_level: high
     test_focus: [任务完成条件判定后奖励准确发放, 异常中断后奖励补发]
   ```

6. **保留原始内容写入 KB 文件**:

   **禁止对文档内容进行蒸馏、精简或重组。** 必须完整保留 Feishu 文档的原始内容（包括表格、列表、备注、标注等），仅在文件顶部添加元数据头。原始内容中的格式标记（`<lark-table>`、`<image>`、`<text>` 等）也应原样保留。

   文件格式：
   ```markdown
   # {document_title}
   <!-- source: {feishu_url} -->
   <!-- module: {module_id} -->
   <!-- imported: {date} -->
   <!-- related_modules: {comma-separated list of modules this doc references} -->

   {原始文档内容，不做任何删减或改写}
   ```

   Write to: `${KB_ROOT}/projects/<project-id>/<filename>.md`

7. **DB mode sync**: If in DB mode, after writing the KB file and updating `project-modules.yaml`, re-import to keep the DB in sync:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --capability-dir "${KNG_HOME}/kb/capability" \
     --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
     --project-id "${PROJECT_ID}" --force
   ```

8. **文档审查反馈**:

   导入完成后，回顾文档原始内容，从能力知识库定义的专业视角给出反馈。**不修改已写入的文件内容**，仅以文字形式向用户报告发现的问题。重点关注以下方面：

   - **规则矛盾或歧义**：文档内不同章节对同一规则的描述是否存在冲突或模糊之处
   - **边界条件缺失**：关键数值、状态转换、异常流程是否缺少边界定义（如上限/下限、超时处理、并发场景）
   - **待确认事项**：文档中标记为"待定"、"待确认"、"TBD"等未决项，汇总列出
   - **跨系统接口风险**：与其他系统的交互点是否定义清晰，是否存在数据一致性风险
   - **可测试性问题**：是否有难以验证的描述（如"体验良好"、"合理范围"等模糊表述），或缺少可量化的验收标准

   输出格式：
   ```
   ## 📋 文档审查反馈

   ### ⚠️ 规则矛盾 / 歧义 (N 项)
   1. 第X章提到"..."，但第Y章描述为"..."，存在冲突

   ### 🔍 边界条件缺失 (N 项)
   1. XX功能未定义当 YY 为 0 / 负数 / 超上限时的处理逻辑

   ### 📌 待确认事项 (N 项)
   1. [第X章] "具体数值待定"

   ### ⚡ 跨系统接口风险 (N 项)
   1. 与XX系统的YY交互未定义失败回滚策略

   ### 🎯 可测试性问题 (N 项)
   1. "体验流畅"缺少量化标准
   ```

   如果某个类别没有发现问题，该类别可以省略。没有任何问题时输出"未发现明显问题"。

9. **Report**: Show:
   - Saved file path
   - Detected/discovered module (with tag list if new)
   - Content summary (document sections overview)
   - If a new module was registered: "新模块已添加到 project-modules.yaml"
   - If new relations were discovered:
     ```
     发现跨系统关联:
     quest ──feeds_into──▶ reward  [HIGH] 任务完成触发奖励发放
     quest ──depends_on──▶ config  [MED]  任务配置依赖配置系统
     ```

---

## Notes

- Capability KB files are stored in `${KNG_HOME}/kb/capability/` and persist across plugin updates.
- Always use UTF-8 encoding when writing files.
- KB files should follow Markdown format with clear headings for maximum retrieval effectiveness.
