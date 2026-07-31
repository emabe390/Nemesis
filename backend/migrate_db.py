#!/usr/bin/env python3
"""
Migration: add final_blow_corp_id and final_blow_alliance_id to kills table.

Usage:
    python migrate_db.py <db_path>
"""

import sqlite3
import sys


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Check if columns already exist
    c.execute("PRAGMA table_info(kills)")
    columns = {row[1] for row in c.fetchall()}

    if "final_blow_corp_id" not in columns:
        c.execute("ALTER TABLE kills ADD COLUMN final_blow_corp_id INTEGER")
        print("Added final_blow_corp_id")
    else:
        print("final_blow_corp_id already exists")

    if "final_blow_alliance_id" not in columns:
        c.execute("ALTER TABLE kills ADD COLUMN final_blow_alliance_id INTEGER")
        print("Added final_blow_alliance_id")
    else:
        print("final_blow_alliance_id already exists")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_db.py <db_path>")
        sys.exit(1)
    migrate(sys.argv[1])
