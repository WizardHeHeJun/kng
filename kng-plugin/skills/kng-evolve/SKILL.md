---
name: kng-evolve
description: "Review test design output, capture feedback, and evolve knowledge base entries. Use after /kng-test to feed learnings back into capability or project KB."
argument-hint: "[--source <test-design.json|test-design.md>] [--type capability|project] [--project <id>]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# KNG Knowledge Evolution

When invoked with: $ARGUMENTS

This skill closes the learning loop: after `/kng-test` generates a test design, use `/kng-evolve` to review the output, capture what was good/bad/missing, and feed those learnings back into the knowledge base so future generations are better.

## Step 0: Resolve Project Context

Before gathering context, resolve the active project knowledge base.

Resolve the data directory:
- `KNG_HOME` = `$KNG_HOME` (if env var set) || `$HOME/.kng-plugin`
- Read `${KNG_HOME}/kng.config.json` (if exists)
- `KB_ROOT` = config `kb_root` || `${KNG_HOME}/kb`
- `CAPABILITY_DIR` = `${KNG_HOME}/kb/capability`
- `DB_PATH` = config `db_path` (if set)

### Storage Mode Detection

Read `${KNG_HOME}/kng.config.json`. If `db_path` is set AND the file exists → **DB mode**. Otherwise → **file mode**.
In DB mode, feedback is persisted to the `learning_feedback` table via `db.py`, and KB file updates are synced back to the DB via `kb_import.py`.

### Project Context Protocol (shared across all KNG skills)

**If `--project <id>` was provided:**
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

3. After resolving, set `PROJECT_ID` to the resolved value and continue.

---

## Trigger Scenarios

### Mode 1: Post-generation Review (most common)
```
/kng-evolve
```
Auto-detect the latest test design file in `test-output/`.

### Mode 2: Specific File Review
```
/kng-evolve --source test-output/20260424-my-project-test-design.json
```

### Mode 3: Learning from a Real Bug
```
/kng-evolve --type project --project my-project
```

---

## Step 1: Gather Context

### 1a. Locate test design source

If `--source` is provided, read that file. Otherwise, Glob for the most recent `*-test-design.json` in `./test-output/`. In Mode 3, skip to Step 2.

### 1b. Retrieve project memory

Read Claude Code's built-in project memory to find relevant past learnings:

1. Check if `.claude/projects/` directory exists in the workspace. Use Glob to find memory files (`*.md`) under the project memory path.
2. Also check if a `MEMORY.md` index file exists in `.claude/` — if so, read it and follow links to relevant memory files.
3. Grep memory files for keywords related to the current test design topic (e.g., testing, bug, feedback, lesson, pattern).

This surfaces past observations like "上次漏测了并发场景" or "结算接口需要幂等校验" that were captured across sessions. These are direct inputs to the evolution process — don't re-ask the user for things memory already knows.

**Note**: This uses Claude Code's native memory system (`.claude/` directory), not any third-party plugin. Every Claude Code user has this available.

### 1c. Load skill registry

**File mode**: Read `${KNG_HOME}/kb/capability/skill-registry.yaml` to understand:
- Which skills exist and what they cover (`skills[].covers`)
- Which scenario templates are defined (`scenarios[].test_focus`)
- Tags for routing feedback to the right file

**DB mode**: Query the `skills` and `skill_scenarios` tables from the DB. The data is equivalent — same fields, loaded from the same YAML during import.

### 1d. Load project module registry

**File mode**: Read `${KB_ROOT}/projects/<project-id>/project-modules.yaml` to understand the project's module taxonomy.

**DB mode**: Query the `modules` and `module_relations` tables for the active `PROJECT_ID`.

In both modes you need:
- Which business modules exist (`modules[].id`, `modules[].name`)
- Each module's keyword tags (`modules[].tags`)
- The fallback module for unclassified content

This enables routing project-specific feedback to the correct module-prefixed KB file (e.g., `battle-xxx.md`, `reward-xxx.md`) rather than dumping everything into generic `bug-patterns.md`.

## Step 2: Guided Review

Present the test design summary (if available) and ask the user focused questions. Start with the most impactful:

1. **遗漏场景**：有没有文档没覆盖但实际需要关注的场景？
2. **实际问题**：执行过程中发现了哪些预期之外的问题？
3. **方法改进**：方法论上有什么可以沉淀的经验？

