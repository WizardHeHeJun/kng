#!/usr/bin/env python3
"""Knowledge base retrieval script for kng plugin.

Standalone CLI — uses only Python stdlib. No external dependencies.

Two retrieval modes:
1. Keyword matching: scores KB files by keyword overlap with query
2. Registry-aware routing: reads skill-registry.yaml to identify which
   skill combination a scenario requires, boosting relevant files

Usage:
    python retrieve_kb.py \
        --query "战斗结算 并发 幂等" \
        --capability-dir /path/to/capability \
        --project-dir /path/to/project-kb \
        --top-k 5

    echo "doc text" | python retrieve_kb.py \
        --query-file /dev/stdin \
        --capability-dir /path/to/capability \
        --project-dir /path/to/project-kb
"""
import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Set, Tuple


def normalize_text(text: str) -> str:
    return re.sub(r"[^\w一-鿿]+", " ", text.lower())


def extract_keywords(text: str) -> Set[str]:
    return {t for t in normalize_text(text).split() if len(t) >= 2}


def read_kb_files(root: pathlib.Path) -> List[Tuple[pathlib.Path, str]]:
    if not root.exists():
        return []
    exts = {".md", ".txt", ".json", ".yaml", ".yml"}
    pairs: List[Tuple[pathlib.Path, str]] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            try:
                pairs.append((p, p.read_text(encoding="utf-8")))
            except Exception:
                continue
    return pairs


