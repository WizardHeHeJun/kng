#!/usr/bin/env python3
"""Web-based viewer for KNG SQLite database.

Stdlib-only. No external dependencies.

Usage:
    python db_viewer.py --db ./kng.db
    python db_viewer.py --db ./kng.db --port 9000 --host 0.0.0.0
"""
import argparse
import base64
import html
import json
import os
import sqlite3
import sys
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FAVICON_DATA = ""
_favicon_path = os.path.join(_SCRIPT_DIR, "Elysia.png")
if os.path.isfile(_favicon_path):
    with open(_favicon_path, "rb") as _f:
        _FAVICON_DATA = base64.b64encode(_f.read()).decode("ascii")


def _read_plugin_version() -> str:
    pj = os.path.join(_SCRIPT_DIR, "..", ".claude-plugin", "plugin.json")
    try:
        with open(pj, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "unknown")
    except Exception:
        return "unknown"


_VIEWER_VERSION = _read_plugin_version()

# ── HTML Templates ──

_CSS = """
:root {
    --bg: #ffffff;
    --surface: #ffffff;
    --surface2: #f8f9fa;
    --border: #e8e8e8;
    --text: #333333;
    --text2: #999999;
    --accent: #e84393;
    --accent2: #d63384;
    --green: #2ecc71;
    --orange: #e67e22;
    --red: #e74c3c;
    --yellow: #f1c40f;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, "PingFang SC", "Segoe UI", "Noto Sans SC", "Helvetica Neue", sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.6; min-height: 100vh; -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: none; color: var(--accent2); }

.topbar {
    background: #ffffff;
    border-bottom: 1px solid var(--border);
    padding: 0 24px; display: flex; align-items: center; gap: 20px;
    position: sticky; top: 0; z-index: 100; height: 48px;
}
.topbar h1 { font-size: 16px; font-weight: 600; white-space: nowrap; color: var(--accent); }
.topbar nav { display: flex; gap: 4px; flex-wrap: wrap; height: 100%; align-items: stretch; }
.topbar nav a {
    color: var(--text2); padding: 0 14px; font-size: 14px;
    display: flex; align-items: center;
    border-bottom: 2px solid transparent; transition: color .15s;
}
.topbar nav a:hover { color: var(--text); }
.topbar nav a.active {
    color: var(--accent); border-bottom-color: var(--accent); font-weight: 600;
}
.search-box {
    margin-left: auto; display: flex; gap: 6px;
}
.search-box input {
    background: var(--surface2); border: 1px solid transparent;
    color: var(--text); padding: 6px 12px; border-radius: 6px;
    font-size: 13px; width: 200px; outline: none; transition: all .2s;
}
.search-box input:focus { background: #fff; border-color: var(--accent); }
.search-box button {
    background: var(--accent); color: #fff; border: none;
    padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
    transition: background .15s;
}
.search-box button:hover { background: var(--accent2); }

.container { max-width: 1200px; margin: 0 auto; padding: 20px 24px; }
h2 { font-size: 20px; margin-bottom: 16px; font-weight: 600; color: var(--text); }
h3 { font-size: 14px; margin-bottom: 8px; color: var(--text2); font-weight: 500; }

.grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px; margin-bottom: 24px;
}
.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px 20px; transition: box-shadow .2s;
}
.card:hover { box-shadow: 0 4px 12px rgba(31,35,41,.08); }
.card .label { font-size: 12px; color: var(--text2); margin-bottom: 4px; }
.card .value { font-size: 28px; font-weight: 700; color: var(--text); }
.card a { color: inherit; display: block; }
.card a:hover { text-decoration: none; }

table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: var(--surface); border-radius: 8px;
    overflow: hidden; border: 1px solid var(--border);
}
th {
    text-align: left; padding: 10px 16px;
    background: var(--surface2); font-size: 12px;
    color: var(--text2); font-weight: 600; text-transform: uppercase;
    letter-spacing: .3px; border-bottom: 1px solid var(--border);
    white-space: nowrap;
}
td {
    padding: 10px 16px; border-bottom: 1px solid #f0f1f5;
    font-size: 13px; vertical-align: top; color: var(--text);
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #fafafa; }

.tag {
    display: inline-block; background: var(--surface2);
    border: none; border-radius: 4px;
    padding: 2px 8px; font-size: 12px; margin: 1px 2px;
    color: var(--text2);
}
details.tag-collapse { display: inline; }
details.tag-collapse > summary {
    display: inline-block; list-style: none; cursor: pointer;
    background: #fff0f6; color: var(--accent);
    border-radius: 4px; padding: 2px 8px; font-size: 12px;
    margin: 1px 2px; user-select: none;
}
details.tag-collapse > summary::-webkit-details-marker { display: none; }
details.tag-collapse > summary::marker { content: ""; }
details.tag-collapse[open] > summary { background: var(--surface2); color: var(--text2); }

.entry-tabs { margin-bottom: 16px; }
.entry-tabs > input[type=radio] { display: none; }
.entry-tabs > label {
    display: inline-block; padding: 6px 14px; cursor: pointer;
    font-size: 13px; color: var(--text2);
    border-bottom: 2px solid transparent; user-select: none;
    margin-right: 4px;
}
.entry-tabs > label:hover { color: var(--text); }
.entry-tabs > .tab-pane { display: none; }
.entry-tabs > input.tab-radio-doc:checked ~ label.tab-label-doc,
.entry-tabs > input.tab-radio-code:checked ~ label.tab-label-code {
    color: var(--accent); border-bottom-color: var(--accent); font-weight: 600;
}
.entry-tabs > input.tab-radio-doc:checked ~ .tab-pane.tab-pane-doc,
.entry-tabs > input.tab-radio-code:checked ~ .tab-pane.tab-pane-code {
    display: block;
}
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 12px; font-weight: 500;
}
.badge-cap { background: #e8f8f0; color: var(--green); }
.badge-proj { background: #ffe0ec; color: var(--accent); }
.badge-high { background: #fee2e2; color: var(--red); }
.badge-medium { background: #fff3e0; color: var(--orange); }
.badge-low { background: #e8f8f0; color: var(--green); }

.content-box {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; margin-bottom: 16px;
    white-space: pre-wrap; font-size: 13px; line-height: 1.8;
    max-height: 600px; overflow-y: auto;
}

.pagination {
    display: flex; gap: 6px; margin-top: 16px; align-items: center;
    justify-content: center;
}
.pagination a, .pagination span {
    padding: 5px 12px; border-radius: 6px; font-size: 13px;
}
.pagination a {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    transition: all .15s;
}
.pagination a:hover { border-color: var(--accent); color: var(--accent); }
.pagination span { color: var(--text2); }

.detail-grid {
    display: grid; grid-template-columns: 120px 1fr;
    gap: 6px 16px; margin-bottom: 20px;
}
.detail-grid .k { color: var(--text2); font-size: 13px; text-align: right; }
.detail-grid .v { font-size: 13px; }

.empty { text-align: center; padding: 48px; color: var(--text2); font-size: 14px; }

.tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.tab {
    padding: 8px 20px; font-size: 14px; font-weight: 400; cursor: pointer;
    color: var(--text2); border-bottom: 2px solid transparent;
    margin-bottom: -1px; transition: color .15s;
    text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }
.tab.active .tab-count { background: #ffe0ec; color: var(--accent); }
.tab .tab-count {
    background: var(--surface2); border-radius: 10px; padding: 1px 7px;
    font-size: 11px; font-weight: 400; color: var(--text2);
}

.rel-arrow { color: var(--accent); font-weight: 500; }

.graph-container {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; margin-bottom: 16px;
}
.project-bar {
    background: #fafafa; border-bottom: 1px solid var(--border);
    padding: 8px 24px; display: flex; align-items: center; gap: 10px;
    font-size: 13px; color: var(--text2);
}
.project-bar a { color: var(--accent); text-decoration: none; font-weight: 500; }
.project-bar a:hover { color: var(--accent2); }
.project-bar .proj-name { color: var(--text); font-weight: 500; }
.project-bar .clear-btn {
    color: var(--text2); font-size: 12px; margin-left: 4px;
    cursor: pointer; text-decoration: none;
}
.project-bar .clear-btn:hover { color: var(--red); }

.project-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; cursor: pointer;
    transition: box-shadow .2s;
}
.project-card:hover { box-shadow: 0 4px 12px rgba(31,35,41,.08); }
.project-card .proj-title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.project-card .proj-id { font-size: 12px; color: var(--text2); }
.project-card .proj-desc { font-size: 13px; color: var(--text2); margin-top: 6px; }

.graph-node {
    display: inline-block; background: var(--surface);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 14px; margin: 3px; font-size: 13px; font-weight: 400;
    cursor: pointer; transition: all 0.15s;
    user-select: none;
}
.graph-node:hover { border-color: var(--accent); color: var(--accent); background: #fff7f9; }
.graph-node.active { border-color: var(--accent); color: #fff; background: var(--accent); }
.rel-row-hidden { display: none; }
.graph-edge {
    padding: 4px 0; font-size: 13px; color: var(--text2);
}
"""

