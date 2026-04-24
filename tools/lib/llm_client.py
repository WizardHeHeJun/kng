#!/usr/bin/env python3
import json
import os
import re
from typing import Any, Dict


def try_parse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("空响应，无法解析 JSON")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def generate_by_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY")
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("缺少 openai 依赖，请先 pip install -r requirements.txt") from e

    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    return try_parse_json(content)


def fallback_generate(doc_content: str) -> Dict[str, Any]:
    title_match = re.search(r"^#\s+(.+)$", doc_content, flags=re.MULTILINE)
    feature_name = title_match.group(1).strip() if title_match else "未命名需求"
    return {
        "feature_name": feature_name,
        "test_points": [
            {"id": "TP-001", "title": "核心功能流程可用", "type": "functional"},
            {"id": "TP-002", "title": "关键字段边界值校验", "type": "boundary"},
            {"id": "TP-003", "title": "异常输入与错误提示", "type": "exception"},
            {"id": "TP-004", "title": "状态流转与重复操作幂等", "type": "state"},
        ],
        "test_cases": [
            {
                "id": "TC-001",
                "title": "主流程成功路径",
                "preconditions": ["已准备有效测试数据"],
                "steps": ["按文档主流程执行关键步骤"],
                "expected": "流程成功结束，结果与文档一致",
                "priority": "P0",
                "related_points": ["TP-001"],
            },
            {
                "id": "TC-002",
                "title": "必填字段为空时拦截",
                "preconditions": ["进入功能页面"],
                "steps": ["关键必填字段留空并提交"],
                "expected": "提交失败并提示明确错误信息",
                "priority": "P1",
                "related_points": ["TP-002", "TP-003"],
            },
        ],
        "risks": [
            {"level": "medium", "item": "文档字段约束不完整", "reason": "可能导致边界测试遗漏"},
            {"level": "medium", "item": "异常分支描述不足", "reason": "失败路径预期不明确"},
        ],
        "clarifications": [
            "请确认关键字段取值范围与默认值",
            "请确认失败重试与幂等策略",
        ],
    }
