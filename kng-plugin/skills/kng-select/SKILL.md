---
name: kng-select
description: "Switch the active project knowledge base. Use to change which project KB is used by /kng-test, /kng-kb, and /kng-evolve."
argument-hint: "[<project-id> | --list]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# KNG Project Selector

When invoked with: $ARGUMENTS

Switch or inspect the active project knowledge base. All other KNG skills (`/kng-test`, `/kng-kb`, `/kng-evolve`) use the active project by default.

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- `project-id` (optional): The project to switch to (e.g., `demo-game`)
- `--list` (optional): Just list available projects without switching

Set defaults:
- `KB_ROOT` = `./kb` (or from `kng.config.json` → `kb_root`)
- `DB_PATH` = from `kng.config.json` → `db_path` (optional)

## Step 2: List Available Projects

### File mode (no `db_path`):
Use Glob to find all subdirectories in `${KB_ROOT}/projects/` that contain at least one `.md` or `.yaml` file (i.e., initialized project KBs).

### DB mode (`db_path` set):
Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/db.py" stats --db "${DB_PATH}"` for overall counts. Additionally, query the DB for project list — the `projects` table has all registered projects with their metadata.

### Both modes:
Read `kng.config.json` to determine the currently active project (field: `active_project`, fallback to `default_project`).

For each project found, show:
- Project ID
- Whether it's the currently active one (mark with `✦`)
- Number of registered modules
- Number of KB entries (DB mode) or KB files (file mode)

If `--list` was specified, display the list and stop here.

## Step 3: Resolve Target Project

### If `project-id` was provided:
1. Verify `${KB_ROOT}/projects/${project-id}/` exists.
2. If it doesn't exist, ask the user:
   - "项目 `{project-id}` 不存在。是否现在创建？" 
   - If yes, invoke `/kng-init {project-id}` via Skill tool, then continue.
   - If no, show the available projects list and ask to pick one.

### If `project-id` was NOT provided:
1. Show the available projects list from Step 2.
2. If ZERO projects exist: inform user and invoke `/kng-init` to create one.
3. If ONE project exists: auto-select it.
4. If MULTIPLE projects exist: ask user to choose.

## Step 4: Save Selection

Read `kng.config.json` (or create if not exists). Set `active_project` to the selected project ID.

```json
{
  "active_project": "<selected-project-id>",
  "kb_root": "./kb",
  "output_dir": "./test-output",
  "db_path": "./kng.db"
}
```

If the config already exists, only update the `active_project` field using Edit tool — preserve all other fields (including `db_path`).

If there is a legacy `default_project` field, keep it in sync (set it to the same value).

## Step 5: Report

Display:

```
✅ 已切换项目知识库: {project-id}

📂 项目路径: {KB_ROOT}/projects/{project-id}/
📦 已注册模块: {module_count} 个
📄 知识库文件: {file_count} 个

后续 /kng-test、/kng-kb、/kng-evolve 将默认使用此项目。
如需切换，使用 /kng-select <其他项目> 或 /kng-select --list 查看所有项目。
```