_NAV_ITEMS = [
    ("/", "总览"),
    ("/table/projects", "项目"),
    ("/table/modules", "模块"),
    ("/table/kb_entries", "知识库"),
    ("/table/skills", "技能工具箱"),
    ("/table/test_designs", "测试设计"),
    ("/table/learning_feedback", "反馈"),
    ("/modules", "模块关联"),
]

_TABLE_LABELS = {
    "projects": "项目",
    "modules": "模块",
    "module_relations": "模块关联",
    "kb_entries": "知识条目",
    "skills": "技能",
    "test_designs": "测试设计",
    "learning_feedback": "学习反馈",
}

_COLUMN_LABELS = {
    "id": "ID",
    "name": "名称",
    "description": "描述",
    "project_id": "项目ID",
    "module_id": "模块ID",
    "title": "标题",
    "content": "内容",
    "source_url": "来源链接",
    "source_file": "来源文件",
    "entry_type": "条目类型",
    "tags": "标签",
    "related_modules": "关联模块",
    "kb_type": "库类型",
    "kb_root": "知识库路径",
    "output_dir": "输出目录",
    "imported_at": "导入时间",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "file": "文件",
    "covers": "覆盖范围",
    "when_to_use": "触发条件",
    "input_spec": "输入",
    "output_spec": "输出",
    "required_skills": "所需技能",
    "extra_tags": "附加标签",
    "test_focus": "测试重点",
    "from_module": "源模块",
    "to_module": "目标模块",
    "type": "类型",
    "risk_level": "风险等级",
    "group_name": "分组名称",
    "term": "词条",
    "feature_name": "功能名称",
    "design_json": "设计数据",
    "test_point_count": "测试点数",
    "test_case_count": "用例数",
    "capability_hits": "能力命中",
    "project_hits": "项目命中",
    "feedback_type": "反馈类型",
    "source_design_id": "来源设计ID",
    "routed_to": "路由至",
    "applied": "已应用",
    "snippet": "摘要",
}


def _nav_html(active_path: str, project: str = "") -> str:
    qs = f"?project={urllib.parse.quote(project)}" if project else ""
    items = []
    for href, label in _NAV_ITEMS:
        link = f"{href}{qs}" if href != "/" else href
        cls = ' class="active"' if active_path == href else ""
        items.append(f'<a href="{link}"{cls}>{label}</a>')
    return "\n".join(items)


def _project_bar_html(project: str, project_name: str, active_path: str) -> str:
    if not project:
        return ""
    clear_href = active_path if active_path else "/"
    return f"""<div class="project-bar">
        <span>当前项目：</span>
        <span class="proj-name">{_e(project_name or project)}</span>
        <a class="clear-btn" href="{clear_href}" title="清除项目筛选">✕ 清除</a>
    </div>"""


def _layout(title: str, body: str, active_path: str = "/",
            project: str = "", project_name: str = "") -> str:
    proj_bar = _project_bar_html(project, project_name, active_path)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} — KNG 知识库查看器</title>
{"<link rel='icon' type='image/png' href='data:image/png;base64," + _FAVICON_DATA + "'>" if _FAVICON_DATA else ""}
<style>{_CSS}</style>
</head>
<body>
<div class="topbar">
    <h1>KNG 知识库查看器</h1>
    <nav>{_nav_html(active_path, project)}</nav>
    <form class="search-box" action="/search" method="get">
        {"<input type='hidden' name='project' value='" + _e(project) + "'>" if project else ""}
        <input type="text" name="q" placeholder="搜索知识库...">
        <button type="submit">搜索</button>
    </form>
