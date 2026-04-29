---
name: kng-test
description: "Generate structured test design from a Feishu/Lark document URL using dual knowledge bases (capability + project)"
argument-hint: "<feishu-url> [--project <project-id>]"
allowed-tools: [Read, Write, Glob, Grep, Bash, Skill]
---

# KNG Test Design Generator

When invoked with: $ARGUMENTS

You will generate a structured test design from a Feishu document, augmented by dual knowledge bases. Follow these steps precisely.

## Step 0: Resolve Project Context & Parse Arguments

Extract from `$ARGUMENTS`:
- `url` (required): The Feishu/Lark document URL
- `--project <id>` (optional): Project identifier for ONE-TIME override (does not change active project)

Set defaults:
- `KB_ROOT` = `./kb` (or from `kng.config.json` → `kb_root`)
- `OUTPUT_DIR` = `./test-output` (or from `kng.config.json` → `output_dir`)
- `DB_PATH` = from `kng.config.json` → `db_path` (optional — if present, enables **DB mode**)

### Storage Mode Detection

Read `kng.config.json`. If `db_path` is set AND the file exists → **DB mode**. Otherwise → **file mode**.
All subsequent KB operations branch on this. DB mode uses `retrieve_kb.py --db` and `db.py`; file mode uses flat files as before.

### Project Context Protocol (shared across all KNG skills)

This protocol ensures a project knowledge base is always active. Follow it exactly:

**If `--project <id>` was provided:**
- Use that project for THIS invocation only (do NOT update `active_project` in config).
- Verify `${KB_ROOT}/projects/<id>/` exists. If not, ask user whether to create it via `/kng-init <id>`.

**If `--project` was NOT provided**, resolve the active project:

1. **Read config**: Check if `kng.config.json` exists in the workspace root.
   - If it has `active_project` (or legacy `default_project`) AND `${KB_ROOT}/projects/${active_project}/` exists → use it. Display: `📂 当前项目知识库: {project_id}` and proceed.

2. **No config or no active project set** → auto-detect:
   a. Use Glob to list subdirectories in `${KB_ROOT}/projects/` that contain `.md` or `.yaml` files.
   b. **ZERO projects found**: Inform user "尚未创建任何项目知识库" and invoke `/kng-init` via Skill tool. After creation, the new project becomes active (kng-init handles this). Re-read config and proceed.
   c. **ONE project found**: Auto-select it. Write/update `kng.config.json` with `active_project` set to this project ID. Display: `📂 已自动选择项目知识库: {project_id}`
   d. **MULTIPLE projects found**: List all projects with brief info (module count, file count). Ask user to choose. Write/update `kng.config.json` with their choice. Display: `📂 已选择项目知识库: {project_id}`

3. After resolving, set `PROJECT_ID` to the resolved value and continue.

## Step 1: Fetch Document

Run via Bash:
```bash
lark-cli docs +fetch --url "<url>" --as user
```

Capture the stdout as the document content. If the command fails:
- Check if `lark-cli` is installed: `which lark-cli`
- If not installed, tell the user to install lark-cli first
- If auth fails, suggest running `lark-cli auth login`

## Step 2: Retrieve Knowledge Base Context

### File mode (no `db_path` in config):

Run the KB retrieval script:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve_kb.py" \
  --query-file /dev/stdin \
  --capability-dir "${CLAUDE_PLUGIN_ROOT}/kb/capability" \
  --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
  --top-k 5 \
  <<< "DOCUMENT_CONTENT_HERE"
```

### DB mode (`db_path` set in config):

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve_kb.py" \
  --query-file /dev/stdin \
  --db "${DB_PATH}" \
  --project "${PROJECT_ID}" \
  --mode keyword \
  --top-k 5 \
  <<< "DOCUMENT_CONTENT_HERE"
```

Both modes output the same JSON format with:
- `capability_hits`, `project_hits` — matched KB entries
- `detected_module` (with `id`, `name`, `score`) — which business module this document belongs to
- `related_modules` — modules connected to the detected module via the knowledge graph, each with `relation_type`, `description`, `risk_level`, and `test_focus`
- `stats` — includes `storage_mode: "file"` or `storage_mode: "sqlite"` to confirm which mode was used

