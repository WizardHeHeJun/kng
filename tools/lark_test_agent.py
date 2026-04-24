#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys

from lib.lark_client import fetch_lark_doc
from lib.llm_client import generate_by_openai, fallback_generate
from lib.output import save_outputs


SYSTEM_PROMPT = """你是资深测试工程师。请根据输入文档输出结构化测试设计，必须是合法 JSON。
JSON 结构：
{
  "feature_name": "字符串",
  "test_points": [{"id":"TP-001","title":"字符串","type":"functional|boundary|exception|state|permission|compatibility"}],
  "test_cases": [{
    "id":"TC-001",
    "title":"字符串",
    "preconditions":["字符串"],
    "steps":["字符串"],
    "expected":"字符串",
    "priority":"P0|P1|P2",
    "related_points":["TP-001"]
  }],
  "risks":[{"level":"high|medium|low","item":"字符串","reason":"字符串"}],
  "clarifications":["字符串"]
}
要求：
1) 覆盖正向、反向、边界、异常流程
2) 每个 test_case 必须可执行、可验证
3) 只输出 JSON，不输出解释性文本"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从飞书文档拉取内容并生成测试设计产出。"
    )
    parser.add_argument("--url", required=True, help="飞书文档 URL")
    parser.add_argument(
        "--identity", default="user", choices=["user", "bot"],
        help="lark-cli 调用身份，默认 user",
    )
    parser.add_argument("--output-dir", default="test-output", help="输出目录，默认 test-output")
    parser.add_argument("--model", default="gpt-4.1-mini", help="使用 OpenAI 时的模型名，默认 gpt-4.1-mini")
    args = parser.parse_args()

    doc_content = fetch_lark_doc(args.url, args.identity)

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"以下是需求/设计文档内容：\n\n{doc_content[:120000]}"
    )

    try:
        test_design = generate_by_openai(prompt, args.model)
        gen_mode = "openai"
    except Exception as e:
        test_design = fallback_generate(doc_content)
        test_design["clarifications"].append(f"自动降级原因：{e}")
        gen_mode = "fallback"

    paths = save_outputs(
        output_dir=pathlib.Path(args.output_dir),
        doc_url=args.url,
        doc_content=doc_content,
        design=test_design,
    )

    print(
        json.dumps(
            {"status": "ok", "mode": gen_mode, "outputs": paths},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