If project memory already surfaced relevant learnings, present them first: "根据之前的记录，这些问题已被识别过：[...]. 是否有新的补充？"

Don't ask all questions at once. Ask one, respond to the answer, then decide if follow-ups are needed.

## Step 3: Route Feedback to Target Files

This is the key step. For each piece of feedback, use the **skill registry** to determine which file(s) to update.

### Routing logic:

1. **Extract keywords** from the feedback content.
2. **Match against `skill-registry.yaml`**:
   - Check `skills[].tags` and `skills[].covers` — if keywords overlap with a skill's coverage, that skill's `file` is a candidate target.
   - Check `scenarios[].extra_tags` and `scenarios[].test_focus` — if keywords match a scenario, ALL `required_skills` in that scenario are candidates.
3. **Classify by scope**:

| Feedback scope | Target | Routing rule |
|---------------|--------|-------------|
| Applicable to any project | capability KB → matched skill file(s) | Keywords match `skills[].tags` |
| Matches a scenario template | capability KB → ALL `required_skills` files in that scenario | Keywords match `scenarios[].extra_tags` |
| New scenario pattern | capability KB → `skill-registry.yaml` (add new scenario) | No existing scenario matches |
| New skill area entirely | capability KB → create new `.md` + register in `skill-registry.yaml` | No existing skill matches |
| Project-specific bug/knowledge | project KB → **module-prefixed file** | See module routing below |

### Module-aware project KB routing:

When feedback is project-specific, use `project-modules.yaml` to identify the target module:

1. Extract keywords from the feedback (use substring matching for Chinese — check if each module tag appears anywhere in the feedback text).
2. Match against `modules[].tags` in `project-modules.yaml` — pick the module with highest tag overlap (minimum 3 hits for confident match).
3. **If a good match is found** (e.g., module `battle`), route to the module-prefixed file:
   - Bug/defect pattern → `{module_id}-bug-patterns.md` (e.g., `battle-bug-patterns.md`)
   - System knowledge → `{module_id}-overview.md` (e.g., `battle-overview.md`)
   - Test constraints → `{module_id}-constraints.md` (e.g., `battle-constraints.md`)
4. If the target file does not exist yet, **create it** with a heading `# {module_name} — {category}` and append the feedback.
5. **If NO module matches** (< 3 tag hits) AND the feedback clearly describes a specific system:
   - This means the project has a module not yet registered. **Auto-discover it**:
     1. Determine what system the feedback is about from context
     2. Generate a new module entry (id, name, tags, description)
     3. Append to `project-modules.yaml` using Edit tool
     4. Inform the user: "发现新模块 [{id}] {name}，已添加到模块注册表"
   - Then route feedback to the newly created module's file
6. **If the feedback is truly cross-module or general**, fall back to generic files: `bug-patterns.md`, `project-overview.md`, or `test-constraints.md`.
7. Always inform the user which module was detected: "反馈已归类到 **{module_name}** 模块"

### Example routing:

User feedback: "支付结算需要关注断线重连后的重复扣款"

1. Keywords: `支付`, `结算`, `断线重连`, `重复扣款`
2. **Capability routing**: scenario tags match `[并发, 幂等, 重复, 断线重连]` → **hit**
3. Scenario requires matched skill files
4. Action: update matched capability skill files
5. **Module routing**: keywords `支付`, `结算` match module `payment` → **hit**
6. Action: append to `payment-bug-patterns.md` (create if not exists)

### Example: new module discovery via feedback

User feedback: "通知系统发送延迟，用户收不到消息"

1. Keywords: `通知`, `发送`, `延迟`, `消息`
2. **Module routing**: no existing module has `通知` in tags → **no match**
3. **Auto-discover**: feedback clearly describes a "通知系统"
4. Generate new module:
   ```yaml
   - id: notification
     name: 通知系统
     tags: [通知, 消息, 推送, 短信, 邮件, 站内信, 模板, 发送]
     description: 消息推送、站内通知、邮件短信发送
   ```
5. Append to `project-modules.yaml`
6. Create `notification-bug-patterns.md` and write the feedback

## Step 4: Detect Cross-System Relations (knowledge graph learning)

Before generating file updates, check if the feedback reveals **cross-system interactions**:

