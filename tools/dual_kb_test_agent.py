#!/usr/bin/env python3
import argparse
import json
import pathlib

from lib.lark_client import fetch_lark_doc
from lib.llm_client import generate_by_openai, fallback_generate
from lib.retrieval import read_kb_files, retrieve_top_k, render_context_block
from lib.output import save_outputs


SYSTEM_PROMPT = """你是游戏测试架构助手。你会同时参考两类知识：
1) 基础能力知识库（测试方法、脚本规范、质量门禁）
2) 项目知识库（玩法、系统、接口、历史缺陷、项目约束）

请输出合法 JSON，结构如下：
{
  "feature_name":"字符串",
  "test_points":[{"id":"TP-001","title":"字符串","type":"functional|boundary|exception|state|permission|compatibility"}],
  "test_cases":[{"id":"TC-001","title":"字符串","preconditions":["字符串"],"steps":["字符串"],"expected":"字符串","priority":"P0|P1|P2","related_points":["TP-001"]}],
  "risks":[{"level":"high|medium|low","item":"字符串","reason":"字符串"}],
  "clarifications":["字符串"],
  "source_refs":[{"source_type":"capability|project|document","path":"字符串","note":"字符串"}]
}

要求：
1. 用例必须能执行并可验收
2. 明确标记高风险场景
3. 至少给出 4 个测试点、4 个测试用例
4. 必须输出 source_refs
5. 只输出 JSON，不要解释文本"""


def main() -> int:
    parser = argparse.ArgumentParser(description="双知识库测试产出工具（基础库 + 项目库）。")
    parser.add_argument("--url", required=True, help="飞书文档 URL")
    parser.add_argument("--project-id", required=True, help="项目标识，例如 demo-game")
    parser.add_argument("--identity", default="user", choices=["user", "bot"], help="lark-cli 身份")
    parser.add_argument("--kb-root", default="kb", help="知识库根目录")
    parser.add_argument("--top-k", type=int, default=5, help="每个知识库检索条数")
    parser.add_argument("--output-dir", default="test-output", help="输出目录")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI 模型名")
    args = parser.parse_args()

    kb_root = pathlib.Path(args.kb_root)
    cap_root = kb_root / "capability"
    proj_root = kb_root / "projects" / args.project_id
    if not proj_root.exists():
        raise FileNotFoundError(f"项目知识库不存在：{proj_root.as_posix()}")

    doc_content = fetch_lark_doc(args.url, args.identity)

    cap_hits = retrieve_top_k(doc_content, read_kb_files(cap_root), args.top_k)
    proj_hits = retrieve_top_k(doc_content, read_kb_files(proj_root), args.top_k)

    cap_ctx = render_context_block(cap_hits, "基础能力知识库片段")
    proj_ctx = render_context_block(proj_hits, "项目知识库片段")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"下面是输入文档内容：\n{doc_content[:50000]}\n\n"
        f"{cap_ctx}\n\n"
        f"{proj_ctx}\n"
    )

    try:
        design = generate_by_openai(prompt, args.model)
        mode = "openai-dual-kb"
    except Exception as e:
        design = fallback_generate(doc_content)
        design["source_refs"] = [
            {"source_type": "document", "path": args.url, "note": "fallback 模式"},
        ]
        design["clarifications"].append(f"自动降级原因：{e}")
        mode = "fallback"

    paths = save_outputs(
        output_dir=pathlib.Path(args.output_dir),
        doc_url=args.url,
        doc_content=doc_content,
        design=design,
        project_id=args.project_id,
        cap_hits=cap_hits,
        proj_hits=proj_hits,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "mode": mode,
                "project_id": args.project_id,
                "capability_hits": [p.as_posix() for p, _, _ in cap_hits],
                "project_hits": [p.as_posix() for p, _, _ in proj_hits],
                "outputs": paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