def load_registry(capability_dir: pathlib.Path) -> Dict[str, Any]:
    """Load skill-registry.yaml if it exists. Pure-stdlib YAML subset parser."""
    reg_path = capability_dir / "skill-registry.yaml"
    if not reg_path.exists():
        return {}
    try:
        content = reg_path.read_text(encoding="utf-8")
        return parse_simple_yaml(content)
    except Exception:
        return {}


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Minimal YAML parser for the registry format. Handles the subset we need."""
    import ast

    result: Dict[str, Any] = {"skills": [], "scenarios": []}
    current_list_key = None
    current_item: Dict[str, Any] = {}
    indent_stack: List[int] = []

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        if stripped.startswith("skills:"):
            current_list_key = "skills"
            current_item = {}
            indent_stack = [indent]
            continue
        if stripped.startswith("scenarios:"):
            current_list_key = "scenarios"
            current_item = {}
            indent_stack = [indent]
            continue

        if current_list_key is None:
            continue

        if stripped.startswith("- ") and ":" in stripped:
            if current_item:
                result[current_list_key].append(current_item)
            current_item = {}
            stripped = stripped[2:]

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().lstrip("- ")
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [s.strip().strip("'\"") for s in val[1:-1].split(",") if s.strip()]
                current_item[key] = items
            elif val:
                current_item[key] = val
        elif stripped.startswith("- "):
            val = stripped[2:].strip()
            last_key = list(current_item.keys())[-1] if current_item else None
            if last_key and isinstance(current_item.get(last_key), list):
                current_item[last_key].append(val)
            elif last_key and isinstance(current_item.get(last_key), str) and not current_item[last_key]:
                current_item[last_key] = [val]

    if current_item and current_list_key:
        result[current_list_key].append(current_item)

    return result


def match_scenarios(query_keywords: Set[str], registry: Dict[str, Any]) -> Dict[str, float]:
    """Match query against registry scenarios, return file->boost_score mapping."""
    boosts: Dict[str, float] = {}
    scenarios = registry.get("scenarios", [])
    skills_index = {s.get("id", ""): s for s in registry.get("skills", [])}

    for scenario in scenarios:
        scenario_tags = set(scenario.get("extra_tags", []))
        scenario_tags.update(extract_keywords(scenario.get("name", "")))
        scenario_tags.update(extract_keywords(scenario.get("description", "")))
        for focus in scenario.get("test_focus", []):
            scenario_tags.update(extract_keywords(focus))

        overlap = len(query_keywords & scenario_tags)
        if overlap < 2:
            continue

        boost = overlap * 3
        for skill_id in scenario.get("required_skills", []):
            skill = skills_index.get(skill_id, {})
            skill_file = skill.get("file", "")
            if skill_file:
                boosts[skill_file] = boosts.get(skill_file, 0) + boost

    for skill in registry.get("skills", []):
        skill_tags = set(skill.get("tags", []))
        for cover in skill.get("covers", []):
            skill_tags.update(extract_keywords(cover))
        overlap = len(query_keywords & skill_tags)
        if overlap > 0:
            skill_file = skill.get("file", "")
            if skill_file:
                boosts[skill_file] = boosts.get(skill_file, 0) + overlap * 2

    return boosts


def load_project_modules(project_dir: pathlib.Path) -> Dict[str, Any]:
    """Load project-modules.yaml if it exists."""
    mod_path = project_dir / "project-modules.yaml"
    if not mod_path.exists():
        return {}
    try:
        content = mod_path.read_text(encoding="utf-8")
        return parse_simple_yaml_modules(content)
    except Exception:
        return {}


def parse_simple_yaml_modules(text: str) -> Dict[str, Any]:
    """Minimal YAML parser for project-modules.yaml format (modules + relations)."""
    result: Dict[str, Any] = {
        "modules": [], "relations": [],
        "auto_detect": True, "fallback_module": "general",
    }
    current_item: Dict[str, Any] = {}
    current_section = None  # "modules" or "relations"

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("auto_detect:"):
            val = stripped.partition(":")[2].strip()
            result["auto_detect"] = val.lower() == "true"
            continue

        if stripped.startswith("fallback_module:"):
            result["fallback_module"] = stripped.partition(":")[2].strip()
            continue

        if stripped.startswith("modules:"):
            if current_item and current_section:
                result[current_section].append(current_item)
            current_section = "modules"
            current_item = {}
            continue

        if stripped.startswith("relations:"):
            if current_item and current_section:
                result[current_section].append(current_item)
            current_section = "relations"
            current_item = {}
            continue

        if current_section is None:
            continue

        if stripped.startswith("- ") and ":" in stripped:
            if current_item:
                result[current_section].append(current_item)
            current_item = {}
            stripped = stripped[2:]

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().lstrip("- ")
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [s.strip().strip("'\"") for s in val[1:-1].split(",") if s.strip()]
                current_item[key] = items
            elif val:
                current_item[key] = val
        elif stripped.startswith("- "):
            val = stripped[2:].strip()
            last_key = list(current_item.keys())[-1] if current_item else None
            if last_key and isinstance(current_item.get(last_key), list):
                current_item[last_key].append(val)

    if current_item and current_section:
        result[current_section].append(current_item)

    return result


def detect_module(query_keywords: Set[str], project_modules: Dict[str, Any],
                  raw_query: str = "") -> Tuple[str, str, float]:
    """Detect which project module best matches the query. Returns (module_id, module_name, score).

    Uses both keyword set intersection AND substring matching for Chinese text
    (which lacks word boundaries).
    """
    if not project_modules.get("modules"):
        return ("general", "通用", 0.0)

    best_id = project_modules.get("fallback_module", "general")
    best_name = "通用"
    best_score = 0.0
    normalized_query = normalize_text(raw_query) if raw_query else " ".join(query_keywords)

    for mod in project_modules["modules"]:
        mod_tags = set(mod.get("tags", []))
        mod_tags.update(extract_keywords(mod.get("name", "")))
        mod_tags.update(extract_keywords(mod.get("description", "")))

        score = float(len(query_keywords & mod_tags))

        for tag in mod.get("tags", []):
            if len(tag) >= 2 and tag in normalized_query:
                score += 1.0

        if score > best_score:
            best_score = score
            best_id = mod.get("id", "general")
            best_name = mod.get("name", best_id)

    if best_score < 2:
        return (project_modules.get("fallback_module", "general"), "通用", best_score)

    return (best_id, best_name, best_score)


def find_related_modules(module_id: str, project_modules: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find modules related to the given module via the knowledge graph."""
    related = []
    for rel in project_modules.get("relations", []):
        if rel.get("from") == module_id or rel.get("to") == module_id:
            other_id = rel.get("to") if rel.get("from") == module_id else rel.get("from")
            risk_weight = {"high": 3.0, "medium": 2.0, "low": 1.0}
            related.append({
                "module_id": other_id,
                "relation_type": rel.get("type", ""),
                "description": rel.get("description", ""),
                "risk_level": rel.get("risk_level", "medium"),
                "test_focus": rel.get("test_focus", []),
                "boost": risk_weight.get(rel.get("risk_level", "medium"), 2.0),
            })
    return related


