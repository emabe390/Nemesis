#!/usr/bin/env python3
"""
Fix unnamed characters ("Character {id}") in both JSON files and SQLite DB.
Resolves real names via ESI /universe/names/ and updates everything.

Usage:
    python backend/fix_unnamed.py

Environment:
    NEMESIS_DB      — SQLite database path (default: backend/nemesis.db)
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests

DATA_DIR = Path("docs/data")
DB_PATH = Path(os.environ.get("NEMESIS_DB", "backend/nemesis.db"))
ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"


def load_names():
    with open(DATA_DIR / "names.json") as f:
        return json.load(f)


def find_unnamed(names):
    unnamed = []
    for name, char_id in names.items():
        if name.startswith("Character "):
            try:
                cid = int(name.split()[1])
                unnamed.append({"bad_name": name, "id": cid})
            except ValueError:
                pass
    return unnamed


def resolve_names(ids):
    resolved = {}
    total = len(ids)
    total_batches = (total + 999) // 1000

    for i in range(0, total, 1000):
        batch = ids[i : i + 1000]
        batch_num = i // 1000 + 1
        pct = 100 * batch_num / total_batches
        bar = "=" * (batch_num * 30 // total_batches)
        print(f"\r  ESI: [{bar:<30}] {pct:.1f}% ({batch_num}/{total_batches})", end="", flush=True)

        for attempt in range(5):
            try:
                r = requests.post(ESI_NAMES_URL, json=batch, timeout=30)
                if r.status_code == 200:
                    for entry in r.json():
                        eid = entry.get("id")
                        name = entry.get("name")
                        if name:
                            resolved[eid] = name
                    break
                elif r.status_code == 429:
                    retry_after = int(r.headers.get("retry-after", 2))
                    print(f"\n  Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                elif r.status_code >= 500:
                    print(f"\n  ESI error {r.status_code}, retrying...")
                    time.sleep(2 ** attempt)
                else:
                    print(f"\n  ESI error {r.status_code}: {r.text[:200]}")
                    break
            except Exception as e:
                print(f"\n  Error: {e}")
                time.sleep(2 ** attempt)
        time.sleep(0.1)
    print()
    return resolved


def update_json_files(rename_map, id_to_name):
    # names.json
    names = load_names()
    for old_name, new_name in rename_map.items():
        char_id = names.pop(old_name)
        names[new_name] = char_id
    with open(DATA_DIR / "names.json", "w") as f:
        json.dump(names, f, indent=2)
    print("Updated names.json")

    # All character JSON files
    updated = 0
    for file in DATA_DIR.glob("*.json"):
        if file.name == "names.json":
            continue
        with open(file) as f:
            data = json.load(f)
        changed = False

        if data.get("character_name") in rename_map:
            data["character_name"] = rename_map[data["character_name"]]
            changed = True

        nemesis = data.get("nemesis")
        if nemesis and nemesis.get("name") in rename_map:
            nemesis["name"] = rename_map[nemesis["name"]]
            changed = True

        for k in data.get("top_killers", []):
            if k.get("name") in rename_map:
                k["name"] = rename_map[k["name"]]
                changed = True

        if changed:
            with open(file, "w") as f:
                json.dump(data, f, indent=2)
            updated += 1
    print(f"Updated {updated} character files")

    # index.json
    index_path = DATA_DIR / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
        changed = False
        for old_name, new_name in rename_map.items():
            if old_name in index:
                entry = index.pop(old_name)
                index[new_name] = entry
                changed = True
        if changed:
            with open(index_path, "w") as f:
                json.dump(index, f, indent=2)
            print("Updated index.json")

    # reverse_nemesis.json
    rev_path = DATA_DIR / "reverse_nemesis.json"
    if rev_path.exists():
        with open(rev_path) as f:
            rev = json.load(f)
        changed = False
        for victims in rev.values():
            for v in victims:
                if v.get("id") in id_to_name:
                    v["name"] = id_to_name[v["id"]]
                    changed = True
        if changed:
            with open(rev_path, "w") as f:
                json.dump(rev, f, indent=2)
            print("Updated reverse_nemesis.json")

    # top_nemesis.json
    top_path = DATA_DIR / "top_nemesis.json"
    if top_path.exists():
        with open(top_path) as f:
            top = json.load(f)
        changed = False
        for entry in top:
            if entry.get("id") in id_to_name:
                entry["name"] = id_to_name[entry["id"]]
                changed = True
            tv = entry.get("top_victim")
            if tv and tv.get("id") in id_to_name:
                tv["name"] = id_to_name[tv["id"]]
                changed = True
        if changed:
            with open(top_path, "w") as f:
                json.dump(top, f, indent=2)
            print("Updated top_nemesis.json")


def update_db(id_to_name):
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}, skipping DB update")
        return

    print(f"Updating database at {DB_PATH}...")
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Check columns exist
    c.execute("PRAGMA table_info(kills)")
    columns = {row[1] for row in c.fetchall()}

    victim_col = "victim_name" if "victim_name" in columns else None
    killer_col = "final_blow_name" if "final_blow_name" in columns else None

    updated = 0
    for char_id, new_name in id_to_name.items():
        if victim_col:
            c.execute(
                f"UPDATE kills SET {victim_col} = ? WHERE victim_char_id = ?",
                (new_name, char_id),
            )
            updated += c.rowcount
        if killer_col:
            c.execute(
                f"UPDATE kills SET {killer_col} = ? WHERE final_blow_char_id = ?",
                (new_name, char_id),
            )
            updated += c.rowcount

    conn.commit()
    conn.close()
    print(f"Updated DB for {len(id_to_name)} characters ({updated} rows affected)")


def main():
    names = load_names()
    unnamed = find_unnamed(names)
    print(f"Found {len(unnamed)} unnamed characters")
    if not unnamed:
        return

    ids = [u["id"] for u in unnamed]
    resolved = resolve_names(ids)
    print(f"Resolved {len(resolved)}/{len(unnamed)} names")
    if not resolved:
        return

    rename_map = {}
    id_to_name = {}
    for u in unnamed:
        new_name = resolved.get(u["id"])
        if new_name:
            rename_map[u["bad_name"]] = new_name
            id_to_name[u["id"]] = new_name

    update_json_files(rename_map, id_to_name)
    update_db(id_to_name)
    print("Done!")


if __name__ == "__main__":
    main()
