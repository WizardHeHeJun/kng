#!/usr/bin/env python3
"""UserPromptSubmit hook: auto-retrieve KB context for every user prompt.

Reads the user's prompt from stdin (JSON), calls retrieve_kb.py,
and returns top hits as additionalContext so Claude sees relevant
knowledge before answering.

Requires: kng.config.json with active_project set.
No external dependencies — stdlib only.
"""

import json
import os
import pathlib
import subprocess
import sys

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
RETRIEVE_SCRIPT = SCRIPT_DIR / "retrieve_kb.py"

MIN_PROMPT_LEN = 8
MAX_CONTEXT_CHARS = 9500
RETRIEVE_TIMEOUT_SEC = 4


def _resolve_kng_home() -> pathlib.Path:
    env = os.environ.get("KNG_HOME")
    if env:
        return pathlib.Path(env)
    return pathlib.Path.home() / ".kng-plugin"


def _load_config(kng_home: pathlib.Path) -> dict:
    cfg_path = kng_home / "kng.config.json"
    if not cfg_path.exists():
        return {}
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _build_retrieve_cmd(config: dict, kng_home: pathlib.Path, query: str) -> list:
    """Build the command-line for retrieve_kb.py based on storage mode."""
    kb_root = pathlib.Path(config.get("kb_root", str(kng_home / "kb")))
    project_id = config.get("active_project", "")
    db_path = config.get("db_path", "")

    cmd = [sys.executable, str(RETRIEVE_SCRIPT), "--query", query, "--top-k", "3"]

    if db_path and pathlib.Path(db_path).exists():
        cmd += ["--db", db_path, "--project", project_id]
    else:
        cap_dir = kb_root / "capability"
        proj_dir = kb_root / "projects" / project_id if project_id else kb_root / "projects"
        cmd += ["--capability-dir", str(cap_dir), "--project-dir", str(proj_dir)]

    return cmd


def _format_hits(hits: list, label: str) -> str:
    if not hits:
        return ""
    lines = [f"### {label}"]
    for i, h in enumerate(hits, 1):
        path = pathlib.Path(h.get("path", ""))
        score = h.get("score", 0)
        snippet = h.get("snippet", "").strip()
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "…"
        lines.append(f"\n**{i}. {path.name}** (score: {score:.1f})")
        lines.append(snippet)
    return "\n".join(lines)


def _format_context(result: dict) -> str:
    parts = []

    mod = result.get("detected_module", {})
    if mod.get("id") and mod["id"] != "general":
        parts.append(f"**检测到模块**: {mod.get('name', mod['id'])} (置信度: {mod.get('score', 0):.1f})")

    related = result.get("related_modules", [])
    if related:
        rels = ", ".join(f"{r['module_id']}({r['risk_level']})" for r in related[:3])
        parts.append(f"**关联模块**: {rels}")

    cap_text = _format_hits(result.get("capability_hits", []), "能力库命中")
    proj_text = _format_hits(result.get("project_hits", []), "项目库命中")

    if cap_text:
        parts.append(cap_text)
    if proj_text:
        parts.append(proj_text)

    if not parts:
        return ""

    header = "## KNG 知识库自动检索结果\n"
    body = header + "\n\n".join(parts)

    if len(body) > MAX_CONTEXT_CHARS:
        body = body[:MAX_CONTEXT_CHARS] + "\n\n…(已截断)"

    return body


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt = input_data.get("prompt", "").strip()
    if len(prompt) < MIN_PROMPT_LEN:
        sys.exit(0)
    # Skip slash commands (e.g. /kng-evolve) — the command name itself is
    # not a meaningful retrieval query and only adds noise.
    if prompt.startswith("/"):
        sys.exit(0)

    kng_home = _resolve_kng_home()
    config = _load_config(kng_home)
    if not config.get("active_project"):
        sys.exit(0)

    cmd = _build_retrieve_cmd(config, kng_home, prompt)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=RETRIEVE_TIMEOUT_SEC,
            cwd=str(SCRIPT_DIR),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        sys.exit(0)

    if proc.returncode != 0 or not proc.stdout.strip():
        sys.exit(0)

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(0)

    total_hits = len(result.get("capability_hits", [])) + len(result.get("project_hits", []))
    if total_hits == 0:
        sys.exit(0)

    context = _format_context(result)
    if not context:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
