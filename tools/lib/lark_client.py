#!/usr/bin/env python3
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class RunResult:
    stdout: str
    stderr: str
    returncode: int


def run_cmd(args: List[str]) -> RunResult:
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return RunResult(stdout=p.stdout, stderr=p.stderr, returncode=p.returncode)


def fetch_lark_doc(url: str, identity: str = "user") -> str:
    cmd = ["lark-cli", "docs", "+fetch", "--url", url, "--as", identity]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RuntimeError(
            "读取飞书文档失败。\n"
            f"command: {' '.join(cmd)}\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
    return result.stdout.strip()
