---
name: kng-test
description: "Generate structured design output from a Feishu/Lark document URL using dual knowledge bases (capability + project)"
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

Resolve the data directory:
- `KNG_HOME` = `$KNG_HOME` (if env var set) || `$HOME/.kng-plugin`
- Read `${KNG_HOME}/kng.config.json` (if exists)
- `KB_ROOT` = config `kb_root` || `${KNG_HOME}/kb`
- `CAPABILITY_DIR` = `${KNG_HOME}/kb/capability`
- `DB_PATH` = config `db_path` (if set)
- `OUTPUT_DIR` = config `output_dir` || `./test-output` (relative to CWD)

### Storage Mode Detection

Read `${KNG_HOME}/kng.config.json`. If `db_path` is set AND the file exists → **DB mode**. Otherwise → **file mode**.
All subsequent KB operations branch on this. DB mode uses `retrieve_kb.py --db` and `db.py`; file mode uses flat files as before.

### Project Context Protocol (shared across all KNG skills)

This protocol ensures a project knowledge base is always active. Follow it exactly:

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

## Step 1: Fetch Document

Run via Bash:
```bash
lark-cli docs +fetch --url "<url>" --as user
```

Capture the stdout as the document content. If the command fails:
- Check if `lark-cli` is installed: `which lark-cli`
- If not installed, tell the user to install lark-cli first
- If auth fails, suggest running `lark-cli auth login`

## Step 2: Retrieve Project Knowledge Base Context

### File mode (no `db_path` in config):

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve_kb.py" \
  --query-file /dev/stdin \
  --capability-dir "${KNG_HOME}/kb/capability" \
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

Parse the output JSON. Focus on:
- `project_hits` — matched project KB entries (business logic, constraints, known issues)
- `detected_module` — which business module this document belongs to
- `related_modules` — cross-system boundaries for integration testing
- `matched_scenarios` — which scenario templates matched (indicates relevant skill combinations)

For each project hit, use the Read tool to load the full file content (up to 4000 characters).

If the script is unavailable or fails, fall back to manual retrieval:
1. Use Glob to find all `.md` files in `${KB_ROOT}/projects/${PROJECT_ID}/`
2. Use Read to read each file

## Step 3: Select Capability Skills (技能工具箱选择)

The capability knowledge base contains **callable skills** — each one is a focused testing ability with trigger conditions, procedures, and output specs. You must select and invoke relevant skills rather than generating test designs from scratch.

### 3a. Load the Skill Toolbox

Read the skill registry:
```bash
cat "${KNG_HOME}/kb/capability/skill-registry.yaml"
```

Or in DB mode, query skills:
```sql
SELECT id, name, file, when_to_use, input_spec, output_spec FROM skills
```

The registry lists all available skills with:
- `when_to_use` — trigger conditions (when this skill is relevant)
- `input` — what the skill needs from the document
- `output` — what test artifacts it produces

### 3b. Match Skills to Document

Analyze the document content and select applicable skills by matching against each skill's `when_to_use` conditions:

| Skill | Select when document contains... |
|-------|----------------------------------|
| **功能路径覆盖** | User flows, feature entries, process descriptions, conditional branches |
| **边界值设计** | Numeric ranges, quantity limits, string lengths, time ranges |
| **异常与容错设计** | Network operations, server interactions, external dependencies |
| **状态流转验证** | State changes, conditional triggers, concurrent operations |
| **权限与安全测试** | Role distinctions, resource ownership, access controls |
| **接口自动化设计** | API interactions, server-side logic, data persistence |
| **优先级与风险评估** | Always selected (runs after other skills to calibrate priorities) |

**Selection rule**: A skill is selected if the document content matches ANY of its trigger conditions. Most documents will match 3-5 skills. Select at least 2 skills for any document.

Display the selected skills: `🔧 选择技能: {skill_names}`

## Step 4: Invoke Selected Skills (技能调用)

For each selected skill, read its full procedure file and apply it to the document:

### 4a. Read Skill Procedure

For each selected skill, read its capability KB file:
```
${KNG_HOME}/kb/capability/{skill.file}
```

Each skill file contains:
- **触发条件**: Confirms this skill is relevant
- **输入**: What to extract from the document
- **执行步骤**: Step-by-step procedure to follow
- **输出规范**: The test points format and ID prefix to use
- **质量检查**: Checklist to verify output quality

### 4b. Execute Each Skill

Follow the skill's `执行步骤` (procedure) using the document content as input:
1. Extract the relevant parts of the document as specified by the skill's `输入`
2. Execute each step in the skill's procedure
3. Generate test points following the skill's `输出规范` (using the specified ID prefix: TP-FP-, TP-BV-, TP-EX-, TP-ST-, TP-PM-, TP-API-)
4. Verify the output against the skill's `质量检查` checklist

### 4c. Generate Integration Test Points

If `related_modules` from Step 2 is non-empty, generate additional integration test points for each related module with `risk_level` = `high` or `medium`. Use the relation's `test_focus` as guidance:
- `TP-INT-001` [integration] — clearly labeled with `type: "integration"`
- Note which two systems are involved in `source_refs`

### 4d. Run Priority & Risk Assessment

The **优先级与风险评估** skill always runs last. It:
- Calibrates priorities across all generated test points (P0 ≤ 30%)
- Identifies high-risk scenarios
- Extracts clarification items from the document
- Generates the `risks` and `clarifications` arrays

## Step 4e: Compose Final Output

Merge all skill outputs into a single test design JSON following the schema defined in the test-design-methodology skill:
- Combine test points from all invoked skills (each with its skill-specific ID prefix)
- Include `source_refs` citing which capability skills and project KB files informed the design
- Add a `invoked_skills` field listing which skills were selected and invoked

**Important**: Generate at least 4 test points and 4 test cases total. The combination of multiple skills should naturally exceed this minimum.

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

## 调用技能
- 功能路径覆盖 → 产出 TP-FP-001 ~ TP-FP-003
- 边界值设计 → 产出 TP-BV-001 ~ TP-BV-002
- ...

## 命中知识（项目库）
- {path} (score={score})

## 关联系统（知识图谱）
<!-- Only if related_modules is non-empty -->
- battle ──depends_on──▶ equipment [HIGH] 战斗伤害依赖装备属性
  - 测试重点: 属性加成实时生效, 装备更换后数值刷新

## 测试点
- `TP-FP-001` [functional] 功能路径测试点（来自：功能路径覆盖）
- `TP-BV-001` [boundary] 边界值测试点（来自：边界值设计）
- `TP-EX-001` [exception] 异常测试点（来自：异常与容错设计）
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
- [skill] functional-path-coverage - 功能路径覆盖
- [skill] boundary-value-design - 边界值设计
- [project] path - note
- [graph] battle→equipment: 战斗伤害依赖装备属性
```

## Step 7: Report

Print a summary:
- Generation mode and project ID
- Number of test points and test cases generated
- KB files that were referenced
- Output file paths

Do NOT print the full JSON content — just the summary and file paths.
