#!/usr/bin/env python3
"""
EVE Nemesis Tracker — zKill Static Database Builder

Downloads zKill history dumps, builds a local SQLite database of all
character kill relationships, then exports nemesis data for every character
with losses. Also builds reverse nemesis index.

Usage:
    python build_nemesis.py --init-db              # Download history and build SQLite
    python build_nemesis.py --update               # Add latest days to existing DB
    python build_nemesis.py --export ../site/data  # Export JSON for static site
    python build_nemesis.py --full ../site/data    # Update DB + export everything

The zKill history API provides daily JSON dumps at:
    https://r2z2.zkillboard.com/history/raw/YYYYMMDD.json

Each file contains killmail_id -> full killmail data (attackers, victim, etc.)
"""

import argparse
import gzip
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import requests


ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"

ZKILL_HISTORY = "https://r2z2.zkillboard.com/history/raw/{}.json"
ZKILL_TOTALS = "https://r2z2.zkillboard.com/history/totals.json"

HEADERS = {
    "User-Agent": "NemesisTracker/1.0 (static site; contact: your@email.com)",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}


def fetch_json(url, retries=3, timeout=60):
    """Fetch JSON from URL with retries."""
    req = Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                # Handle gzip
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return json.loads(data)
        except HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                time.sleep(5)
                continue
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return None


