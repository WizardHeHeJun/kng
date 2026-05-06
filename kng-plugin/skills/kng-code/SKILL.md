---
name: kng-code
description: "Import local files (source code, docs) into KNG knowledge base and link code with design documents"
argument-hint: "<import|link> [--path <path>] [--doc <kb_file>] [--code <path>] [--type capability|project] [--project <id>] [--module <id>]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Skill]
---

# KNG Code Importer

When invoked with: $ARGUMENTS

Import local files (source code, documents) into the KNG knowledge base, and establish metadata cross-links between design documents and their implementing code.

## Step 0: Resolve Project Context

### Project Context Protocol (shared across all KNG skills)

Resolve the data directory:
- `KNG_HOME` = `$KNG_HOME` (if env var set) || `$HOME/.kng-plugin`
- Read `${KNG_HOME}/kng.config.json` (if exists)
- `KB_ROOT` = config `kb_root` || `${KNG_HOME}/kb`
- `CAPABILITY_DIR` = `${KNG_HOME}/kb/capability`
- `DB_PATH` = config `db_path` (if set)

### Storage Mode Detection

Read `${KNG_HOME}/kng.config.json`. If `db_path` is set AND the file exists → **DB mode**. Otherwise → **file mode**.

**If `--project <id>` was provided in any sub-command:**
- Use that project for THIS invocation only (do NOT update `active_project` in config).
- Verify `${KB_ROOT}/projects/<id>/` exists. If not, ask user whether to create it via `/kng-init <id>`.

**If `--project` was NOT provided**, resolve the active project:

1. **Read config**: Check if `${KNG_HOME}/kng.config.json` exists.
   - If it has `active_project` (or legacy `default_project`) AND `${KB_ROOT}/projects/${active_project}/` exists → use it. Display: `📂 当前项目知识库: {project_id}` and proceed.

2. **No config or no active project set** → auto-detect:
   a. Use Glob to list subdirectories in `${KB_ROOT}/projects/` that contain `.md` or `.yaml` files.
   b. **ZERO projects found**: Inform user and invoke `/kng-init` via Skill tool. After creation, re-read config and proceed.
   c. **ONE project found**: Auto-select it. Write/update config with `active_project`. Display: `📂 已自动选择项目知识库: {project_id}`
   d. **MULTIPLE projects found**: List all projects. Ask user to choose. Write/update config. Display: `📂 已选择项目知识库: {project_id}`

3. After resolving, set `PROJECT_ID` to the resolved value and continue to sub-command parsing.

---

Parse the sub-command from `$ARGUMENTS`: `import` or `link`.

---

## Sub-command: `import`

Import local files (source code or documents) into the knowledge base.

### Arguments
- `--path <path>` (required): Local file path or glob pattern (e.g., `src/battle/skill.ts`, `src/battle/**/*.ts`).
- `--type capability|project` (required): Target KB.
- `--project <id>` (required if type=project): Target project.
- `--module <id>` (optional, project type only): Force assignment to a specific module. If omitted, auto-detect.

### Steps

1. **Expand and list files**:

   Use Glob to expand the `--path` pattern. List all matched files. If no files match, report error and stop.

   Classify each file by extension:
   - **Code files**: `.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.go`, `.java`, `.cs`, `.c`, `.cpp`, `.h`, `.hpp`, `.rs`, `.rb`, `.php`, `.swift`, `.kt`, `.lua`, `.sh`, `.bat`, `.ps1`, `.sql`, `.proto`, `.graphql`
   - **Document files**: `.md`, `.txt`, `.yaml`, `.yml`, `.json`, `.xml`, `.csv`, `.rst`, `.adoc`
   - **Other**: warn user and skip, or ask whether to include

   Display the file list:
   ```
   📁 匹配到 N 个文件:
   代码文件 (M 个):
     - src/battle/skill.ts (typescript, 245 lines)
     - src/battle/damage.ts (typescript, 180 lines)
   文档文件 (K 个):
     - docs/battle-design.md (128 lines)
   ```

2. **Process each file** — for each file, execute Steps 2a–2f:

   a. **Read file content**:
      Use the Read tool to read the full file content. **禁止对文件内容进行蒸馏、精简、摘要或重组。** 原始内容完整保留。

   b. **Module matching** (project type only):

      Read `${KB_ROOT}/projects/<project-id>/project-modules.yaml`.

      If `--module` was explicitly provided, use it for ALL files in this import batch.

      Otherwise, for each file:
      - For **code files**: extract identifiers from file path (directory names, file name) and code content (class names, function names, comments). Match against module `tags`.
      - For **document files**: same logic as kng-kb import — match content against module `tags` via substring matching.
      - Pick the module with the highest tag hit count. If < 3 hits, attempt auto-discovery (same as kng-kb import Step 3e).

      Inform the user:
      ```
      src/battle/skill.ts → [battle] 战斗系统 (命中 tags: 战斗, 技能, skill, damage)
      src/battle/damage.ts → [battle] 战斗系统 (命中 tags: 战斗, 伤害, damage, buff)
      ```

   c. **Generate file name**:
      - Code files: `{module_id}-{original_filename_without_ext}-code.md` (e.g., `battle-skill-code.md`)
      - Document files: `{module_id}-{title_slug}.md` (e.g., `battle-design-notes.md`)
      - If `general` module, no prefix.

   d. **Write KB file**:

      **Code file format:**
      ```markdown
      # {filename}
      <!-- source: {relative_path_from_project_root} -->
      <!-- source_type: code -->
      <!-- module: {module_id} -->
      <!-- imported: {date} -->
      <!-- language: {language} -->

      ```{language}
      {完整源代码，不做任何删减}
      ```
      ```

      **Document file format:**
      ```markdown
      # {title}
      <!-- source: {relative_path_from_project_root} -->
      <!-- source_type: local_doc -->
      <!-- module: {module_id} -->
      <!-- imported: {date} -->
      <!-- related_modules: {comma-separated list, if cross-references detected} -->

      {原始文档内容，不做任何删减或改写}
      ```

      Write to:
      - capability → `${KNG_HOME}/kb/capability/<filename>.md`
      - project → `${KB_ROOT}/projects/<project-id>/<filename>.md`

   e. **Detect cross-system references** (project type, code files):

      Scan code for imports, function calls, or comments that reference other modules:
      - `import ... from '../reward/...'` → references `reward` module
      - Comments mentioning other systems (e.g., `// 调用背包系统扣除道具`)
      - API calls to other modules

      If cross-system references are found AND they match existing modules in `project-modules.yaml`, check if the relation already exists. If not, append the new relation (same format as kng-kb import Step 5).

   f. **DB mode sync**: If in DB mode, after writing all KB files:
      ```bash
      python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
        --db "${DB_PATH}" \
        --capability-dir "${KNG_HOME}/kb/capability" \
        --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
        --project-id "${PROJECT_ID}" --force
      ```

