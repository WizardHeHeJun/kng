#!/usr/bin/env python3
"""SessionStart hook: auto-start KB viewer if DB mode is configured.

Reads kng.config.json, checks if the viewer is already running,
and starts it in the background if not.

Also enforces version coherence: if a stale viewer from an older
plugin version is still bound to the port, it gets shut down so the
current version can take over.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from typing import Optional

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
VIEWER_SCRIPT = SCRIPT_DIR / "db_viewer.py"
PLUGIN_JSON = SCRIPT_DIR.parent / ".claude-plugin" / "plugin.json"
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


def _current_plugin_version() -> str:
    try:
        return json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version", "unknown")
    except Exception:
        return "unknown"


def _viewer_info() -> Optional[dict]:
    """Return viewer's /api/version payload, or None if unreachable."""
    try:
        req = urllib.request.Request(f"{VIEWER_URL}/api/version", method="GET")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _viewer_is_responding() -> bool:
    try:
        req = urllib.request.Request(f"{VIEWER_URL}/api/stats", method="GET")
        with urllib.request.urlopen(req, timeout=1):
            return True
    except Exception:
        return False


def _request_shutdown() -> None:
    try:
        req = urllib.request.Request(f"{VIEWER_URL}/api/shutdown", method="GET")
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def _port_pids() -> list:
    """Return PIDs listening on VIEWER_PORT (cross-platform, stdlib only)."""
    pids = set()
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
            needle = f"127.0.0.1:{VIEWER_PORT}"
            for line in out.splitlines():
                if needle in line and "LISTENING" in line:
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        else:
            out = subprocess.run(
                ["lsof", "-iTCP:{}".format(VIEWER_PORT), "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
    except Exception:
        pass
    return sorted(pids)


def _kill_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _wait_port_free(timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_pids():
            return True
        time.sleep(0.1)
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


def _free_port(timeout: float = 2.0) -> None:
    """Ensure VIEWER_PORT is fully released. Try graceful shutdown first,
    then force-kill any PID still bound — handles zombie listeners and the
    multiple-listener case where shutdown only hits one of them."""
    if not _port_pids():
        return
    _request_shutdown()
    if _wait_port_free(timeout=timeout):
        return
    for pid in _port_pids():
        _kill_pid(pid)
    _wait_port_free(timeout=2.0)


def _ensure_viewer(db_path: str, current_version: str) -> Optional[str]:
    """Make sure a viewer matching current_version is running on VIEWER_PORT.

    Returns a status message if action was taken, else None.
    """
    info = _viewer_info()
    if info is not None and info.get("version") == current_version:
        return None  # already up to date and responsive

    old_version = info.get("version") if info else None
    _free_port()
    _start_viewer(db_path)

    if old_version:
        return f"知识库查看器 v{old_version} → v{current_version}：{VIEWER_URL}"
    return f"知识库查看器已启动 v{current_version}：{VIEWER_URL}"


def main():
    kng_home = _resolve_kng_home()
    config = _load_config(kng_home)

    db_path = config.get("db_path", "")
    if not db_path or not pathlib.Path(db_path).exists():
        sys.exit(0)

    removed = _purge_stale(db_path)
    current_version = _current_plugin_version()

    context_parts = []
    if removed > 0:
        context_parts.append(f"已自动清理 {removed} 条过期知识库条目（源文件已删除）")

    msg = _ensure_viewer(db_path, current_version)
    if msg:
        context_parts.append(msg)

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
