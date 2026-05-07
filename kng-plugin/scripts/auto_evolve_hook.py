#!/usr/bin/env python3
"""UserPromptSubmit hook: auto-learning trigger.

Maintains a per-session turn counter and rolling transcript of recent
user prompts under ${KNG_HOME}/cache/. Once the configured turn threshold
is reached, injects a directive instructing the main assistant to spawn
a feedback-extraction subagent — keeping the main conversation context
clean while still harvesting candidate feedback into the pending queue.

Reads kng.config.json `auto_evolve` block; disabled if missing or
explicitly turned off. Stdlib only.
"""

import datetime
import json
import os
import pathlib
import sys

DEFAULT_TURN_THRESHOLD = 5
DEFAULT_PENDING_THRESHOLD = 8
TRANSCRIPT_MAX_LINES = 20
MIN_PROMPT_LEN = 8
SESSION_FALLBACK = "no-session"


def _resolve_kng_home() -> pathlib.Path:
    env = os.environ.get("KNG_HOME")
    if env:
        return pathlib.Path(env)
    return pathlib.Path.home() / ".kng-plugin"


def _load_config(kng_home: pathlib.Path) -> dict:
    cfg_path = kng_home / "kng.config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _ensure_cache_dir(kng_home: pathlib.Path) -> pathlib.Path:
    cache = kng_home / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _read_state(state_path: pathlib.Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state_path: pathlib.Path, state: dict) -> None:
    try:
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _append_transcript(transcript_path: pathlib.Path, prompt: str) -> None:
    """Append the prompt to the rolling transcript, keeping only the most
    recent TRANSCRIPT_MAX_LINES lines."""
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "role": "user",
        "content": prompt,
    }
    line = json.dumps(entry, ensure_ascii=False)

    existing = []
    if transcript_path.exists():
        try:
            existing = transcript_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            existing = []
    existing.append(line)
    if len(existing) > TRANSCRIPT_MAX_LINES:
        existing = existing[-TRANSCRIPT_MAX_LINES:]
    try:
        transcript_path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except OSError:
        pass


def _build_directive(kng_home: pathlib.Path, transcript_path: pathlib.Path) -> str:
    """Build the additionalContext directive that asks the main assistant
    to spawn an extraction subagent."""
    pending_path = kng_home / "cache" / "pending-feedback.jsonl"
    return (
        "📝 KNG 自动学习触发（已达对话轮次阈值）。\n"
        "请用 Agent 工具启动一个反馈提取 subagent，**不要自己提取**——目的是不污染当前主对话上下文。\n\n"
        "推荐参数：\n"
        '  subagent_type: "general-purpose"\n'
        '  description: "Extract KNG feedback candidates"\n'
        "  prompt:\n"
        "    你是 KNG 自动学习的反馈提取 subagent。任务步骤：\n"
        f"    1. Read 文件 `{transcript_path}`，里面是当前会话最近的 user prompt（JSONL，每行一条）。\n"
        "    2. 按以下 4 类模式抽取候选反馈：\n"
        "       - correction: 用户对助手输出的明确纠正（如\"不对\"、\"应该是 X 而不是 Y\"）\n"
        "       - missed: 用户主动指出的漏点 / 漏测场景 / 漏考虑的需求\n"
        "       - constraint: 用户提到的硬约束、边界条件、不变量\n"
        "       - confirmation: 用户对非显然判断的明确确认（如\"对，就用这个方案\"）\n"
        "    3. 每条候选追加为一行 JSON 写入 "
        f"`{pending_path}`（追加模式，每行一条 JSON，"
        '字段: ts, session, type, content, context_snippet）。如果文件不存在，先创建。\n'
        "    4. 仅返回一行简短确认：'已提取 N 条候选反馈写入 pending'。**不要展开候选详情**——主助手不需要看，会在用户跑 /kng-evolve 时审核。\n"
        "    5. 如果 transcript 里没有可抽取的候选（例如全是问答型对话），返回 '本轮无新候选'。\n\n"
        "启动 subagent 后，简短告知用户一句话即可（如 '已触发自动学习'），然后继续响应用户当前请求。"
    )


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt = input_data.get("prompt", "").strip()
    if len(prompt) < MIN_PROMPT_LEN:
        sys.exit(0)

    session_id = input_data.get("session_id") or SESSION_FALLBACK

    kng_home = _resolve_kng_home()
    config = _load_config(kng_home)

    auto_cfg = config.get("auto_evolve", {})
    if auto_cfg.get("enabled") is False:
        sys.exit(0)
    turn_threshold = int(auto_cfg.get("turn_threshold", DEFAULT_TURN_THRESHOLD))

    cache = _ensure_cache_dir(kng_home)
    state_path = cache / "turn-state.json"
    transcript_path = cache / f"transcript-{session_id}.jsonl"

    state = _read_state(state_path)
    session_state = state.get(session_id, {"turn_count": 0, "last_extract_turn": 0})
    session_state["turn_count"] = int(session_state.get("turn_count", 0)) + 1

    _append_transcript(transcript_path, prompt)

    should_trigger = (
        session_state["turn_count"] - int(session_state.get("last_extract_turn", 0))
        >= turn_threshold
    )

    if should_trigger:
        session_state["last_extract_turn"] = session_state["turn_count"]

    state[session_id] = session_state
    _write_state(state_path, state)

    if not should_trigger:
        sys.exit(0)

    directive = _build_directive(kng_home, transcript_path)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": directive,
        }
    }
    sys.stdout.buffer.write(
        (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8")
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