3. **Report**:
   ```
   ✅ 导入完成，共导入 N 个文件:

   代码文件:
   1. battle-skill-code.md ← src/battle/skill.ts [battle]
   2. battle-damage-code.md ← src/battle/damage.ts [battle]

   文档文件:
   3. battle-design-notes.md ← docs/battle-design.md [battle]

   新增跨系统关联: (if any)
   battle ──depends_on──▶ inventory  [HIGH] 技能消耗道具
   ```

---

## Sub-command: `link`

Establish metadata cross-links between an existing KB document entry and local code files. The code files are imported into the KB and both sides receive linking metadata.

### Arguments
- `--doc <kb_filename>` (required): The KB entry filename to link FROM (e.g., `battle-skill-system.md`). Must already exist in the project KB.
- `--code <path>` (required): Local code file path or glob pattern (e.g., `src/battle/**/*.ts`).
- `--project <id>` (optional): Target project. If omitted, use active project.

### Steps

1. **Validate the document KB entry**:

   Resolve the full path: `${KB_ROOT}/projects/<project-id>/<kb_filename>`.

   If the file does not exist, search for it:
   - Use Glob to find files matching `*<kb_filename>*` in the project KB directory.
   - If found, suggest the match. If not found, report error and stop.

   Read the document file. Extract its `module` from the metadata comment (`<!-- module: xxx -->`).

2. **Expand and import code files**:

   Use Glob to expand `--code` path. For each matched code file:

   a. Read the file content using Read tool. **禁止蒸馏，完整保留原始代码。**

   b. **Module assignment**: Code files inherit the document's `module_id` by default. If a code file clearly belongs to a different module (e.g., its path contains a different module name), detect and use the appropriate module instead.

   c. **Generate file name**: `{module_id}-{original_filename_without_ext}-code.md`

   d. **Check for existing KB entry**: If a KB file with the same name already exists, ask user whether to overwrite or skip.

   e. **Write KB file** with linking metadata:
      ```markdown
      # {filename}
      <!-- source: {relative_path} -->
      <!-- source_type: code -->
      <!-- module: {module_id} -->
      <!-- imported: {date} -->
      <!-- language: {language} -->
      <!-- linked_doc: {kb_filename} -->

      ```{language}
      {完整源代码，不做任何删减}
      ```
      ```

3. **Update the document KB entry with back-links**:

   Read the existing document KB file. Use Edit tool to add or update the `linked_code` metadata comment.

   If the document already has a `<!-- linked_code: ... -->` line, append the new code filenames to the existing list.

   If not, insert `<!-- linked_code: {code_file_1}, {code_file_2}, ... -->` after the last existing metadata comment line (i.e., after `<!-- related_modules: ... -->` or `<!-- imported: ... -->`).

4. **DB mode sync**: If in DB mode:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/kb_import.py" \
     --db "${DB_PATH}" \
     --capability-dir "${KNG_HOME}/kb/capability" \
     --project-dir "${KB_ROOT}/projects/${PROJECT_ID}" \
     --project-id "${PROJECT_ID}" --force
   ```

5. **Report**:
   ```
   ✅ 关联完成

   📄 文档: battle-skill-system.md [battle] 战斗技能系统
   🔗 已关联代码文件:
     - battle-skill-code.md ← src/battle/skill.ts
     - battle-damage-code.md ← src/battle/damage.ts
     - battle-buff-code.md ← src/battle/buff.ts

   文档已添加 linked_code 元数据。
   代码文件已添加 linked_doc 元数据。
   ```

---

## Notes

- **禁止蒸馏**: 所有导入的文件内容（代码或文档）必须完整保留原始内容，不做任何精简、摘要或重组。
- Code KB files wrap the source code in a markdown code block with language annotation for syntax highlighting and retrieval.
- The `source` metadata uses relative paths from the project root, making it portable.
- `linked_doc` and `linked_code` metadata enable bidirectional navigation between design documents and implementation code.
- The `source_type` metadata (`code` | `local_doc`) allows retrieval scripts to filter by content type.
- Always use UTF-8 encoding when writing files.
- If importing a large number of files (>20), display progress and ask user to confirm before proceeding.
- **禁止在项目目录或当前工作目录创建中间文件。** 需要临时脚本或缓存数据时，必须写入 `${KNG_HOME}/cache/` 目录（不存在则先创建）。流程结束后应清理不再需要的缓存文件。
