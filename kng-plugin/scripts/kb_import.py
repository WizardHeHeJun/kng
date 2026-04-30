#!/usr/bin/env python3
"""Bulk import flat KB files into KNG SQLite database.

Imports skill-registry.yaml, synonym-aliases.yaml, project-modules.yaml,
and all KB markdown files into the database.

Usage:
    python kb_import.py \
        --db ./kng.db \
        --capability-dir ./kng-plugin/kb/capability \
        --project-dir ./kb/projects/demo-game \
        --project-id demo-game
"""
import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from db import KngDatabase
from retrieve_kb import (
    parse_simple_yaml,
    parse_simple_yaml_modules,
    parse_synonym_yaml,
    read_kb_files,
)


def extract_title(content: str, fallback: str) -> str:
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def classify_entry_type(filename: str, content: str) -> str:
    name = filename.lower()
    head = content[:500]
    if "可调用技能" in head or "## 触发条件" in head:
        return "skill"
    # Numbered methodology files (e.g. "01-四阶段工作流.md") are guidelines
    import re as _re
    if _re.match(r"^\d{2}-", filename):
        return "guideline"
    if "bug-pattern" in name or "defect" in name or "缺陷" in head:
        return "issue"
    if "playbook" in name or "脚本" in head:
        return "playbook"
    if "guideline" in name or "规范" in head:
        return "guideline"
    if "constraint" in name or "约束" in head:
        return "guideline"
    if "architecture" in name or "架构" in head:
        return "architecture"
    if "test-point" in name or "测试点" in head:
        return "test_point"
    if "requirement" in name or "需求" in head:
        return "requirement"
    return "general"


