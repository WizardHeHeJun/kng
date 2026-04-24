#!/usr/bin/env python3
import pathlib
import re
from typing import List, Tuple


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w一-鿿]+", " ", text)
    return text


def keywords(text: str) -> set:
    base = normalize_text(text)
    return {t for t in base.split() if len(t) >= 2}


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


def retrieve_top_k(
    query_text: str, docs: List[Tuple[pathlib.Path, str]], top_k: int
) -> List[Tuple[pathlib.Path, str, int]]:
    qk = keywords(query_text)
    scored: List[Tuple[pathlib.Path, str, int]] = []
    for path, content in docs:
        ck = keywords(content[:12000])
        score = len(qk.intersection(ck))
        if score > 0:
            scored.append((path, content, score))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k]


def render_context_block(items: List[Tuple[pathlib.Path, str, int]], tag: str) -> str:
    lines: List[str] = [f"## {tag}"]
    if not items:
        lines.append("(empty)")
        return "\n".join(lines)
    for path, content, score in items:
        snippet = content[:1800]
        lines.append(f"\n### {path.as_posix()} (score={score})\n{snippet}")
    return "\n".join(lines)
