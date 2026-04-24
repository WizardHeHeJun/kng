#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple


def render_markdown(
    design: Dict[str, Any],
    doc_url: str,
    project_id: Optional[str] = None,
    cap_hits: Optional[List[Tuple[pathlib.Path, str, int]]] = None,
    proj_hits: Optional[List[Tuple[pathlib.Path, str, int]]] = None,
) -> str:
    md_lines = [
        f"# 测试设计：{design.get('feature_name', '未命名需求')}",
        "",
    ]
    if project_id:
        md_lines.append(f"- 项目：{project_id}")
    md_lines.extend([
        f"- 来源文档：{doc_url}",
        f"- 生成时间：{dt.datetime.now().isoformat(timespec='seconds')}",
        "",
    ])

    if cap_hits is not None:
        md_lines.append("## 命中知识（基础能力库）")
        for p, _, s in cap_hits:
            md_lines.append(f"- {p.as_posix()} (score={s})")
        md_lines.append("")

    if proj_hits is not None:
        md_lines.append("## 命中知识（项目库）")
        for p, _, s in proj_hits:
            md_lines.append(f"- {p.as_posix()} (score={s})")
        md_lines.append("")

    md_lines.append("## 测试点")
    for p in design.get("test_points", []):
        md_lines.append(f"- `{p.get('id','')}` [{p.get('type','')}] {p.get('title','')}")

    md_lines.extend(["", "## 测试用例"])
    for c in design.get("test_cases", []):
        md_lines.append(f"- `{c.get('id','')}` {c.get('title','')} ({c.get('priority','')})")
        md_lines.append(f"  - 前置：{'; '.join(c.get('preconditions', []))}")
        md_lines.append(f"  - 步骤：{'; '.join(c.get('steps', []))}")
        md_lines.append(f"  - 预期：{c.get('expected', '')}")

    md_lines.extend(["", "## 风险"])
    for r in design.get("risks", []):
        md_lines.append(f"- [{r.get('level','')}] {r.get('item','')}：{r.get('reason','')}")

    md_lines.extend(["", "## 待确认"])
    for q in design.get("clarifications", []):
        md_lines.append(f"- {q}")

    if "source_refs" in design:
        md_lines.extend(["", "## 引用来源"])
        for ref in design.get("source_refs", []):
            md_lines.append(
                f"- [{ref.get('source_type','')}] {ref.get('path','')} - {ref.get('note','')}"
            )

    return "\n".join(md_lines) + "\n"


def save_outputs(
    output_dir: pathlib.Path,
    doc_url: str,
    doc_content: str,
    design: Dict[str, Any],
    project_id: Optional[str] = None,
    cap_hits: Optional[List[Tuple[pathlib.Path, str, int]]] = None,
    proj_hits: Optional[List[Tuple[pathlib.Path, str, int]]] = None,
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"{stamp}-{project_id}" if project_id else stamp

    source_path = output_dir / f"{prefix}-source.md"
    json_path = output_dir / f"{prefix}-test-design.json"
    md_path = output_dir / f"{prefix}-test-design.md"

    source_path.write_text(doc_content, encoding="utf-8")
    json_path.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(design, doc_url, project_id, cap_hits, proj_hits),
        encoding="utf-8",
    )

    return {"source": str(source_path), "json": str(json_path), "markdown": str(md_path)}
