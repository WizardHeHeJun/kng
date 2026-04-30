#!/usr/bin/env python3
"""Auto-generate skill-registry.yaml from capability skill files.

Scans capability/*.md for callable skills (identified by "可调用技能" or
"## 触发条件" markers), extracts metadata from markdown sections, and
writes skill-registry.yaml.

Existing scenarios in skill-registry.yaml are preserved — only the skills
section is regenerated.

Usage:
    python generate_registry.py <capability_dir>
    python generate_registry.py /path/to/kb/capability --verbose
"""
import argparse
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple


STOP_WORDS = frozenset(
    "的 了 在 是 和 或 与 等 如 当 为 被 到 从 用 对 可以 进行 "
    "需要 可能 以及 包括 通过 使用 例如 比如 不同 描述 内容 "
    "以下 时候 相关 涉及 明确 这个 那个 其中 之间".split()
)


def is_callable_skill(content: str) -> bool:
    head = content[:500]
    return "可调用技能" in head or "## 触发条件" in head


def extract_title(content: str) -> str:
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""


def extract_description(content: str) -> str:
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("> 可调用技能"):
            desc = line.partition("：")[2] or line.partition(":")[2]
            return desc.strip()
    return ""


def extract_section(content: str, heading: str) -> str:
    lines = content.split("\n")
    capturing = False
    section_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and heading in stripped:
            capturing = True
            continue
        if capturing and stripped.startswith("## "):
            break
        if capturing:
            section_lines.append(line)
    return "\n".join(section_lines).strip()


def extract_list_items(section_text: str) -> List[str]:
    items = []
    for line in section_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            text = stripped[2:].strip()
            text = re.sub(r"^\[[ x]\]\s*", "", text)
            if text:
                items.append(text)
    return items


def extract_output_spec(section_text: str) -> str:
    id_match = re.search(r"TP-([A-Z]+)-", section_text)
    type_match = re.search(r'[`"\']?type[`"\']?\s*[:：]\s*[`"\']?(\w+)', section_text)
    if id_match and type_match:
        prefix = id_match.group(1)
        type_val = type_match.group(1)
        return f"测试点（type={type_val}, id=TP-{prefix}-xxx）"
    if id_match:
        prefix = id_match.group(1)
        return f"测试点（id=TP-{prefix}-xxx）"
    return "测试点"


def extract_tags(trigger_text: str, description: str, name: str) -> List[str]:
    seen: set = set()
    tags: List[str] = []

    def add(tag: str) -> None:
        tag = tag.strip("：:。.、，,")
        if len(tag) < 2 or tag in seen:
            return
        seen.add(tag)
        tags.append(tag)

    add(name)

    for line in trigger_text.split("\n"):
        stripped = line.strip().lstrip("- ")
        if not stripped:
            continue
        core = re.split(r"[（(]", stripped)[0].strip()
        core = re.sub(r"^(当策划案|此技能|本技能).*", "", core)
        core = re.sub(r"^(明确的|具体的)\s*", "", core)
        if 2 <= len(core) <= 12:
            add(core)
        elif len(core) > 12:
            parts = re.split(r"[、/，,]", core)
            for p in parts:
                p = p.strip()
                if 2 <= len(p) <= 12:
                    add(p)

    desc_keywords = re.split(r"[，、。,.]", description)
    for kw in desc_keywords:
        kw = kw.strip()
        if 2 <= len(kw) <= 8:
            add(kw)

    return tags[:12]


def extract_covers(checklist_text: str) -> List[str]:
    items = extract_list_items(checklist_text)
    covers = []
    for item in items:
        clean = re.sub(r"至少覆盖\s*", "", item)
        clean = re.sub(r"^\d+\s*(条|个|种)\s*", "", clean)
        clean = clean.strip("。.")
        if clean:
            covers.append(clean)
    return covers


def parse_skill_file(filepath: pathlib.Path) -> Optional[Dict]:
    content = filepath.read_text(encoding="utf-8")
    if not is_callable_skill(content):
        return None

    skill_id = filepath.stem
    filename = filepath.name
    name = extract_title(content) or skill_id
    description = extract_description(content)

    trigger_section = extract_section(content, "触发条件")
    input_section = extract_section(content, "输入")
    output_section = extract_section(content, "输出规范")
    checklist_section = extract_section(content, "质量检查")

    trigger_items = extract_list_items(trigger_section)
    when_to_use = "、".join(trigger_items) if trigger_items else ""

    input_items = extract_list_items(input_section)
    input_spec = "、".join(input_items) if input_items else ""

    output_spec = extract_output_spec(output_section)
    tags = extract_tags(trigger_section, description, name)
    covers = extract_covers(checklist_section)

    return {
        "id": skill_id,
        "file": filename,
        "name": name,
        "when_to_use": when_to_use,
        "input": input_spec,
        "output": output_spec,
        "tags": tags,
        "covers": covers,
    }


