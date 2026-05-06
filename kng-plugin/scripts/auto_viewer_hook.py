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


def main():
    kng_home = _resolve_kng_home()
    config = _load_config(kng_home)

    db_path = config.get("db_path", "")
    if not db_path or not pathlib.Path(db_path).exists():
        sys.exit(0)

    if _viewer_is_running():
        sys.exit(0)

    _start_viewer(db_path)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"知识库查看器已启动：{VIEWER_URL}",
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