def retrieve_top_k(
    query_text: str,
    docs: List[Tuple[pathlib.Path, str]],
    top_k: int,
    boosts: Dict[str, float] = None,
    module_prefix: str = None,
    module_boost: float = 0.0,
    related_prefixes: Dict[str, float] = None,
) -> List[Dict[str, Any]]:
    qk = extract_keywords(query_text)
    scored: List[Tuple[pathlib.Path, str, float]] = []
    for path, content in docs:
        ck = extract_keywords(content[:12000])
        score = float(len(qk & ck))

        if boosts:
            for filename, boost in boosts.items():
                if path.name == filename:
                    score += boost

        if module_prefix and path.stem.startswith(module_prefix + "-"):
            score += module_boost

        if related_prefixes:
            for prefix, rel_boost in related_prefixes.items():
                if path.stem.startswith(prefix + "-"):
                    score += rel_boost

        if score > 0:
            scored.append((path, content, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    results = []
    for path, content, score in scored[:top_k]:
        results.append({
            "path": path.as_posix(),
            "score": score,
            "snippet": content[:2000],
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="KNG knowledge base retrieval")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Query text to match against")
    group.add_argument("--query-file", help="File containing query text (use /dev/stdin for pipe)")
    parser.add_argument("--capability-dir", required=True, help="Path to capability KB directory")
    parser.add_argument("--project-dir", required=True, help="Path to project KB directory")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top results per KB")
    args = parser.parse_args()

    if args.query:
        query_text = args.query
    else:
        if str(args.query_file) in ("/dev/stdin", "-"):
            query_text = sys.stdin.read()
        else:
            query_text = pathlib.Path(args.query_file).read_text(encoding="utf-8")

    cap_dir = pathlib.Path(args.capability_dir)
    proj_dir = pathlib.Path(args.project_dir)

    registry = load_registry(cap_dir)
    query_kw = extract_keywords(query_text)
    boosts = match_scenarios(query_kw, registry) if registry else {}

    project_modules = load_project_modules(proj_dir)
    mod_id, mod_name, mod_score = detect_module(query_kw, project_modules, raw_query=query_text)
    module_prefix = mod_id if mod_id != "general" and mod_score >= 2 else None
    module_boost = mod_score * 2 if module_prefix else 0.0

    related = find_related_modules(mod_id, project_modules) if module_prefix else []
    related_prefixes = {r["module_id"]: r["boost"] for r in related}

    cap_docs = read_kb_files(cap_dir)
    proj_docs = read_kb_files(proj_dir)

    cap_hits = retrieve_top_k(query_text, cap_docs, args.top_k, boosts)
    proj_hits = retrieve_top_k(query_text, proj_docs, args.top_k,
                               module_prefix=module_prefix, module_boost=module_boost,
                               related_prefixes=related_prefixes)

    matched_scenarios = []
    if registry:
        for scenario in registry.get("scenarios", []):
            stags = set(scenario.get("extra_tags", []))
            stags.update(extract_keywords(scenario.get("name", "")))
            if len(query_kw & stags) >= 2:
                matched_scenarios.append({
                    "name": scenario.get("name", ""),
                    "required_skills": scenario.get("required_skills", []),
                    "test_focus": scenario.get("test_focus", []),
                })

    output = {
        "capability_hits": cap_hits,
        "project_hits": proj_hits,
        "matched_scenarios": matched_scenarios,
        "detected_module": {
            "id": mod_id,
            "name": mod_name,
            "score": mod_score,
        },
        "related_modules": [
            {
                "module_id": r["module_id"],
                "relation_type": r["relation_type"],
                "description": r["description"],
                "risk_level": r["risk_level"],
                "test_focus": r["test_focus"],
            }
            for r in related
        ],
        "stats": {
            "capability_files": len(cap_docs),
            "project_files": len(proj_docs),
            "query_keywords": len(query_kw),
            "registry_boosts": len(boosts),
            "module_boost_applied": module_prefix is not None,
            "related_modules_boosted": len(related_prefixes),
        },
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