def load_existing_scenarios(registry_path: pathlib.Path) -> str:
    if not registry_path.exists():
        return ""
    content = registry_path.read_text(encoding="utf-8")
    match = re.search(r"^(# 场景组合模板.*)", content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"^(scenarios:.*)", content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1)
    return ""


def yaml_escape(s: str) -> str:
    if not s:
        return '""'
    if any(c in s for c in ":{}[]&*?|>!%@`#,"):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def format_yaml_list(items: List[str]) -> str:
    if not items:
        return "[]"
    escaped = [yaml_escape(item) for item in items]
    inline = "[" + ", ".join(escaped) + "]"
    if len(inline) <= 80:
        return inline
    lines = "\n".join(f"      - {yaml_escape(item)}" for item in items)
    return "\n" + lines


def generate_yaml(skills: List[Dict], existing_scenarios: str) -> str:
    lines = [
        "# Skill Registry — 能力库可调用技能索引",
        "# 由 generate_registry.py 从 capability/*.md 自动生成",
        "# retrieve_kb.py 和 /kng-test 会读取此文件进行技能路由和选择",
        "",
        "skills:",
    ]

    for i, skill in enumerate(skills):
        lines.append(f"  - id: {skill['id']}")
        lines.append(f"    file: {skill['file']}")
        lines.append(f"    name: {skill['name']}")
        lines.append(f"    when_to_use: {yaml_escape(skill['when_to_use'])}")
        lines.append(f"    input: {yaml_escape(skill['input'])}")
        lines.append(f"    output: {yaml_escape(skill['output'])}")
        lines.append(f"    tags: {format_yaml_list(skill['tags'])}")
        covers_inline = "[" + ", ".join(yaml_escape(c) for c in skill["covers"]) + "]"
        lines.append(f"    covers: {covers_inline}")
        if i < len(skills) - 1:
            lines.append("")

    lines.append("")

    if existing_scenarios:
        lines.append(existing_scenarios)
    else:
        lines.append("# 场景组合模板 — 描述常见测试场景需要哪些 skill 组合")
        lines.append("# 由 /kng-evolve 在使用过程中逐步积累")
        lines.append("scenarios: []")

    return "\n".join(lines) + "\n"


def scan_and_generate(capability_dir: pathlib.Path, verbose: bool = False) -> Tuple[List[Dict], str]:
    md_files = sorted(capability_dir.glob("*.md"))
    skills = []
    for f in md_files:
        skill = parse_skill_file(f)
        if skill:
            skills.append(skill)
            if verbose:
                print(f"  [skill] {f.name} -> id={skill['id']}, tags={skill['tags']}")
        elif verbose:
            print(f"  [skip]  {f.name}")

    registry_path = capability_dir / "skill-registry.yaml"
    existing_scenarios = load_existing_scenarios(registry_path)

    yaml_content = generate_yaml(skills, existing_scenarios)
    return skills, yaml_content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-generate skill-registry.yaml from capability skill files"
    )
    parser.add_argument("capability_dir", help="Path to capability KB directory")
    parser.add_argument("--verbose", action="store_true", help="Print each scanned file")
    parser.add_argument("--dry-run", action="store_true", help="Print YAML to stdout instead of writing")
    args = parser.parse_args()

    capability_dir = pathlib.Path(args.capability_dir)
    if not capability_dir.is_dir():
        print(f"Error: {capability_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"Scanning {capability_dir} for callable skills...")
    skills, yaml_content = scan_and_generate(capability_dir, verbose=args.verbose)
    print(f"Found {len(skills)} callable skills")

    if args.dry_run:
        print("\n--- Generated skill-registry.yaml ---")
        print(yaml_content)
        return 0

    output_path = capability_dir / "skill-registry.yaml"
    output_path.write_text(yaml_content, encoding="utf-8")
    print(f"Written to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
