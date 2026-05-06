#!/usr/bin/env python3
"""Collapse duplicate kb_entries that share the same source_file.

Background: earlier plugin versions called ``kb_import.py --force`` from every
skill, which bypassed the source-file dedupe check and inserted a fresh copy
of every KB file on each import. This script repairs DBs that accumulated
duplicates, keeping the newest row per source_file.

Usage:
    python dedupe_db.py --db PATH [--dry-run]

If ``--db`` is omitted, the script reads ``db_path`` from
``$KNG_HOME/kng.config.json`` (or ``~/.kng-plugin/kng.config.json``).
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import KngDatabase


def _resolve_default_db() -> str:
    home = os.environ.get("KNG_HOME")
    base = pathlib.Path(home) if home else pathlib.Path.home() / ".kng-plugin"
    cfg = base / "kng.config.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8")).get("db_path", "")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite DB path (default: from kng.config.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report duplicate counts without deleting")
    args = parser.parse_args()

    db_path = args.db or _resolve_default_db()
    if not db_path or not pathlib.Path(db_path).exists():
        print(f"DB not found: {db_path or '(unresolved)'}", file=sys.stderr)
        return 1

    db = KngDatabase(db_path)
    db.connect()
    db.initialize()

    rows = db.conn.execute(
        """SELECT source_file, COUNT(*) c
             FROM kb_entries
            WHERE source_file IS NOT NULL AND source_file != ''
            GROUP BY source_file
           HAVING c > 1
            ORDER BY c DESC""",
    ).fetchall()

    duplicate_groups = len(rows)
    extra_rows = sum(r["c"] - 1 for r in rows)

    print(f"DB: {db_path}")
    print(f"Duplicate source_file groups: {duplicate_groups}")
    print(f"Excess rows that would be removed: {extra_rows}")
    if duplicate_groups and args.dry_run:
        print("\nTop offenders:")
        for r in rows[:10]:
            print(f"  {r['c']:4d}  {r['source_file']}")

    if args.dry_run or duplicate_groups == 0:
        db.close()
        return 0

    removed = db.dedupe_kb_entries_by_source()
    print(f"\nRemoved {removed} duplicate rows.")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