1. Does the feedback mention TWO OR MORE modules? (e.g., "战斗中使用背包道具" involves both `battle` and `inventory`)
2. Does the feedback describe a bug that spans system boundaries? (e.g., "任务完成但奖励没发" involves `quest` and `reward`)
3. Does the feedback reveal a dependency not in the current graph?

For each discovered cross-system relation:
a. Identify `from` and `to` modules
b. Determine relation `type`: `depends_on`, `feeds_into`, `shares_state`, or `triggers`
c. Set `risk_level` based on the bug severity: actual bugs → `high`, potential risks → `medium`
d. Extract `test_focus` from the feedback (what specifically should be tested at this boundary)
e. Check if this relation already exists in `project-modules.yaml` `relations:`
   - If exists: check if the bug warrants upgrading `risk_level` (e.g., `medium` → `high`), and add new `test_focus` items
   - If new: prepare a new relation entry to append

Example: User reports "订单完成后结算延迟，用户以为没生效又点了一次导致重复扣款"
- Modules involved: `order`, `payment`
- Relation: `order ──feeds_into──▶ payment`
- Risk: `high` (actual financial duplication issue)
- New test_focus: "结算延迟时的重复请求防护"

## Step 5: Generate Updates

For each target file identified in Step 3:

1. Read the current file content.
2. Identify the appropriate section to append to (match by heading).
3. Draft the new content following the existing file's style:
   - Bullet points, not paragraphs
   - Actionable rules, not descriptions
   - Include date annotation: `<!-- learned: 2026-04-24 -->`
4. If the feedback defines a new scenario pattern not in the registry, also draft an addition to `skill-registry.yaml` under `scenarios:`.
5. If Step 4 found cross-system relations, draft the additions/updates to `project-modules.yaml` `relations:` section.

## Step 6: Apply Updates

Show the user a summary of ALL proposed changes:

```
📋 即将更新:
1. kb/capability/test-design-guidelines.md
   + 异常路径 section: "断线重连后的重复操作校验"
2. kb/capability/api-test-script-playbook.md
   + 必须覆盖的异常 section: "断线重连场景的幂等校验"
3. kb/capability/skill-registry.yaml
   + scenarios: 新增 "断线重连测试" 场景模板
4. kb/projects/my-project/payment-bug-patterns.md  ← [payment] 模块
   + "断线重连后重复结算"
5. kb/projects/my-project/project-modules.yaml    ← 知识图谱更新
   + relations: quest ──feeds_into──▶ reward [HIGH] (新增/升级)
   + modules: 新增 pet 宠物系统 (仅当发现新模块时)
```

Ask for confirmation. Then apply using Edit tool — append to existing sections, never overwrite.

### DB mode: persist feedback & sync

After applying file edits, if in DB mode:

1. **Save feedback record** to the `learning_feedback` table via Bash:
   ```bash
   python -c "
   import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   from db import KngDatabase
   db = KngDatabase('${DB_PATH}'); db.connect(); db.initialize()
   db.save_feedback('${FEEDBACK_TYPE}', '''${CONTENT}''',
                    project_id='${PROJECT_ID}', module_id='${MODULE_ID}',
                    routed_to=${ROUTED_FILES_JSON})
   db.close()
   "
   ```
   Where `FEEDBACK_TYPE` is one of: `missed_scenario`, `actual_bug`, `method_improvement`, `new_scenario`, `new_module`, `relation_update`.

2. **Re-import** updated KB files and module registry to keep DB in sync:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --capability-dir "${KNG_HOME}/kb/capability" \
     --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
     --project-id "${PROJECT_ID}" --force
   ```

## Step 7: Summary

Report:
- Files updated and what was added
- Which skills will benefit (via registry routing)
- If graph was updated: show the new/modified relations
- "这些改进会在下次 `/kng-test` 时自动生效。知识图谱的关联关系会让测试设计自动覆盖跨系统集成场景。"

---

## Learning Principles

1. **提炼而非照搬**：具体 bug → 可复用的测试模式
2. **可操作**：每条知识能直接指导测试用例设计
3. **多文件联动**：一个场景往往需要更新多个 skill 文件，通过 registry 路由确保不遗漏
4. **累积叠加**：追加到已有 section，保持知识连贯
5. **标注时间**：用 HTML 注释标注学习时间，便于追溯
6. **记忆去重**：如果 Claude Code 原生 memory（`.claude/` 目录）已有相同观察，不重复写入 KB，但验证 KB 是否已覆盖