def parse_metadata_comments(content: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for match in re.finditer(r"<!--\s*(\w+):\s*(.+?)\s*-->", content):
        key, value = match.group(1), match.group(2)
        if key == "related_modules":
            metadata[key] = [m.strip() for m in value.split(",")]
        else:
            metadata[key] = value
    return metadata


def detect_module_from_filename(filename: str) -> str:
    skip_prefixes = {"bug", "test", "project", "skill", "api", "data", "config", "readme"}
    stem = pathlib.Path(filename).stem
    if "-" in stem:
        prefix = stem.split("-")[0]
        if (len(prefix) >= 3 and prefix.isascii() and prefix.isalpha()
                and prefix not in skip_prefixes):
            return prefix
    return ""


def import_capability(db: KngDatabase, capability_dir: pathlib.Path,
                      force: bool = False, verbose: bool = False) -> Dict[str, int]:
    stats = {"skills": 0, "scenarios": 0, "synonyms": 0, "kb_entries": 0}

    registry_path = capability_dir / "skill-registry.yaml"
    if registry_path.exists():
        registry = parse_simple_yaml(registry_path.read_text(encoding="utf-8"))
        for skill in registry.get("skills", []):
            db.upsert_skill(
                skill.get("id", ""), skill.get("name", ""),
                skill.get("file", ""), skill.get("tags", []),
                skill.get("covers", []),
                when_to_use=skill.get("when_to_use", ""),
                input_spec=skill.get("input", ""),
                output_spec=skill.get("output", ""),
            )
            stats["skills"] += 1
        for scenario in registry.get("scenarios", []):
            db.insert_scenario(
                scenario.get("name", ""), scenario.get("description", ""),
                scenario.get("required_skills", []),
                scenario.get("extra_tags", []),
                scenario.get("test_focus", []),
            )
            stats["scenarios"] += 1
        if verbose:
            print(f"  skill-registry.yaml: {stats['skills']} skills, {stats['scenarios']} scenarios")

    synonym_path = capability_dir / "synonym-aliases.yaml"
    if synonym_path.exists():
        syn_map = parse_synonym_yaml(synonym_path.read_text(encoding="utf-8"))
        seen_groups: Dict[frozenset, str] = {}
        for term, term_set in syn_map.items():
            key = frozenset(term_set)
            if key not in seen_groups:
                group_name = f"group_{len(seen_groups)}"
                for t in term_set:
                    if t.isascii() and t.isalpha():
                        group_name = t
                        break
                seen_groups[key] = group_name
                db.upsert_synonym_group(group_name, list(term_set))
                stats["synonyms"] += len(term_set)
        if verbose:
            print(f"  synonym-aliases.yaml: {len(seen_groups)} groups, {stats['synonyms']} terms")

    cap_files = read_kb_files(capability_dir)
    for path, content in cap_files:
        source = str(path)
        if not force and db.entry_exists_by_source(source):
            continue
        title = extract_title(content, path.stem)
        entry_type = classify_entry_type(path.name, content)
        db.insert_kb_entry(
            title=title, content=content, kb_type="capability",
            source_file=source, entry_type=entry_type,
        )
        stats["kb_entries"] += 1
        if verbose:
            print(f"  KB: {path.name} -> {entry_type}")

    return stats


def import_project(db: KngDatabase, project_dir: pathlib.Path,
                   project_id: str, force: bool = False,
                   verbose: bool = False) -> Dict[str, int]:
    stats = {"modules": 0, "relations": 0, "kb_entries": 0}

    db.upsert_project(project_id, project_id, "",
                      str(project_dir.parent), "./test-output")

    modules_path = project_dir / "project-modules.yaml"
    if modules_path.exists():
        pm = parse_simple_yaml_modules(modules_path.read_text(encoding="utf-8"))
        for mod in pm.get("modules", []):
            db.upsert_module(
                project_id, mod.get("id", ""), mod.get("name", ""),
                mod.get("description", ""), mod.get("tags", []),
            )
            stats["modules"] += 1
        for rel in pm.get("relations", []):
            db.upsert_relation(
                project_id, rel.get("from", ""), rel.get("to", ""),
                rel.get("type", "depends_on"), rel.get("risk_level", "medium"),
                rel.get("test_focus", []), rel.get("description", ""),
            )
            stats["relations"] += 1
        if verbose:
            print(f"  project-modules.yaml: {stats['modules']} modules, {stats['relations']} relations")

    proj_files = read_kb_files(project_dir)
    for path, content in proj_files:
        source = str(path)
        if not force and db.entry_exists_by_source(source):
            continue
        title = extract_title(content, path.stem)
        module_id = detect_module_from_filename(path.name)
        metadata = parse_metadata_comments(content)
        entry_type = classify_entry_type(path.name, content)
        db.insert_kb_entry(
            title=title, content=content, kb_type="project",
            project_id=project_id,
            module_id=module_id or metadata.get("module", ""),
            source_url=metadata.get("source", ""),
            source_file=source, entry_type=entry_type,
            related_modules=metadata.get("related_modules", []),
        )
        stats["kb_entries"] += 1
        if verbose:
            print(f"  KB: {path.name} -> module={module_id or '(none)'}, type={entry_type}")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Import flat KB files into KNG SQLite database")
    parser.add_argument("--db", required=True, help="SQLite database file path")
    parser.add_argument("--capability-dir", help="Path to capability KB directory")
    parser.add_argument("--project-dir", help="Path to project KB directory")
    parser.add_argument("--project-id", help="Project ID (required with --project-dir)")
    parser.add_argument("--force", action="store_true", help="Re-import even if source already exists")
    parser.add_argument("--verbose", action="store_true", help="Print each imported file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported")
    args = parser.parse_args()

    if args.project_dir and not args.project_id:
        parser.error("--project-id is required when --project-dir is specified")

    if args.dry_run:
        if args.capability_dir:
            cap = pathlib.Path(args.capability_dir)
            files = read_kb_files(cap)
            print(f"Capability KB: {len(files)} files to import")
            for p, _ in files:
                print(f"  {p.name}")
        if args.project_dir:
            proj = pathlib.Path(args.project_dir)
            files = read_kb_files(proj)
            print(f"Project KB ({args.project_id}): {len(files)} files to import")
            for p, _ in files:
                print(f"  {p.name}")
        return 0

    db = KngDatabase(args.db)
    db.connect()
    db.initialize()

    total_stats: Dict[str, int] = {}

    if args.capability_dir:
        cap_dir = pathlib.Path(args.capability_dir)
        print(f"Importing capability KB from {cap_dir}...")
        cap_stats = import_capability(db, cap_dir, force=args.force, verbose=args.verbose)
        total_stats.update({f"cap_{k}": v for k, v in cap_stats.items()})

    if args.project_dir:
        proj_dir = pathlib.Path(args.project_dir)
        print(f"Importing project KB '{args.project_id}' from {proj_dir}...")
        proj_stats = import_project(db, proj_dir, args.project_id,
                                     force=args.force, verbose=args.verbose)
        total_stats.update({f"proj_{k}": v for k, v in proj_stats.items()})

    db.close()

    print("\nImport complete:")
    print(json.dumps(total_stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
