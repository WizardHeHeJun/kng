#!/usr/bin/env python3
"""SQLite database abstraction layer for KNG knowledge base.

Stdlib-only. No external dependencies.

Usage:
    from db import KngDatabase

    db = KngDatabase("./kng.db")
    db.connect()
    db.initialize()
    # ... CRUD operations ...
    db.close()

CLI:
    python db.py init --db ./kng.db
    python db.py stats --db ./kng.db
"""
import argparse
import json
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    kb_root     TEXT NOT NULL DEFAULT './kb',
    output_dir  TEXT DEFAULT './test-output',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS modules (
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, module_id)
);

CREATE TABLE IF NOT EXISTS module_relations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL,
    from_module  TEXT NOT NULL,
    to_module    TEXT NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('depends_on','feeds_into','shares_state','triggers')),
    risk_level   TEXT DEFAULT 'medium' CHECK (risk_level IN ('high','medium','low')),
    test_focus   TEXT DEFAULT '[]',
    description  TEXT DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id, from_module) REFERENCES modules(project_id, module_id),
    FOREIGN KEY (project_id, to_module) REFERENCES modules(project_id, module_id),
    UNIQUE (project_id, from_module, to_module, type)
);

CREATE TABLE IF NOT EXISTS kb_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT,
    module_id       TEXT,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_url      TEXT DEFAULT '',
    source_file     TEXT DEFAULT '',
    entry_type      TEXT DEFAULT 'general' CHECK (entry_type IN (
                        'requirement','architecture','test_point','issue',
                        'guideline','playbook','general'
                    )),
    tags            TEXT DEFAULT '[]',
    related_modules TEXT DEFAULT '[]',
    kb_type         TEXT NOT NULL CHECK (kb_type IN ('capability','project')),
    imported_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_entries_fts USING fts5(
    title, content, tags,
    content=kb_entries, content_rowid=id,
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS kb_entries_ai AFTER INSERT ON kb_entries BEGIN
    INSERT INTO kb_entries_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS kb_entries_ad AFTER DELETE ON kb_entries BEGIN
    INSERT INTO kb_entries_fts(kb_entries_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS kb_entries_au AFTER UPDATE ON kb_entries BEGIN
    INSERT INTO kb_entries_fts(kb_entries_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO kb_entries_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS skills (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    file        TEXT NOT NULL,
    tags        TEXT DEFAULT '[]',
    covers      TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS skill_scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    required_skills TEXT DEFAULT '[]',
    extra_tags      TEXT DEFAULT '[]',
    test_focus      TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS synonyms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name  TEXT NOT NULL,
    term        TEXT NOT NULL,
    UNIQUE (group_name, term)
);

CREATE TABLE IF NOT EXISTS test_designs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id        TEXT,
    feature_name     TEXT NOT NULL,
    source_url       TEXT DEFAULT '',
    design_json      TEXT NOT NULL,
    test_point_count INTEGER DEFAULT 0,
    test_case_count  INTEGER DEFAULT 0,
    capability_hits  TEXT DEFAULT '[]',
    project_hits     TEXT DEFAULT '[]',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS learning_feedback (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT REFERENCES projects(id),
    module_id        TEXT,
    source_design_id INTEGER,
    feedback_type    TEXT NOT NULL CHECK (feedback_type IN (
                        'missed_scenario','actual_bug','method_improvement',
                        'new_scenario','new_module','relation_update'
                     )),
    content          TEXT NOT NULL,
    routed_to        TEXT DEFAULT '[]',
    applied          INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kb_entries_project ON kb_entries(project_id, kb_type);
CREATE INDEX IF NOT EXISTS idx_kb_entries_module ON kb_entries(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_kb_entries_type ON kb_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_relations_from ON module_relations(project_id, from_module);
CREATE INDEX IF NOT EXISTS idx_relations_to ON module_relations(project_id, to_module);
CREATE INDEX IF NOT EXISTS idx_synonyms_term ON synonyms(term);
CREATE INDEX IF NOT EXISTS idx_test_designs_project ON test_designs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_project ON learning_feedback(project_id, created_at);
"""


def _normalize_text(text: str) -> str:
    return re.sub(r"[^\w一-鿿]+", " ", text.lower())


def _extract_keywords(text: str) -> Set[str]:
    return {t for t in _normalize_text(text).split() if len(t) >= 2}


def _substring_match_score(keywords: Set[str], normalized_text: str) -> float:
    score = 0.0
    for kw in keywords:
        if len(kw) >= 2 and kw in normalized_text:
            score += 0.5
    return score


class KngDatabase:

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def initialize(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(_SCHEMA_SQL)
        existing = cur.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0]
        if existing is None:
            cur.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "initial schema"),
            )
        self.conn.commit()

    # ── Projects ──

    def upsert_project(self, id: str, name: str, description: str = "",
                       kb_root: str = "./kb", output_dir: str = "./test-output") -> None:
        self.conn.execute(
            """INSERT INTO projects (id, name, description, kb_root, output_dir)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, description=excluded.description,
                 kb_root=excluded.kb_root, output_dir=excluded.output_dir,
                 updated_at=datetime('now')""",
            (id, name, description, kb_root, output_dir),
        )
        self.conn.commit()

    def get_project(self, id: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> List[Dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM projects ORDER BY id")]

    def delete_project(self, id: str) -> None:
        self.conn.execute("DELETE FROM projects WHERE id=?", (id,))
        self.conn.commit()

    # ── Modules ──

    def upsert_module(self, project_id: str, module_id: str, name: str,
                      description: str = "", tags: List[str] = None) -> None:
        self.conn.execute(
            """INSERT INTO modules (project_id, module_id, name, description, tags)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(project_id, module_id) DO UPDATE SET
                 name=excluded.name, description=excluded.description,
                 tags=excluded.tags, updated_at=datetime('now')""",
            (project_id, module_id, name, description, json.dumps(tags or [], ensure_ascii=False)),
        )
        self.conn.commit()

    def get_module(self, project_id: str, module_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM modules WHERE project_id=? AND module_id=?",
            (project_id, module_id),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        return d

    def list_modules(self, project_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM modules WHERE project_id=? ORDER BY module_id",
            (project_id,),
        )
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            result.append(d)
        return result

    def delete_module(self, project_id: str, module_id: str) -> None:
        self.conn.execute(
            "DELETE FROM modules WHERE project_id=? AND module_id=?",
            (project_id, module_id),
        )
        self.conn.commit()

    def detect_module(self, query_keywords: Set[str], project_id: str,
                      raw_query: str = "") -> Tuple[str, str, float]:
        modules = self.list_modules(project_id)
        if not modules:
            return ("general", "通用", 0.0)

        best_id, best_name, best_score = "general", "通用", 0.0
        normalized_query = _normalize_text(raw_query) if raw_query else " ".join(query_keywords)

        for mod in modules:
            mod_tags = set(mod["tags"])
            mod_tags.update(_extract_keywords(mod["name"]))
            mod_tags.update(_extract_keywords(mod.get("description", "")))

            score = float(len(query_keywords & mod_tags))
            for tag in mod["tags"]:
                if len(tag) >= 2 and tag in normalized_query:
                    score += 1.0

            if score > best_score:
                best_score = score
                best_id = mod["module_id"]
                best_name = mod["name"]

        if best_score < 2:
            return ("general", "通用", best_score)
        return (best_id, best_name, best_score)

    # ── Module Relations ──

    def upsert_relation(self, project_id: str, from_module: str, to_module: str,
                        rel_type: str, risk_level: str = "medium",
                        test_focus: List[str] = None, description: str = "") -> None:
        self.conn.execute(
            """INSERT INTO module_relations (project_id, from_module, to_module, type,
                                            risk_level, test_focus, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, from_module, to_module, type) DO UPDATE SET
                 risk_level=excluded.risk_level, test_focus=excluded.test_focus,
                 description=excluded.description, updated_at=datetime('now')""",
            (project_id, from_module, to_module, rel_type, risk_level,
             json.dumps(test_focus or [], ensure_ascii=False), description),
        )
        self.conn.commit()

    def find_related_modules(self, project_id: str, module_id: str) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT * FROM module_relations
               WHERE project_id=? AND (from_module=? OR to_module=?)""",
            (project_id, module_id, module_id),
        )
        risk_weight = {"high": 3.0, "medium": 2.0, "low": 1.0}
        related = []
        for r in rows:
            other = r["to_module"] if r["from_module"] == module_id else r["from_module"]
            related.append({
                "module_id": other,
                "relation_type": r["type"],
                "description": r["description"],
                "risk_level": r["risk_level"],
                "test_focus": json.loads(r["test_focus"]),
                "boost": risk_weight.get(r["risk_level"], 2.0),
            })
        return related

    def list_relations(self, project_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM module_relations WHERE project_id=? ORDER BY from_module",
            (project_id,),
        )
        return [dict(r) for r in rows]

    # ── KB Entries ──

    def insert_kb_entry(self, title: str, content: str, kb_type: str,
                        project_id: str = None, module_id: str = None,
                        source_url: str = "", source_file: str = "",
                        entry_type: str = "general", tags: List[str] = None,
                        related_modules: List[str] = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO kb_entries (project_id, module_id, title, content,
                   source_url, source_file, entry_type, tags, related_modules, kb_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, module_id, title, content, source_url, source_file,
             entry_type, json.dumps(tags or [], ensure_ascii=False),
             json.dumps(related_modules or [], ensure_ascii=False), kb_type),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_kb_entry(self, id: int, **kwargs) -> None:
        allowed = {"title", "content", "module_id", "entry_type", "tags",
                    "related_modules", "source_url"}
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k in ("tags", "related_modules"):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            vals.append(v)
        if not sets:
            return
        sets.append("updated_at=datetime('now')")
        vals.append(id)
        self.conn.execute(f"UPDATE kb_entries SET {', '.join(sets)} WHERE id=?", vals)
        self.conn.commit()

    def get_kb_entry(self, id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM kb_entries WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        d["related_modules"] = json.loads(d["related_modules"])
        return d

    def list_kb_entries(self, project_id: str = None, kb_type: str = None,
                        module_id: str = None) -> List[Dict]:
        sql = "SELECT * FROM kb_entries WHERE 1=1"
        params: list = []
        if kb_type:
            sql += " AND kb_type=?"
            params.append(kb_type)
        if project_id:
            sql += " AND project_id=?"
            params.append(project_id)
        elif kb_type == "capability":
            sql += " AND project_id IS NULL"
        if module_id:
            sql += " AND module_id=?"
            params.append(module_id)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params)
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            d["related_modules"] = json.loads(d["related_modules"])
            result.append(d)
        return result

    def delete_kb_entry(self, id: int) -> None:
        self.conn.execute("DELETE FROM kb_entries WHERE id=?", (id,))
        self.conn.commit()

    def entry_exists_by_source(self, source_file: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM kb_entries WHERE source_file=? LIMIT 1", (source_file,)
        ).fetchone()
        return row is not None

    def search_kb_fts(self, query: str, kb_type: str = None,
                      project_id: str = None, top_k: int = 5) -> List[Dict]:
        tokens = _normalize_text(query).split()
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)

        sql = """SELECT kb.id, kb.title, kb.kb_type, kb.project_id, kb.module_id,
                        kb.source_file, kb.entry_type,
                        substr(kb.content, 1, 2000) as snippet,
                        rank
                 FROM kb_entries_fts fts
                 JOIN kb_entries kb ON kb.id = fts.rowid
                 WHERE kb_entries_fts MATCH ?"""
        params: list = [fts_query]

        if kb_type:
            sql += " AND kb.kb_type=?"
            params.append(kb_type)
        if project_id:
            sql += " AND (kb.project_id=? OR kb.project_id IS NULL)"
            params.append(project_id)

        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        results = []
        try:
            for row in self.conn.execute(sql, params):
                results.append({
                    "id": row["id"],
                    "path": row["source_file"] or row["title"],
                    "score": -row["rank"],
                    "snippet": row["snippet"],
                    "module_id": row["module_id"],
                    "entry_type": row["entry_type"],
                })
        except sqlite3.OperationalError:
            pass
        return results

    def search_kb_keyword(self, query_keywords: Set[str], kb_type: str,
                          project_id: str = None, top_k: int = 5,
                          boosts: Dict[str, float] = None,
                          module_prefix: str = None, module_boost: float = 0.0,
                          related_prefixes: Dict[str, float] = None) -> List[Dict]:
        entries = self.list_kb_entries(project_id=project_id, kb_type=kb_type)
        scored: List[Tuple[Dict, float]] = []

        for entry in entries:
            ck = _extract_keywords(entry["content"])
            intersection_count = len(query_keywords & ck)
            query_coverage = intersection_count / max(len(query_keywords), 1)
            score = intersection_count + query_coverage * 2.0

            unmatched = query_keywords - ck
            if unmatched:
                score += _substring_match_score(unmatched, _normalize_text(entry["content"]))

            if boosts:
                src = entry.get("source_file", "")
                for filename, boost in boosts.items():
                    if src.endswith(filename):
                        score += boost

            mid = entry.get("module_id", "") or ""
            if module_prefix and mid == module_prefix:
                score += module_boost

            if related_prefixes and mid:
                for prefix, rel_boost in related_prefixes.items():
                    if mid == prefix:
                        score += rel_boost

            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for entry, score in scored[:top_k]:
            results.append({
                "id": entry["id"],
                "path": entry.get("source_file") or entry["title"],
                "score": round(score, 2),
                "snippet": entry["content"][:2000],
                "module_id": entry.get("module_id"),
                "entry_type": entry.get("entry_type"),
            })
        return results

    # ── Skills ──

    def upsert_skill(self, id: str, name: str, file: str,
                     tags: List[str] = None, covers: List[str] = None) -> None:
        self.conn.execute(
            """INSERT INTO skills (id, name, file, tags, covers)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, file=excluded.file,
                 tags=excluded.tags, covers=excluded.covers,
                 updated_at=datetime('now')""",
            (id, name, file,
             json.dumps(tags or [], ensure_ascii=False),
             json.dumps(covers or [], ensure_ascii=False)),
        )
        self.conn.commit()

    def get_skill(self, id: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM skills WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        d["covers"] = json.loads(d["covers"])
        return d

    def list_skills(self) -> List[Dict]:
        result = []
        for r in self.conn.execute("SELECT * FROM skills ORDER BY id"):
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            d["covers"] = json.loads(d["covers"])
            result.append(d)
        return result

    # ── Skill Scenarios ──

    def insert_scenario(self, name: str, description: str = "",
                        required_skills: List[str] = None,
                        extra_tags: List[str] = None,
                        test_focus: List[str] = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO skill_scenarios (name, description, required_skills, extra_tags, test_focus)
               VALUES (?, ?, ?, ?, ?)""",
            (name, description,
             json.dumps(required_skills or [], ensure_ascii=False),
             json.dumps(extra_tags or [], ensure_ascii=False),
             json.dumps(test_focus or [], ensure_ascii=False)),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_scenarios(self) -> List[Dict]:
        result = []
        for r in self.conn.execute("SELECT * FROM skill_scenarios ORDER BY id"):
            d = dict(r)
            for k in ("required_skills", "extra_tags", "test_focus"):
                d[k] = json.loads(d[k])
            result.append(d)
        return result

    def match_scenarios(self, query_keywords: Set[str],
                        original_keyword_count: int = 0
                        ) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        boosts: Dict[str, float] = {}
        matched: List[Dict[str, Any]] = []
        scenarios = self.list_scenarios()
        skills_index = {s["id"]: s for s in self.list_skills()}

        for scenario in scenarios:
            scenario_tags = set(scenario.get("extra_tags", []))
            scenario_tags.update(_extract_keywords(scenario.get("name", "")))
            scenario_tags.update(_extract_keywords(scenario.get("description", "")))
            for focus in scenario.get("test_focus", []):
                scenario_tags.update(_extract_keywords(focus))

            overlap = len(query_keywords & scenario_tags)
            scenario_text = _normalize_text(
                scenario.get("name", "") + " " +
                scenario.get("description", "") + " " +
                " ".join(scenario.get("extra_tags", [])) + " " +
                " ".join(scenario.get("test_focus", []))
            )
            substr_hits = _substring_match_score(
                query_keywords - scenario_tags, scenario_text
            )
            effective_overlap = overlap + substr_hits

            kw_count = original_keyword_count if original_keyword_count > 0 else len(query_keywords)
            min_overlap = max(1, min(2, kw_count // 2))
            if effective_overlap < min_overlap:
                continue

            boost = effective_overlap * 3
            for skill_id in scenario.get("required_skills", []):
                skill = skills_index.get(skill_id, {})
                skill_file = skill.get("file", "")
                if skill_file:
                    boosts[skill_file] = boosts.get(skill_file, 0) + boost

            matched.append({
                "name": scenario.get("name", ""),
                "required_skills": scenario.get("required_skills", []),
                "test_focus": scenario.get("test_focus", []),
            })

        for skill in skills_index.values():
            skill_tags = set(skill.get("tags", []))
            for cover in skill.get("covers", []):
                skill_tags.update(_extract_keywords(cover))
            overlap = len(query_keywords & skill_tags)
            if overlap > 0:
                skill_file = skill.get("file", "")
                if skill_file:
                    boosts[skill_file] = boosts.get(skill_file, 0) + overlap * 2

        return boosts, matched

    # ── Synonyms ──

    def upsert_synonym_group(self, group_name: str, terms: List[str]) -> None:
        self.conn.execute(
            "DELETE FROM synonyms WHERE group_name=?", (group_name,)
        )
        for term in terms:
            self.conn.execute(
                "INSERT OR IGNORE INTO synonyms (group_name, term) VALUES (?, ?)",
                (group_name, term),
            )
        self.conn.commit()

    def load_synonym_map(self) -> Dict[str, Set[str]]:
        rows = self.conn.execute("SELECT group_name, term FROM synonyms").fetchall()
        groups: Dict[str, List[str]] = {}
        for r in rows:
            groups.setdefault(r["group_name"], []).append(r["term"])
        synonym_map: Dict[str, Set[str]] = {}
        for terms in groups.values():
            term_set = set(terms)
            for t in terms:
                synonym_map[t] = term_set
        return synonym_map

    def expand_keywords(self, keywords: Set[str]) -> Set[str]:
        synonym_map = self.load_synonym_map()
        expanded = set(keywords)
        for kw in keywords:
            if kw in synonym_map:
                expanded |= synonym_map[kw]
        return expanded

    # ── Test Designs ──

    def save_test_design(self, project_id: str, feature_name: str,
                         design_json: str, module_id: str = None,
                         source_url: str = "",
                         test_point_count: int = 0, test_case_count: int = 0,
                         capability_hits: List = None,
                         project_hits: List = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO test_designs (project_id, module_id, feature_name, source_url,
                   design_json, test_point_count, test_case_count,
                   capability_hits, project_hits)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, module_id, feature_name, source_url, design_json,
             test_point_count, test_case_count,
             json.dumps(capability_hits or [], ensure_ascii=False),
             json.dumps(project_hits or [], ensure_ascii=False)),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_test_design(self, id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM test_designs WHERE id=?", (id,)).fetchone()
        return dict(row) if row else None

    def list_test_designs(self, project_id: str, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM test_designs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        )
        return [dict(r) for r in rows]

    # ── Learning Feedback ──

    def save_feedback(self, feedback_type: str, content: str,
                      project_id: str = None, module_id: str = None,
                      source_design_id: int = None,
                      routed_to: List[str] = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO learning_feedback (project_id, module_id, source_design_id,
                   feedback_type, content, routed_to)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, module_id, source_design_id, feedback_type, content,
             json.dumps(routed_to or [], ensure_ascii=False)),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_feedback(self, project_id: str = None, limit: int = 20) -> List[Dict]:
        if project_id:
            rows = self.conn.execute(
                "SELECT * FROM learning_feedback WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            )
        else:
            rows = self.conn.execute(
                "SELECT * FROM learning_feedback ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        counts = {}
        for table in ("projects", "modules", "module_relations", "kb_entries",
                       "skills", "skill_scenarios", "synonyms",
                       "test_designs", "learning_feedback"):
            row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0]

        cap_count = self.conn.execute(
            "SELECT COUNT(*) FROM kb_entries WHERE kb_type='capability'"
        ).fetchone()[0]
        proj_count = self.conn.execute(
            "SELECT COUNT(*) FROM kb_entries WHERE kb_type='project'"
        ).fetchone()[0]
        counts["kb_capability"] = cap_count
        counts["kb_project"] = proj_count

        version = self.conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0]
        counts["schema_version"] = version

        return counts


# ── CLI ──

def cmd_init(args):
    db = KngDatabase(args.db)
    db.connect()
    db.initialize()
    db.close()
    print(f"Database initialized: {args.db}")


def cmd_stats(args):
    db = KngDatabase(args.db)
    db.connect()
    db.initialize()
    stats = db.get_stats()
    db.close()
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="KNG database management")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize database")
    p_init.add_argument("--db", required=True, help="Database file path")

    p_stats = sub.add_parser("stats", help="Show database statistics")
    p_stats.add_argument("--db", required=True, help="Database file path")

    p_view = sub.add_parser("view", help="Launch web viewer")
    p_view.add_argument("--db", required=True, help="Database file path")
    p_view.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    p_view.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "view":
        from db_viewer import main as viewer_main
        sys.argv = ["db_viewer", "--db", args.db, "--port", str(args.port), "--host", args.host]
        return viewer_main()
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