</div>
{proj_bar}
<div class="container">
{body}
</div>
</body>
</html>"""


def _e(text: Any) -> str:
    return html.escape(str(text)) if text is not None else ""


def _truncate(text: str, maxlen: int = 120) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


_TAG_COLLAPSE_THRESHOLD = 3


def _collapse_tag_parts(parts: List[str]) -> str:
    if len(parts) <= _TAG_COLLAPSE_THRESHOLD:
        return " ".join(parts)
    visible = " ".join(parts[:_TAG_COLLAPSE_THRESHOLD])
    hidden = " ".join(parts[_TAG_COLLAPSE_THRESHOLD:])
    extra = len(parts) - _TAG_COLLAPSE_THRESHOLD
    return (
        f'{visible} '
        f'<details class="tag-collapse">'
        f'<summary>+{extra} 更多</summary> '
        f'{hidden}'
        f'</details>'
    )


def _tags_html(tags_json: str) -> str:
    try:
        tags = json.loads(tags_json) if isinstance(tags_json, str) else tags_json
    except (json.JSONDecodeError, TypeError):
        return _e(str(tags_json))
    if not tags:
        return '<span style="color:var(--text2)">—</span>'
    parts = [f'<span class="tag">{_e(t)}</span>' for t in tags]
    return _collapse_tag_parts(parts)


_RISK_LABELS = {"high": "高", "medium": "中", "low": "低"}
_KB_TYPE_LABELS = {"capability": "能力库", "project": "项目库"}
_ENTRY_TYPE_LABELS = {
    "requirement": "需求",
    "architecture": "架构",
    "test_point": "测试点",
    "issue": "缺陷",
    "guideline": "规范",
    "playbook": "剧本",
    "skill": "技能",
    "general": "通用",
}


def _risk_badge(level: str) -> str:
    label = _RISK_LABELS.get(level, level)
    return f'<span class="badge badge-{_e(level)}">{_e(label)}</span>'


def _kb_type_badge(kb_type: str) -> str:
    cls = "badge-cap" if kb_type == "capability" else "badge-proj"
    label = _KB_TYPE_LABELS.get(kb_type, kb_type)
    return f'<span class="badge {cls}">{_e(label)}</span>'


# ── Pages ──

def page_dashboard(db: sqlite3.Connection) -> str:
    tables = [
        "projects", "modules", "module_relations", "kb_entries",
        "skills", "test_designs", "learning_feedback",
    ]
    cards = []
    for t in tables:
        count = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        label = _TABLE_LABELS.get(t, t)
        cards.append(f"""<div class="card">
            <a href="/table/{t}">
                <div class="label">{label}</div>
                <div class="value">{count}</div>
            </a>
        </div>""")

    cap = db.execute("SELECT COUNT(*) FROM kb_entries WHERE kb_type='capability'").fetchone()[0]
    proj = db.execute("SELECT COUNT(*) FROM kb_entries WHERE kb_type='project'").fetchone()[0]

    body = f"""
    <h2>数据库总览</h2>
    <div class="grid">{"".join(cards)}</div>
    <h3>知识库分布</h3>
    <div class="grid">
        <div class="card">
            <div class="label">能力知识库（跨项目共享）</div>
            <div class="value" style="color:var(--green)">{cap}</div>
        </div>
        <div class="card">
            <div class="label">项目知识库</div>
            <div class="value" style="color:var(--accent)">{proj}</div>
        </div>
    </div>
    """
    return _layout("总览", body, "/")


_PROJECT_FILTERABLE = {"modules", "module_relations", "kb_entries", "test_designs", "learning_feedback"}


def _get_project_name(db: sqlite3.Connection, project_id: str) -> str:
    if not project_id:
        return ""
    row = db.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
    return row["name"] if row else project_id


def page_projects(db: sqlite3.Connection) -> str:
    projects = db.execute("SELECT id, name, description FROM projects ORDER BY id").fetchall()
    if not projects:
        body = '<h2>项目</h2><div class="empty">暂无项目</div>'
        return _layout("项目", body, "/table/projects")

    cards = []
    for p in projects:
        desc = _e(p["description"]) if p["description"] else '<span style="color:var(--text2)">暂无描述</span>'
        cards.append(f"""
        <a href="/table/kb_entries?project={urllib.parse.quote(p['id'])}" style="text-decoration:none;color:inherit">
            <div class="project-card">
                <div class="proj-title">{_e(p['name'])}</div>
                <div class="proj-id">ID: {_e(p['id'])}</div>
                <div class="proj-desc">{desc}</div>
            </div>
        </a>""")

    body = f"""
    <h2>项目 <span style="color:var(--text2);font-size:16px">（共 {len(projects)} 个）</span></h2>
    <p style="color:var(--text2);font-size:13px;margin-bottom:16px">点击项目查看其知识库内容</p>
    <div class="grid">{"".join(cards)}</div>
    """
    return _layout("项目", body, "/table/projects")


def _tags_html_translated(tags_json: str, name_map: Dict[str, str]) -> str:
    try:
        tags = json.loads(tags_json) if isinstance(tags_json, str) else tags_json
    except (json.JSONDecodeError, TypeError):
        return _e(str(tags_json))
    if not tags:
        return '<span style="color:var(--text2)">—</span>'
    parts = [f'<span class="tag">{_e(name_map.get(t, t))}</span>' for t in tags]
    return _collapse_tag_parts(parts)


def _module_tags_html(tags_json: str, name_map: Dict[str, str], project_id: str = "") -> str:
    try:
        tags = json.loads(tags_json) if isinstance(tags_json, str) else tags_json
    except (json.JSONDecodeError, TypeError):
        return _e(str(tags_json))
    if not tags:
        return '<span style="color:var(--text2)">—</span>'
    qs = f"?project={urllib.parse.quote(project_id)}" if project_id else ""
    parts = []
    for t in tags:
        display = name_map.get(t, t)
        parts.append(
            f'<a href="/module/{urllib.parse.quote(str(t))}{qs}" '
            f'class="tag" style="cursor:pointer;color:var(--accent)">{_e(display)}</a>'
        )
    return _collapse_tag_parts(parts)


def _module_link(module_id: str, name_map: Dict[str, str], project_id: str = "") -> str:
    if not module_id:
        return '<span style="color:var(--text2)">—</span>'
    display = name_map.get(module_id, module_id) if name_map else module_id
    qs = f"?project={urllib.parse.quote(project_id)}" if project_id else ""
    return (
        f'<a href="/module/{urllib.parse.quote(str(module_id))}{qs}">'
        f'{_e(display)}</a>'
    )


def _render_table_rows(cur, rows, table: str, hidden_cols: set,
                       module_names: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    """Render table header + tbody HTML from cursor metadata and rows."""
    all_cols = [desc[0] for desc in cur.description] if cur.description else []
    cols = [c for c in all_cols if c not in hidden_cols]
    col_indices = [i for i, c in enumerate(all_cols) if c not in hidden_cols]
    mod_map = module_names or {}

    header = "".join(f"<th>{_e(_COLUMN_LABELS.get(c, c))}</th>" for c in cols)
    id_col_idx = next((i for i, c in enumerate(all_cols) if c == "id"), None)
    project_id_idx = next((i for i, c in enumerate(all_cols) if c == "project_id"), None)
    tbody = []
    for row in rows:
        row_id = row[id_col_idx] if id_col_idx is not None else None
        row_pid = row[project_id_idx] if project_id_idx is not None else ""
        cells = []
        for i, col in zip(col_indices, cols):
            val = row[i]
            if col == "id" and table == "kb_entries":
                cells.append(f'<td><a href="/entry/{val}">{_e(val)}</a></td>')
            elif col == "title" and table == "kb_entries" and row_id is not None:
                cells.append(f'<td><a href="/entry/{row_id}">{_e(val)}</a></td>')
            elif col in ("content", "design_json", "snippet"):
                cells.append(f"<td>{_e(_truncate(str(val), 60))}</td>")
            elif col == "entry_type" and val:
                cells.append(f"<td>{_e(_ENTRY_TYPE_LABELS.get(val, val))}</td>")
            elif col in ("module_id", "from_module", "to_module"):
                cells.append(f"<td>{_module_link(val, mod_map, row_pid or '')}</td>")
            elif col == "related_modules":
                cells.append(f"<td>{_module_tags_html(val, mod_map, row_pid or '')}</td>")
            elif col in ("tags", "covers", "required_skills",
                         "extra_tags", "test_focus", "capability_hits",
                         "project_hits", "routed_to"):
                cells.append(f"<td>{_tags_html(val)}</td>")
            elif col == "kb_type" and val:
                cells.append(f"<td>{_kb_type_badge(val)}</td>")
            elif col == "risk_level" and val:
                cells.append(f"<td>{_risk_badge(val)}</td>")
            else:
                cells.append(f"<td>{_e(val)}</td>")
        tbody.append(f"<tr>{''.join(cells)}</tr>")
    return header, "".join(tbody)


def page_kb(db: sqlite3.Connection, page: int = 1, per_page: int = 50,
            project: str = "", kb_type: str = "project") -> str:
    project_name = _get_project_name(db, project)

    where_parts = ["kb_type=?"]
    params: list = [kb_type]
    if project and kb_type != "capability":
        where_parts.append("project_id=?")
        params.append(project)
    where = " AND ".join(where_parts)

    total = db.execute(f"SELECT COUNT(*) FROM kb_entries WHERE {where}", params).fetchone()[0]
    offset_val = (page - 1) * per_page
    cur = db.execute(f"SELECT * FROM kb_entries WHERE {where} LIMIT ? OFFSET ?",
                     params + [per_page, offset_val])
    rows = cur.fetchall()

    hidden = {"created_at", "updated_at", "imported_at", "kb_type", "source_file", "source_url"}
    if project:
        hidden.add("project_id")
    if kb_type == "capability":
        hidden.update({"project_id", "module_id", "tags", "related_modules"})

    cap_count = db.execute(
        "SELECT COUNT(*) FROM kb_entries WHERE kb_type='capability'"
    ).fetchone()[0]
    proj_count = db.execute(
        "SELECT COUNT(*) FROM kb_entries WHERE kb_type='project'"
        + (" AND project_id=?" if project else ""),
        [project] if project else [],
    ).fetchone()[0]

    qs_proj = f"&project={urllib.parse.quote(project)}" if project else ""
    proj_active = "active" if kb_type == "project" else ""
    cap_active = "active" if kb_type == "capability" else ""

    tabs_html = f"""
    <div class="tabs">
        <a class="tab {proj_active}" href="/table/kb_entries?kb_type=project{qs_proj}">
            项目知识库 <span class="tab-count">{proj_count}</span>
        </a>
        <a class="tab {cap_active}" href="/table/kb_entries?kb_type=capability{qs_proj}">
            能力知识库 <span class="tab-count">{cap_count}</span>
        </a>
    </div>
    """

    tab_label = "项目知识库" if kb_type == "project" else "能力知识库"

    mod_map = {r["module_id"]: r["name"] for r in
               db.execute("SELECT module_id, name FROM modules").fetchall()}

    if not rows:
        body = f'<h2>知识库</h2>{tabs_html}<div class="empty">暂无数据</div>'
        return _layout("知识库", body, "/table/kb_entries", project, project_name)

    header, tbody_html = _render_table_rows(cur, rows, "kb_entries", hidden, mod_map)

    total_pages = (total + per_page - 1) // per_page
    pag_base = f"/table/kb_entries?kb_type={kb_type}"
    if project:
        pag_base += f"&project={urllib.parse.quote(project)}"
    pag = ""
    if total_pages > 1:
        parts = ['<div class="pagination">']
        if page > 1:
            parts.append(f'<a href="{pag_base}&page={page-1}">&laquo; 上一页</a>')
        parts.append(f"<span>第 {page} / {total_pages} 页</span>")
        if page < total_pages:
            parts.append(f'<a href="{pag_base}&page={page+1}">下一页 &raquo;</a>')
        parts.append("</div>")
        pag = "".join(parts)

    body = f"""
    <h2>知识库</h2>
    {tabs_html}
    <h3>{_e(tab_label)} <span style="color:var(--text2);font-size:14px">（共 {total} 条）</span></h3>
    <div style="overflow-x:auto">
        <table><thead><tr>{header}</tr></thead><tbody>{tbody_html}</tbody></table>
    </div>
    {pag}
    """
    return _layout("知识库", body, "/table/kb_entries", project, project_name)


def page_skills(db: sqlite3.Connection) -> str:
    rows = db.execute(
        "SELECT id, name, file, tags, covers, when_to_use, input_spec, output_spec "
        "FROM skills ORDER BY id"
    ).fetchall()

    if not rows:
        body = '<h2>技能工具箱</h2><div class="empty">暂无可调用技能</div>'
        return _layout("技能", body, "/table/skills")

    cards = []
    for row in rows:
        d = dict(row)
        tags_html = _tags_html(d.get("tags", "[]"))
        covers_html = _tags_html(d.get("covers", "[]"))
        when_to_use = _e(d.get("when_to_use") or "—")
        input_spec = _e(d.get("input_spec") or "—")
        output_spec = _e(d.get("output_spec") or "—")

        cards.append(f"""
        <div class="card" style="padding:20px;margin-bottom:12px;border-radius:8px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
                <span style="font-size:18px;font-weight:600;color:var(--text)">{_e(d['name'])}</span>
                <span style="font-size:12px;color:var(--text2);background:var(--surface2);
                      padding:2px 8px;border-radius:4px">{_e(d['id'])}</span>
                <span style="font-size:12px;color:var(--text2);margin-left:auto">{_e(d['file'])}</span>
            </div>
            <div style="display:grid;grid-template-columns:80px 1fr;gap:6px 12px;font-size:13px">
                <div style="color:var(--accent);font-weight:500">触发条件</div>
                <div>{when_to_use}</div>
                <div style="color:var(--accent);font-weight:500">输入</div>
                <div>{input_spec}</div>
                <div style="color:var(--accent);font-weight:500">输出</div>
                <div>{output_spec}</div>
                <div style="color:var(--accent);font-weight:500">标签</div>
                <div>{tags_html}</div>
                <div style="color:var(--accent);font-weight:500">覆盖范围</div>
                <div>{covers_html}</div>
            </div>
        </div>""")

    body = f"""
    <h2>技能工具箱 <span style="color:var(--text2);font-size:16px">（共 {len(rows)} 个可调用技能）</span></h2>
    <p style="color:var(--text2);font-size:13px;margin-bottom:16px">
        每个技能可在测试设计流程中被选择和调用。entry_type = "skill" 的知识条目会自动关联到此处。
    </p>
    {"".join(cards)}
    """
    return _layout("技能工具箱", body, "/table/skills")


def page_table(db: sqlite3.Connection, table: str, page: int = 1,
               per_page: int = 50, project: str = "", kb_type: str = "") -> str:
    allowed = {
        "projects", "modules", "module_relations", "kb_entries",
        "skills", "test_designs", "learning_feedback",
    }
    if table not in allowed:
        return _layout("404", '<div class="empty">未找到该表</div>')

    if table == "projects":
        return page_projects(db)

    if table == "kb_entries":
        return page_kb(db, page, per_page, project, kb_type or "project")

    if table == "skills":
        return page_skills(db)

    project_name = _get_project_name(db, project)

    has_project_col = table in _PROJECT_FILTERABLE
    if project and has_project_col:
        total = db.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project,)).fetchone()[0]
        offset_val = (page - 1) * per_page
        cur = db.execute(f"SELECT * FROM {table} WHERE project_id=? LIMIT ? OFFSET ?",
                         (project, per_page, offset_val))
    else:
        total = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        offset_val = (page - 1) * per_page
        cur = db.execute(f"SELECT * FROM {table} LIMIT ? OFFSET ?", (per_page, offset_val))

    hidden_cols = {"created_at", "updated_at", "imported_at"}
    if project and has_project_col:
        hidden_cols.add("project_id")

    rows = cur.fetchall()
    table_label = _TABLE_LABELS.get(table, table)

    if not rows:
        body = f'<h2>{_e(table_label)}</h2><div class="empty">暂无数据</div>'
        return _layout(table_label, body, f"/table/{table}", project, project_name)

    mod_map = {r["module_id"]: r["name"] for r in
               db.execute("SELECT module_id, name FROM modules").fetchall()}
    header, tbody_html = _render_table_rows(cur, rows, table, hidden_cols, mod_map)

    total_pages = (total + per_page - 1) // per_page
    pag = _pagination(page, total_pages, f"/table/{table}", project)

    body = f"""
    <h2>{_e(table_label)} <span style="color:var(--text2);font-size:16px">（共 {total} 条）</span></h2>
    <div style="overflow-x:auto">
        <table><thead><tr>{header}</tr></thead><tbody>{tbody_html}</tbody></table>
    </div>
    {pag}
    """
    return _layout(table_label, body, f"/table/{table}", project, project_name)


def page_entry(db: sqlite3.Connection, entry_id: int) -> str:
    row = db.execute("SELECT * FROM kb_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return _layout("未找到", '<div class="empty">未找到该条目</div>')

    d = dict(row)
    fields = [
        ("ID", d["id"]),
        ("标题", d["title"]),
        ("知识库类型", _kb_type_badge(d["kb_type"])),
        ("条目类型", d["entry_type"]),
        ("所属项目", d.get("project_id") or "—"),
        ("所属模块", d.get("module_id") or "—"),
        ("源文件", d.get("source_file") or "—"),
        ("源链接", d.get("source_url") or "—"),
        ("标签", _tags_html(d.get("tags", "[]"))),
        ("关联模块", _tags_html(d.get("related_modules", "[]"))),
        ("导入时间", d.get("imported_at", "—")),
        ("更新时间", d.get("updated_at", "—")),
    ]
    detail = []
    for k, v in fields:
        if k in ("知识库类型", "标签", "关联模块"):
            detail.append(f'<div class="k">{k}</div><div class="v">{v}</div>')
        else:
            detail.append(f'<div class="k">{k}</div><div class="v">{_e(v)}</div>')

    body = f"""
    <h2>知识条目 #{entry_id}</h2>
    <div class="detail-grid">{"".join(detail)}</div>
    <h3>内容</h3>
    <div class="content-box">{_e(d["content"])}</div>
    <a href="/table/kb_entries">&larr; 返回知识库列表</a>
    """
    return _layout(f"条目 #{entry_id}", body, "/table/kb_entries")


def page_search(db: sqlite3.Connection, query: str, project: str = "") -> str:
    project_name = _get_project_name(db, project)

    if not query.strip():
        body = '<h2>搜索</h2><div class="empty">输入关键词搜索知识库条目</div>'
        return _layout("搜索", body, project=project, project_name=project_name)

    tokens = query.strip().split()
    fts_query = " OR ".join(tokens)
    rows = []

    proj_filter = " AND (kb.project_id=? OR kb.kb_type='capability')" if project else ""
    proj_params = [project] if project else []

    try:
        rows = db.execute(
            f"""SELECT kb.id, kb.title, kb.kb_type, kb.entry_type,
                      kb.project_id, kb.module_id, kb.source_file,
                      substr(kb.content, 1, 300) as snippet, fts.rank
               FROM kb_entries_fts fts
               JOIN kb_entries kb ON kb.id = fts.rowid
               WHERE kb_entries_fts MATCH ?{proj_filter}
               ORDER BY fts.rank
               LIMIT 50""",
            [fts_query] + proj_params,
        ).fetchall()
    except sqlite3.OperationalError:
        pass

    if not rows:
        like_clauses = " OR ".join(["(title LIKE ? OR content LIKE ?)"] * len(tokens))
        like_params = []
        for t in tokens:
            like_params.extend([f"%{t}%", f"%{t}%"])
        proj_filter2 = " AND (project_id=? OR kb_type='capability')" if project else ""
        rows = db.execute(
            f"""SELECT id, title, kb_type, entry_type,
                       project_id, module_id, source_file,
                       substr(content, 1, 300) as snippet,
                       0 as rank
                FROM kb_entries
                WHERE ({like_clauses}){proj_filter2}
                LIMIT 50""",
            like_params + proj_params,
        ).fetchall()

    if not rows:
        body = f"""
        <h2>搜索："{_e(query)}"</h2>
        <div class="empty">未找到相关结果</div>
        """
        return _layout("搜索", body, project=project, project_name=project_name)

    results = []
    for row in rows:
        d = dict(row)
        score = round(-d["rank"], 2)
        entry_type_label = _ENTRY_TYPE_LABELS.get(d["entry_type"], d["entry_type"])
        results.append(f"""<tr>
            <td><a href="/entry/{d['id']}">{_e(d['title'])}</a></td>
            <td>{_kb_type_badge(d['kb_type'])}</td>
            <td>{_e(entry_type_label)}</td>
            <td>{_e(d.get('module_id') or '—')}</td>
            <td>{score}</td>
            <td>{_e(_truncate(d['snippet'], 150))}</td>
        </tr>""")

    body = f"""
    <h2>搜索："{_e(query)}" <span style="color:var(--text2);font-size:16px">（{len(rows)} 条结果）</span></h2>
    <div style="overflow-x:auto">
        <table>
        <thead><tr>
            <th>标题</th><th>库类型</th><th>条目类型</th>
            <th>模块</th><th>评分</th><th>摘要</th>
        </tr></thead>
        <tbody>{"".join(results)}</tbody>
        </table>
    </div>
    """
    return _layout(f"搜索：{query}", body, project=project, project_name=project_name)


def page_modules(db: sqlite3.Connection) -> str:
    projects = db.execute("SELECT id, name FROM projects ORDER BY id").fetchall()
    sections = []

    for proj in projects:
        pid = proj["id"]
        modules = db.execute(
            "SELECT module_id, name, description FROM modules WHERE project_id=? ORDER BY module_id",
            (pid,),
        ).fetchall()
        relations = db.execute(
            "SELECT from_module, to_module, type, risk_level, description "
            "FROM module_relations WHERE project_id=? ORDER BY from_module",
            (pid,),
        ).fetchall()

        mod_name_map = {m["module_id"]: m["name"] for m in modules}

        mod_list = "".join(
            f'<span class="graph-node" data-module="{_e(m["module_id"])}" '
            f'onclick="toggleModuleFilter(this)">'
            f'{_e(m["name"])}</span>'
            for m in modules
        )

        rel_rows = []
        type_symbols = {
            "depends_on": "依赖",
            "feeds_into": "输出到",
            "shares_state": "共享状态",
            "triggers": "触发",
        }
        for r in relations:
            sym = type_symbols.get(r["type"], r["type"])
            from_name = mod_name_map.get(r["from_module"], r["from_module"])
            to_name = mod_name_map.get(r["to_module"], r["to_module"])
            rel_rows.append(f"""<tr data-from="{_e(r['from_module'])}" data-to="{_e(r['to_module'])}">
                <td>{_e(from_name)}</td>
                <td class="rel-arrow">{_e(sym)}</td>
                <td>{_e(to_name)}</td>
                <td>{_risk_badge(r['risk_level'])}</td>
                <td>{_e(r['description'] or '—')}</td>
            </tr>""")

        rel_table = ""
        if rel_rows:
            rel_table = f"""
            <div style="margin-bottom:8px">
                <span id="filter-hint-{_e(pid)}" style="font-size:13px;color:var(--text2)"></span>
            </div>
            <table id="rel-table-{_e(pid)}">
            <thead><tr><th>源模块</th><th>关系</th><th>目标模块</th><th>风险</th><th>说明</th></tr></thead>
            <tbody>{"".join(rel_rows)}</tbody>
            </table>"""
        else:
            rel_table = '<div class="empty" style="padding:16px">暂无关联关系</div>'

        sections.append(f"""
        <h3>项目：{_e(pid)} — {_e(proj['name'])}</h3>
        <div class="graph-container" data-project="{_e(pid)}">
            <div style="margin-bottom:12px;font-size:13px;color:var(--text2)">
                模块（{len(modules)} 个）
                <span style="margin-left:8px;color:var(--text2);font-size:12px">— 点击模块筛选关联关系</span>
            </div>
            {mod_list or '<span style="color:var(--text2)">暂无模块</span>'}
        </div>
        {rel_table}
        <br>
        """)

    if not projects:
        sections.append('<div class="empty">数据库中暂无项目</div>')

    filter_script = """
    <script>
    function toggleModuleFilter(el) {
        var mid = el.getAttribute('data-module');
        var container = el.closest('[data-project]');
        var pid = container.getAttribute('data-project');
        var wasActive = el.classList.contains('active');

        container.querySelectorAll('.graph-node').forEach(function(n) {
            n.classList.remove('active');
        });

        var table = document.getElementById('rel-table-' + pid);
        var hint = document.getElementById('filter-hint-' + pid);
        if (!table) return;
        var rows = table.querySelectorAll('tbody tr');

        if (wasActive) {
            rows.forEach(function(r) { r.classList.remove('rel-row-hidden'); });
            if (hint) hint.textContent = '';
        } else {
            el.classList.add('active');
            var shown = 0;
            rows.forEach(function(r) {
                var from = r.getAttribute('data-from');
                var to = r.getAttribute('data-to');
                if (from === mid || to === mid) {
                    r.classList.remove('rel-row-hidden');
                    shown++;
                } else {
                    r.classList.add('rel-row-hidden');
                }
            });
            var label = el.textContent.trim();
            if (hint) hint.textContent = '筛选：' + label + '（' + shown + ' 条关联）· 再次点击清除筛选';
        }
    }
    </script>
    """

    body = f"""
    <h2>模块关联图谱</h2>
    {"".join(sections)}
    {filter_script}
    """
    return _layout("模块关联", body, "/modules")


_REL_TYPE_LABELS = {
    "depends_on": "依赖",
    "feeds_into": "输出到",
    "shares_state": "共享状态",
    "triggers": "触发",
}


def page_module_detail(db: sqlite3.Connection, module_id: str, project: str = "") -> str:
    if project:
        mod = db.execute(
            "SELECT * FROM modules WHERE module_id=? AND project_id=?",
            (module_id, project),
        ).fetchone()
    else:
        mod = db.execute(
            "SELECT * FROM modules WHERE module_id=? LIMIT 1",
            (module_id,),
        ).fetchone()

    if not mod:
        body = f'<h2>模块未找到</h2><div class="empty">未找到模块 {_e(module_id)}</div>'
        return _layout("模块未找到", body, "/modules", project, _get_project_name(db, project))

    pid = mod["project_id"]
    project_name = _get_project_name(db, pid)

    mod_name_map = {
        m["module_id"]: m["name"]
        for m in db.execute(
            "SELECT module_id, name FROM modules WHERE project_id=?", (pid,)
        ).fetchall()
    }

    info = f"""
    <div class="detail-grid">
        <div class="k">模块ID</div><div class="v">{_e(mod['module_id'])}</div>
        <div class="k">名称</div><div class="v">{_e(mod['name'])}</div>
        <div class="k">所属项目</div><div class="v">{_e(pid)} — {_e(project_name)}</div>
        <div class="k">描述</div><div class="v">{_e(mod['description'] or '—')}</div>
    </div>
    """

    out_rels = db.execute(
        "SELECT to_module, type, risk_level, description FROM module_relations "
        "WHERE project_id=? AND from_module=? ORDER BY to_module",
        (pid, module_id),
    ).fetchall()
    in_rels = db.execute(
        "SELECT from_module, type, risk_level, description FROM module_relations "
        "WHERE project_id=? AND to_module=? ORDER BY from_module",
        (pid, module_id),
    ).fetchall()

    rel_blocks = []
    if out_rels:
        rows_html = []
        for r in out_rels:
            sym = _REL_TYPE_LABELS.get(r["type"], r["type"])
            rows_html.append(f"""<tr>
                <td class="rel-arrow">{_e(sym)}</td>
                <td>{_module_link(r['to_module'], mod_name_map, pid)}</td>
                <td>{_risk_badge(r['risk_level'])}</td>
                <td>{_e(r['description'] or '—')}</td>
            </tr>""")
        rel_blocks.append(f"""
        <h3>输出关系（{len(out_rels)} 条）</h3>
        <table>
        <thead><tr><th>关系</th><th>目标模块</th><th>风险</th><th>说明</th></tr></thead>
        <tbody>{"".join(rows_html)}</tbody>
        </table>
        <br>""")

    if in_rels:
        rows_html = []
        for r in in_rels:
            sym = _REL_TYPE_LABELS.get(r["type"], r["type"])
            rows_html.append(f"""<tr>
                <td>{_module_link(r['from_module'], mod_name_map, pid)}</td>
                <td class="rel-arrow">{_e(sym)}</td>
                <td>{_risk_badge(r['risk_level'])}</td>
                <td>{_e(r['description'] or '—')}</td>
            </tr>""")
        rel_blocks.append(f"""
        <h3>输入关系（{len(in_rels)} 条）</h3>
        <table>
        <thead><tr><th>源模块</th><th>关系</th><th>风险</th><th>说明</th></tr></thead>
        <tbody>{"".join(rows_html)}</tbody>
        </table>
        <br>""")

    if not rel_blocks:
        rel_blocks.append('<h3>关联关系</h3><div class="empty" style="padding:16px">暂无关联关系</div>')

    entries = db.execute(
        "SELECT id, title, kb_type, entry_type, source_file FROM kb_entries "
        "WHERE module_id=? AND project_id=? ORDER BY id DESC",
        (module_id, pid),
    ).fetchall()
    related_entries = db.execute(
        """SELECT id, title, kb_type, entry_type, source_file FROM kb_entries
           WHERE project_id=? AND (module_id IS NULL OR module_id != ?)
                 AND related_modules LIKE ? ORDER BY id DESC""",
        (pid, module_id, f'%"{module_id}"%'),
    ).fetchall()

    def _entry_rows(items):
        out = []
        for e in items:
            et_label = _ENTRY_TYPE_LABELS.get(e["entry_type"], e["entry_type"])
            out.append(f"""<tr>
                <td><a href="/entry/{e['id']}">{_e(e['id'])}</a></td>
                <td><a href="/entry/{e['id']}">{_e(e['title'])}</a></td>
                <td>{_kb_type_badge(e['kb_type'])}</td>
                <td>{_e(et_label)}</td>
                <td>{_e(e['source_file'] or '—')}</td>
            </tr>""")
        return "".join(out)

    def _split_doc_code(items):
        docs, codes = [], []
        for e in items:
            sf = (e["source_file"] or "").lower()
            (codes if sf.endswith("-code.md") else docs).append(e)
        return docs, codes

    def _entries_block(title: str, items, slot: str) -> str:
        docs, codes = _split_doc_code(items)
        empty_pane = '<div class="empty" style="padding:16px">无</div>'
        doc_table = (f'<div style="overflow-x:auto"><table>'
                     f'<thead><tr><th>ID</th><th>标题</th><th>库类型</th><th>条目类型</th><th>源文件</th></tr></thead>'
                     f'<tbody>{_entry_rows(docs)}</tbody></table></div>') if docs else empty_pane
        code_table = (f'<div style="overflow-x:auto"><table>'
                      f'<thead><tr><th>ID</th><th>标题</th><th>库类型</th><th>条目类型</th><th>源文件</th></tr></thead>'
                      f'<tbody>{_entry_rows(codes)}</tbody></table></div>') if codes else empty_pane
        return f"""
        <h3>{title}（{len(items)} 条）</h3>
        <div class="entry-tabs">
            <input type="radio" name="entries-{slot}" id="tab-doc-{slot}" class="tab-radio-doc" checked>
            <input type="radio" name="entries-{slot}" id="tab-code-{slot}" class="tab-radio-code">
            <label for="tab-doc-{slot}" class="tab-label-doc">文档（{len(docs)}）</label>
            <label for="tab-code-{slot}" class="tab-label-code">代码（{len(codes)}）</label>
            <div class="tab-pane tab-pane-doc">{doc_table}</div>
            <div class="tab-pane tab-pane-code">{code_table}</div>
        </div>
        <br>"""

    if entries:
        entries_html = _entries_block("本模块知识条目", entries, "own")
    else:
        entries_html = '<h3>本模块知识条目</h3><div class="empty" style="padding:16px">暂无知识条目</div><br>'

    related_html = ""
    if related_entries:
        related_html = _entries_block("关联到本模块的条目", related_entries, "rel")

    body = f"""
    <h2>模块：{_e(mod['name'])} <span style="color:var(--text2);font-size:14px">（{_e(module_id)}）</span></h2>
    {info}
    {"".join(rel_blocks)}
    {entries_html}
    {related_html}
    <a href="/modules">&larr; 返回模块关联图谱</a>
    """
    return _layout(f"模块 {module_id}", body, "/modules", pid, project_name)


def _pagination(page: int, total_pages: int, base_url: str, project: str = "") -> str:
    if total_pages <= 1:
        return ""
    extra = f"&project={urllib.parse.quote(project)}" if project else ""
    parts = ['<div class="pagination">']
    if page > 1:
        parts.append(f'<a href="{base_url}?page={page-1}{extra}">&laquo; 上一页</a>')
    parts.append(f"<span>第 {page} / {total_pages} 页</span>")
    if page < total_pages:
        parts.append(f'<a href="{base_url}?page={page+1}{extra}">下一页 &raquo;</a>')
    parts.append("</div>")
    return "".join(parts)


# ── HTTP Handler ──

class KngViewerHandler(BaseHTTPRequestHandler):
    db_path: str = ""

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _respond(self, code: int, body: str, content_type: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _parse_qs(self) -> Dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items()}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = self._parse_qs()

        db = self._connect()
        try:
            if path == "/":
                self._respond(200, page_dashboard(db))
            elif path.startswith("/table/"):
                table = path[7:]
                pg = int(params.get("page", "1"))
                proj = params.get("project", "")
                kb_t = params.get("kb_type", "")
                self._respond(200, page_table(db, table, page=pg, project=proj, kb_type=kb_t))
            elif path.startswith("/entry/"):
                try:
                    eid = int(path[7:])
                except ValueError:
                    self._respond(400, _layout("错误", '<div class="empty">无效的条目 ID</div>'))
                    return
                self._respond(200, page_entry(db, eid))
            elif path == "/search":
                q = params.get("q", "")
                proj = params.get("project", "")
                self._respond(200, page_search(db, q, project=proj))
            elif path == "/modules":
                self._respond(200, page_modules(db))
            elif path.startswith("/module/"):
                mod_id = urllib.parse.unquote(path[8:])
                proj = params.get("project", "")
                self._respond(200, page_module_detail(db, mod_id, project=proj))
            elif path == "/api/stats":
                tables = [
                    "projects", "modules", "module_relations", "kb_entries",
                    "skills", "test_designs", "learning_feedback",
                ]
                stats = {}
                for t in tables:
                    stats[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                self._respond(200, json.dumps(stats, indent=2), "application/json")
            elif path == "/api/version":
                payload = {"version": _VIEWER_VERSION, "pid": os.getpid()}
                self._respond(200, json.dumps(payload), "application/json")
            elif path == "/api/shutdown":
                self._respond(200, json.dumps({"shutdown": True}), "application/json")
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._respond(404, _layout("404", '<div class="empty">页面未找到</div>'))
        except Exception as ex:
            self._respond(500, _layout("错误", f'<div class="empty">内部错误：{_e(str(ex))}</div>'))
        finally:
            db.close()

    def log_message(self, format, *args):
        sys.stderr.write(f"[KNG Viewer] {args[0]} {args[1]} {args[2]}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="KNG database web viewer")
    parser.add_argument("--db", required=True, help="Path to kng.db")
    parser.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("SELECT COUNT(*) FROM kb_entries")
    except sqlite3.OperationalError:
        print(f"错误：{args.db} 不是有效的 KNG 数据库。", file=sys.stderr)
        print("请先运行 'python db.py init --db ./kng.db' 初始化。", file=sys.stderr)
        conn.close()
        return 1
    conn.close()

    KngViewerHandler.db_path = args.db
    server = HTTPServer((args.host, args.port), KngViewerHandler)
    print(f"KNG 知识库查看器已启动：http://{args.host}:{args.port}（v{_VIEWER_VERSION}, pid={os.getpid()}）")
    print(f"数据库：{args.db}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