Parse all fields. The `detected_module` goes into output metadata. The `related_modules` are critical — they tell you which cross-system boundaries need integration testing.

If the script is unavailable or fails, fall back to manual retrieval:
1. Use Glob to find all `.md` files in `${CLAUDE_PLUGIN_ROOT}/kb/capability/` and `${KB_ROOT}/projects/${PROJECT_ID}/`
2. Use Read to read each file

## Step 3: Read Hit Files

For each hit returned by the retrieval script, use the Read tool to load the full file content (up to 4000 characters per file). This gives you complete context beyond the snippets.

## Step 4: Generate Test Design

Using the test-design-methodology skill (which should be auto-loaded in your context), generate a JSON object that:
- Analyzes the document content thoroughly
- Applies the capability KB methodology (test point design rules, priority definitions, script specs)
- Incorporates project-specific knowledge (game mechanics, known bug patterns, constraints)
- Follows the exact JSON schema defined in the methodology skill
- Includes `source_refs` citing which KB files informed each aspect of the design

**Important**: Generate at least 4 test points and 4 test cases. Cover functional, boundary, exception, and state paths.

**Integration test points from knowledge graph**: If `related_modules` is non-empty, generate additional test points of type `integration` for each related module with `risk_level` = `high` or `medium`. Use the relation's `test_focus` as guidance. For example, if the document is about 战斗系统 and the graph shows `battle ──depends_on──▶ equipment [HIGH]`, generate test points like:
- `TP-INT-001` [integration] 装备属性变更后战斗伤害实时刷新
- `TP-INT-002` [integration] 装备卸下状态下的战斗数值回退

These integration test points must be clearly labeled with `type: "integration"` and note which two systems are involved in `source_refs`.

## Step 5: Validate Output

Read the schema file at `${CLAUDE_PLUGIN_ROOT}/schemas/test_design.schema.json` and verify your generated JSON conforms to it:
- All required fields present: `feature_name`, `test_points`, `test_cases`, `risks`, `clarifications`
- Each test_point has `id`, `title`, `type`
- Each test_case has `id`, `title`, `preconditions`, `steps`, `expected`, `priority`
- Each risk has `level`, `item`, `reason`

Fix any schema violations before proceeding.

## Step 6: Save Outputs

Generate a timestamp in format `YYYYMMDD-HHMMSS` (use Bash: `date +%Y%m%d-%H%M%S`).
Set `PREFIX = "${TIMESTAMP}-${PROJECT_ID}"`.

Create the output directory if needed (use Bash: `mkdir -p "${OUTPUT_DIR}"`).

Write three files to `${OUTPUT_DIR}/` **directly using the Write tool** (do NOT use Python scripts or Bash to write these files):

### 1. `${PREFIX}-source.md`
The raw document content fetched from Feishu. Write it directly with the Write tool.

### 2. `${PREFIX}-test-design.json`
The generated test design JSON, pretty-printed with 2-space indentation. Write it directly with the Write tool.

### 3. `${PREFIX}-test-design.md`
A readable Markdown summary:

```markdown
# 测试设计：{feature_name}

- 项目：{project_id}
- 所属模块：{detected_module.name} ({detected_module.id})
- 来源文档：{url}
- 生成时间：{ISO timestamp}

## 命中知识（基础能力库）
- {path} (score={score})

## 命中知识（项目库）
- {path} (score={score})

## 关联系统（知识图谱）
<!-- Only if related_modules is non-empty -->
- battle ──depends_on──▶ equipment [HIGH] 战斗伤害依赖装备属性
  - 测试重点: 属性加成实时生效, 装备更换后数值刷新

## 测试点
- `TP-001` [functional] 测试点标题
- `TP-INT-001` [integration] 跨系统集成测试点（来自知识图谱）

## 测试用例
- `TC-001` 用例标题 (P0)
  - 前置：前置条件
  - 步骤：操作步骤
  - 预期：预期结果

## 风险
- [high] 风险项：风险原因

## 待确认
- 待确认问题

## 引用来源
- [capability] path - note
- [graph] battle→equipment: 战斗伤害依赖装备属性
```

## Step 7: Report

Print a summary:
- Generation mode and project ID
- Number of test points and test cases generated
- KB files that were referenced
- Output file paths

Do NOT print the full JSON content — just the summary and file paths.