def init_db(db_path):
    """Create SQLite schema for killmail relationships."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Raw killmail relationships: who killed whom
    c.execute("""
        CREATE TABLE IF NOT EXISTS kills (
            killmail_id INTEGER PRIMARY KEY,
            killmail_time TEXT,
            victim_char_id INTEGER,
            victim_corp_id INTEGER,
            victim_alliance_id INTEGER,
            victim_ship_type_id INTEGER,
            final_blow_char_id INTEGER,
            top_damage_char_id INTEGER,
            solar_system_id INTEGER,
            total_value REAL,
            raw_json BLOB
        )
    """)

    # Index for fast nemesis queries
    c.execute("CREATE INDEX IF NOT EXISTS idx_victim ON kills(victim_char_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_final_blow ON kills(final_blow_char_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_time ON kills(killmail_time)")

    # Track which days we've imported
    c.execute("""
        CREATE TABLE IF NOT EXISTS imported_days (
            day TEXT PRIMARY KEY,
            kill_count INTEGER,
            imported_at TEXT
        )
    """)

    # Character name cache (resolved from ESI or zKill)
    c.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            character_id INTEGER PRIMARY KEY,
            name TEXT,
            corporation_id INTEGER,
            alliance_id INTEGER,
            resolved_at TEXT
        )
    """)

    # Ship name cache
    c.execute("""
        CREATE TABLE IF NOT EXISTS ships (
            type_id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)

    conn.commit()
    conn.close()


def parse_killmail(killmail_id, km):
    """Extract relevant fields from a zKill raw killmail."""
    victim = km.get("victim", {})
    attackers = km.get("attackers", [])

    victim_char_id = victim.get("character_id")
    if victim_char_id is None:
        return None  # Skip NPC/structure kills for nemesis tracking

    # Find final blow and top damage dealer
    final_blow = None
    top_damage = None
    top_damage_val = 0

    for a in attackers:
        char_id = a.get("character_id")
        if char_id is None:
            continue
        if a.get("final_blow"):
            final_blow = char_id
        dmg = a.get("damage_done", 0)
        if dmg > top_damage_val:
            top_damage_val = dmg
            top_damage = char_id

    # If no final_blow marked, use top damage
    killer_id = final_blow or top_damage
    if killer_id is None:
        return None

    zkb = km.get("zkb", {})
    total_value = zkb.get("totalValue", 0)

    return {
        "killmail_id": killmail_id,
        "killmail_time": km.get("killmail_time"),
        "victim_char_id": victim_char_id,
        "victim_corp_id": victim.get("corporation_id"),
        "victim_alliance_id": victim.get("alliance_id"),
        "victim_ship_type_id": victim.get("ship_type_id"),
        "final_blow_char_id": final_blow,
        "top_damage_char_id": top_damage,
        "solar_system_id": km.get("solar_system_id"),
        "total_value": total_value,
        "raw_json": json.dumps(km, separators=(',', ':')),
    }


def import_day(db_path, day):
    """Download and import a single day's killmails."""
    url = ZKILL_HISTORY.format(day)
    print(f"  Fetching {day}...", end=" ", flush=True)

    data = fetch_json(url)
    if data is None:
        print("404 (no data)")
        return 0

    kills = []
    for killmail_id, km in data.items():
        parsed = parse_killmail(int(killmail_id), km)
        if parsed:
            kills.append(parsed)

    if not kills:
        print("0 character kills")
        return 0

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Insert with conflict ignore (in case re-importing)
    c.executemany("""
        INSERT OR IGNORE INTO kills
        (killmail_id, killmail_time, victim_char_id, victim_corp_id,
         victim_alliance_id, victim_ship_type_id, final_blow_char_id,
         top_damage_char_id, solar_system_id, total_value, raw_json)
        VALUES
        (:killmail_id, :killmail_time, :victim_char_id, :victim_corp_id,
         :victim_alliance_id, :victim_ship_type_id, :final_blow_char_id,
         :top_damage_char_id, :solar_system_id, :total_value, :raw_json)
    """, kills)

    c.execute("""
        INSERT OR REPLACE INTO imported_days (day, kill_count, imported_at)
        VALUES (?, ?, datetime('now'))
    """, (day, len(kills)))

    conn.commit()
    conn.close()
    print(f"{len(kills)} kills")
    return len(kills)


def get_imported_days(db_path):
    """Return set of already-imported days."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT day FROM imported_days")
    days = {row[0] for row in c.fetchall()}
    conn.close()
    return days


def get_available_days():
    """Fetch list of days with data from zKill totals."""
    data = fetch_json(ZKILL_TOTALS)
    if not data:
        return []
    # Return sorted list of days (strings)
    return sorted(data.keys())


def build_database(db_path, start_day=None, end_day=None, force=False):
    """Download all available history and build the SQLite DB."""
    init_db(db_path)

    available = get_available_days()
    if not available:
        print("Could not fetch day list from zKill")
        return

    imported = set() if force else get_imported_days(db_path)

    # Filter by date range
    days = [d for d in available]
    if start_day:
        days = [d for d in days if d >= start_day]
    if end_day:
        days = [d for d in days if d <= end_day]

    to_import = [d for d in days if d not in imported]
    print(f"Total available days: {len(available)}")
    print(f"Already imported: {len(imported)}")
    print(f"To import: {len(to_import)}")
    print()

    total_kills = 0
    for i, day in enumerate(to_import, 1):
        kills = import_day(db_path, day)
        total_kills += kills
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(to_import)} days, {total_kills} kills so far")
        time.sleep(0.5)  # Be polite to zKill

    print(f"\nDone. Imported {total_kills} kills across {len(to_import)} days.")


def compute_nemesis(db_path, min_losses=3):
    """
    For every character with >= min_losses, compute:
    - Their nemesis (who killed them most, by final blow)
    - Top 5 killers
    - Recent losses
    Returns dict: char_id -> nemesis_data
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get all victims with enough losses
    c.execute("""
        SELECT victim_char_id, COUNT(*) as loss_count
        FROM kills
        WHERE victim_char_id IS NOT NULL
        GROUP BY victim_char_id
        HAVING loss_count >= ?
    """, (min_losses,))

    victims = {row[0]: row[1] for row in c.fetchall()}
    print(f"Found {len(victims)} characters with >= {min_losses} losses")

    results = {}
    char_ids_to_resolve = set()

    for char_id in victims:
        # All losses for this character
        c.execute("""
            SELECT killmail_id, killmail_time, victim_ship_type_id,
                   final_blow_char_id, top_damage_char_id, total_value, raw_json
            FROM kills
            WHERE victim_char_id = ?
            ORDER BY killmail_time DESC
        """, (char_id,))

        losses = []
        killer_counts = defaultdict(lambda: {"count": 0, "final_blows": 0, "total_damage": 0})

        for row in c.fetchall():
            killmail_id, km_time, ship_id, final_blow, top_damage, value, raw = row
            killer = final_blow or top_damage
            if not killer:
                continue

            losses.append({
                "killmail_id": killmail_id,
                "killmail_time": km_time,
                "ship_type_id": ship_id,
                "loss_value": value,
                "killer_id": killer,
            })

            killer_counts[killer]["count"] += 1
            if killer == final_blow:
                killer_counts[killer]["final_blows"] += 1

        if not killer_counts:
            continue

        # Sort killers by count desc
        sorted_killers = sorted(
            killer_counts.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        nemesis_id, nemesis_stats = sorted_killers[0]
        top_5 = sorted_killers[:5]

        char_ids_to_resolve.add(char_id)
        char_ids_to_resolve.add(nemesis_id)
        for k_id, _ in top_5:
            char_ids_to_resolve.add(k_id)

        # Recent 10 losses
        recent = losses[:10]
        for loss in recent:
            char_ids_to_resolve.add(loss["killer_id"])

        results[char_id] = {
            "character_id": char_id,
            "total_losses": len(losses),
            "unique_killers": len(killer_counts),
            "nemesis": {
                "id": nemesis_id,
                "name": None,
                "kill_count": nemesis_stats["count"],
                "final_blows": nemesis_stats["final_blows"],
            },
            "top_killers": [
                {
                    "id": k_id,
                    "name": None,
                    "kill_count": stats["count"],
                    "final_blows": stats["final_blows"],
                }
                for k_id, stats in top_5
            ],
            "recent_losses": [
                {
                    "killmail_id": l["killmail_id"],
                    "killmail_time": l["killmail_time"],
                    "ship_type_id": l["ship_type_id"],
                    "loss_value": l["loss_value"],
                    "killer_id": l["killer_id"],
                    "killer_name": None,
                }
                for l in recent
            ],
        }

    conn.close()

    # Resolve names
    print(f"Resolving {len(char_ids_to_resolve)} character names...")
    names = resolve_character_names(char_ids_to_resolve)

    # Fill in names
    for char_id, data in results.items():
        data["character_name"] = names.get(char_id, f"Character {char_id}")
        data["nemesis"]["name"] = names.get(data["nemesis"]["id"], f"Character {data['nemesis']['id']}")
        for k in data["top_killers"]:
            k["name"] = names.get(k["id"], f"Character {k['id']}")
        for loss in data["recent_losses"]:
            loss["killer_name"] = names.get(loss["killer_id"], f"Character {loss['killer_id']}")

    return results


def resolve_ids(ids, category_filter=None):
    """
    Resolve IDs to names via ESI /universe/names/ (batch up to 1000).
    Returns dict: id -> name (filtered by category if specified).
    """
    if not ids:
        return {}

    names = {}
    ids_list = list(ids)

    for i in range(0, len(ids_list), 1000):
        batch = ids_list[i:i+1000]
        try:
            r = requests.post(ESI_NAMES_URL, json=batch, timeout=30)
            if r.status_code == 200:
                for entry in r.json():
                    eid = entry.get("id")
                    name = entry.get("name")
                    cat = entry.get("category")
                    if name and (category_filter is None or cat == category_filter):
                        names[eid] = name
        except Exception as e:
            print(f"  ESI resolution error: {e}")

    return names


def resolve_character_names(char_ids):
    """Resolve character IDs to names."""
    names = resolve_ids(char_ids, category_filter="character")
    for cid in char_ids:
        if cid not in names:
            names[cid] = f"Character {cid}"
    return names


def resolve_ship_names(ship_ids):
    """Resolve ship type IDs to names."""
    names = resolve_ids(ship_ids, category_filter="inventory_type")
    for sid in ship_ids:
        if sid not in names:
            names[sid] = f"Type {sid}"
    return names


def export_nemesis_data(db_path, output_dir, min_losses=3):
    """Export nemesis JSON files for static site."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = compute_nemesis(db_path, min_losses=min_losses)
    print(f"Exporting {len(results)} characters...")

    # Collect all ship IDs to resolve
    ship_ids = set()
    for data in results.values():
        for loss in data["recent_losses"]:
            if loss["ship_type_id"]:
                ship_ids.add(loss["ship_type_id"])

    # Resolve ship names
    if ship_ids:
        print(f"Resolving {len(ship_ids)} ship names...")
        ship_names = resolve_ship_names(ship_ids)
        for data in results.values():
            for loss in data["recent_losses"]:
                loss["ship_name"] = ship_names.get(loss["ship_type_id"], "Unknown")

    # Save individual files
    index = {}
    for char_id, data in results.items():
        char_name = data["character_name"]
        slug = char_name.lower().replace(" ", "_").replace("-", "_")

        # Save by ID
        with open(out / f"{char_id}.json", "w") as f:
            json.dump(data, f, indent=2)

        # Save by slug
        with open(out / f"{slug}.json", "w") as f:
            json.dump(data, f, indent=2)

        index[char_name] = {
            "id": char_id,
            "nemesis_name": data["nemesis"]["name"],
            "nemesis_kill_count": data["nemesis"]["kill_count"],
            "total_losses": data["total_losses"],
        }

    # Save index
    with open(out / "index.json", "w") as f:
        json.dump(index, f, indent=2)

    # Build reverse nemesis
    reverse = defaultdict(list)
    for char_id, data in results.items():
        nemesis_id = data["nemesis"]["id"]
        reverse[nemesis_id].append({
            "id": char_id,
            "name": data["character_name"],
            "kill_count": data["nemesis"]["kill_count"],
        })

    # Sort by kill_count desc
    for nemesis_id in reverse:
        reverse[nemesis_id].sort(key=lambda x: x["kill_count"], reverse=True)

    with open(out / "reverse_nemesis.json", "w") as f:
        json.dump(dict(reverse), f, indent=2)

    print(f"Saved to {out}")
    print(f"  Characters: {len(results)}")
    print(f"  Index entries: {len(index)}")
    print(f"  Reverse entries: {len(reverse)}")


def update_database(db_path):
    """Add any new days since last import."""
    init_db(db_path)
    imported = get_imported_days(db_path)
    available = get_available_days()

    to_import = [d for d in available if d not in imported]
    if not to_import:
        print("Database is up to date.")
        return

    print(f"Importing {len(to_import)} new days...")
    total = 0
    for day in to_import:
        kills = import_day(db_path, day)
        total += kills
        time.sleep(0.5)
    print(f"Added {total} kills from {len(to_import)} days.")


def db_stats(db_path):
    """Print database statistics."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM kills")
    total_kills = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT victim_char_id) FROM kills")
    unique_victims = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT final_blow_char_id) FROM kills WHERE final_blow_char_id IS NOT NULL")
    unique_killers = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM imported_days")
    days = c.fetchone()[0]

    c.execute("SELECT MIN(killmail_time), MAX(killmail_time) FROM kills")
    min_time, max_time = c.fetchone()

    conn.close()

    print(f"Database: {db_path}")
    print(f"  Total kills: {total_kills:,}")
    print(f"  Unique victims: {unique_victims:,}")
    print(f"  Unique killers: {unique_killers:,}")
    print(f"  Days imported: {days}")
    print(f"  Date range: {min_time} to {max_time}")


