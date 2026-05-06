#!/usr/bin/env python3
"""SessionStart hook: auto-start KB viewer if DB mode is configured.

Reads kng.config.json, checks if the viewer is already running,
and starts it in the background if not.
"""

import json
import os
import pathlib
import subprocess
import sys
import urllib.request

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
VIEWER_SCRIPT = SCRIPT_DIR / "db_viewer.py"
VIEWER_PORT = 8787
VIEWER_URL = f"http://127.0.0.1:{VIEWER_PORT}"


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


def _viewer_is_running() -> bool:
    try:
        req = urllib.request.Request(f"{VIEWER_URL}/api/stats", method="GET")
        with urllib.request.urlopen(req, timeout=1):
            return True
    except Exception:
        return False


def _start_viewer(db_path: str):
    if sys.platform == "win32":
        subprocess.Popen(
            [sys.executable, str(VIEWER_SCRIPT), "--db", db_path, "--port", str(VIEWER_PORT)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            [sys.executable, str(VIEWER_SCRIPT), "--db", db_path, "--port", str(VIEWER_PORT)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _purge_stale(db_path: str) -> int:
    try:
        from db import KngDatabase
        db = KngDatabase(db_path)
        db.connect()
        db.initialize()
        removed = db.purge_stale_entries()
        db.close()
        return removed
    except Exception:
        return 0


def main():
    kng_home = _resolve_kng_home()
    config = _load_config(kng_home)

    db_path = config.get("db_path", "")
    if not db_path or not pathlib.Path(db_path).exists():
        sys.exit(0)

    removed = _purge_stale(db_path)

    context_parts = []
    if removed > 0:
        context_parts.append(f"已自动清理 {removed} 条过期知识库条目（源文件已删除）")

    if not _viewer_is_running():
        _start_viewer(db_path)
        context_parts.append(f"知识库查看器已启动：{VIEWER_URL}")

    if context_parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }
        print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