def main():
    parser = argparse.ArgumentParser(description="EVE Nemesis Tracker — zKill Database Builder")
    parser.add_argument("--db", default="nemesis.db", help="SQLite database path")
    parser.add_argument("--init-db", action="store_true", help="Build database from zKill history")
    parser.add_argument("--update", action="store_true", help="Add latest days to existing DB")
    parser.add_argument("--export", "-o", help="Export nemesis JSON to directory")
    parser.add_argument("--full", "-f", help="Update DB + export (output directory)")
    parser.add_argument("--stats", action="store_true", help="Show database stats")
    parser.add_argument("--start", help="Start date YYYYMMDD")
    parser.add_argument("--end", help="End date YYYYMMDD")
    parser.add_argument("--min-losses", type=int, default=3, help="Min losses to include character")
    parser.add_argument("--force", action="store_true", help="Re-import already-imported days")
    args = parser.parse_args()

    if args.init_db:
        build_database(args.db, start_day=args.start, end_day=args.end, force=args.force)
    elif args.update:
        update_database(args.db)
    elif args.export:
        export_nemesis_data(args.db, args.export, min_losses=args.min_losses)
    elif args.full:
        update_database(args.db)
        export_nemesis_data(args.db, args.full, min_losses=args.min_losses)
    elif args.stats:
        db_stats(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
