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
import os
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
            final_blow_corp_id INTEGER,
            final_blow_alliance_id INTEGER,
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

    # Get final blow attacker's corp/alliance
    final_blow_corp_id = None
    final_blow_alliance_id = None
    for a in attackers:
        if a.get("character_id") == final_blow:
            final_blow_corp_id = a.get("corporation_id")
            final_blow_alliance_id = a.get("alliance_id")
            break

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
        "final_blow_corp_id": final_blow_corp_id,
        "final_blow_alliance_id": final_blow_alliance_id,
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
         final_blow_corp_id, final_blow_alliance_id,
         top_damage_char_id, solar_system_id, total_value, raw_json)
        VALUES
        (:killmail_id, :killmail_time, :victim_char_id, :victim_corp_id,
         :victim_alliance_id, :victim_ship_type_id, :final_blow_char_id,
         :final_blow_corp_id, :final_blow_alliance_id,
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


def get_available_days(max_age_days=365):
    """Fetch list of days with data from zKill totals, capped at max_age_days."""
    from datetime import datetime, timedelta
    data = fetch_json(ZKILL_TOTALS)
    if not data:
        return []
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime('%Y%m%d')
    days = sorted([d for d in data.keys() if d >= cutoff])
    return days


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

    # Re-import the latest day in range to catch incomplete dumps
    if days and not force and days[-1] in imported:
        to_import.append(days[-1])

    print(f"Total available days: {len(available)} (capped at 365)")
    print(f"Already imported: {len(imported)}")
    print(f"To import: {len(to_import)}")
    print()

    total_kills = 0
    for i, day in enumerate(sorted(to_import), 1):
        kills = import_day(db_path, day)
        total_kills += kills
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(to_import)} days, {total_kills} kills so far")
        time.sleep(0.5)  # Be polite to zKill

    print(f"\nDone. Imported {total_kills} kills across {len(to_import)} days.")


def fill_range(db_path, start_day):
    """Import all days from start_day to now, skipping already-imported days."""
    init_db(db_path)

    available = get_available_days()
    if not available:
        print("Could not fetch day list from zKill")
        return

    imported = get_imported_days(db_path)

    days = [d for d in available if d >= start_day]
    to_import = [d for d in days if d not in imported]

    # Re-import the latest day to catch incomplete dumps
    if days and days[-1] in imported:
        to_import.append(days[-1])

    if not to_import:
        print("All days in range already imported.")
        return

    print(f"Available from {start_day}: {len(days)} days (capped at 365 from zKill)")
    print(f"Already imported: {len([d for d in days if d in imported])}")
    print(f"To import: {len(to_import)}")
    print()

    total_kills = 0
    for i, day in enumerate(sorted(to_import), 1):
        kills = import_day(db_path, day)
        total_kills += kills
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(to_import)} days, {total_kills} kills so far")
        time.sleep(0.5)

    print(f"\nDone. Imported {total_kills} kills across {len(to_import)} days.")


def compute_nemesis(db_path, min_losses=3):
    """
    For every character with >= min_losses, compute:
    - Their nemesis (who killed them most, by final blow)
    - Top 5 killers
    Returns dict: char_id -> nemesis_data
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Single query: get all victim-killer relationships at once
    print("Computing nemesis relationships...")
    c.execute("""
        SELECT victim_char_id,
               COALESCE(final_blow_char_id, top_damage_char_id) as killer_id,
               CASE WHEN final_blow_char_id IS NOT NULL THEN 1 ELSE 0 END as is_final_blow,
               COUNT(*) as kill_count,
               SUM(CASE WHEN final_blow_char_id IS NOT NULL THEN 1 ELSE 0 END) as final_blow_count
        FROM kills
        WHERE victim_char_id IS NOT NULL
          AND COALESCE(final_blow_char_id, top_damage_char_id) IS NOT NULL
        GROUP BY victim_char_id, killer_id
    """)

    # Build killer counts per victim
    victim_killers = defaultdict(lambda: defaultdict(lambda: {"count": 0, "final_blows": 0}))
    victim_loss_counts = defaultdict(int)

    for row in c:
        victim_id = row["victim_char_id"]
        killer_id = row["killer_id"]
        victim_killers[victim_id][killer_id]["count"] = row["kill_count"]
        victim_killers[victim_id][killer_id]["final_blows"] = row["final_blow_count"]
        victim_loss_counts[victim_id] += row["kill_count"]

    # Filter to victims with >= min_losses
    victims = {vid: cnt for vid, cnt in victim_loss_counts.items() if cnt >= min_losses}
    print(f"Found {len(victims)} characters with >= {min_losses} losses")

    results = {}
    char_ids_to_resolve = set()
    total = len(victims)

    for i, (char_id, total_losses) in enumerate(victims.items(), 1):
        if i % 10000 == 0 or i == total:
            pct = 100 * i / total
            bar = '=' * (i * 50 // total)
            print(f"\r  Progress: [{bar:<50}] {pct:.1f}% ({i}/{total})", end='', flush=True)

        killers = victim_killers[char_id]
        if not killers:
            continue

        sorted_killers = sorted(
            killers.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        nemesis_id, nemesis_stats = sorted_killers[0]
        top_5 = sorted_killers[:5]

        char_ids_to_resolve.add(char_id)
        char_ids_to_resolve.add(nemesis_id)
        for k_id, _ in top_5:
            char_ids_to_resolve.add(k_id)

        results[char_id] = {
            "character_id": char_id,
            "total_losses": total_losses,
            "unique_killers": len(killers),
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
        }

    print()  # newline after progress bar
    conn.close()

    # Resolve names with cache
    cache_path = os.path.join(os.path.dirname(db_path), "name_cache.json")
    name_cache = load_name_cache(cache_path)
    print(f"Resolving {len(char_ids_to_resolve)} character names (cached: {len(name_cache)})...")
    names = resolve_character_names(char_ids_to_resolve, cache=name_cache)
    save_name_cache(name_cache, cache_path)

    # Fill in names
    for char_id, data in results.items():
        data["character_name"] = names.get(char_id, f"Character {char_id}")
        data["nemesis"]["name"] = names.get(data["nemesis"]["id"], f"Character {data['nemesis']['id']}")
        for k in data["top_killers"]:
            k["name"] = names.get(k["id"], f"Character {k['id']}")

    # Resolve corporation and alliance info
    print("Fetching corporation/alliance info...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get latest corp/alliance for each victim
    victim_ids = list(results.keys())
    print(f"  Looking up corp/alliance for {len(victim_ids)} victims...")
    c.execute("""
        SELECT victim_char_id, victim_corp_id, victim_alliance_id
        FROM kills
        WHERE victim_char_id IN ({0})
        ORDER BY killmail_time DESC
    """.format(','.join('?' * len(victim_ids))), victim_ids)

    victim_corp_alliance = {}
    for i, row in enumerate(c, 1):
        if i % 50000 == 0:
            print(f"    Processed {i} rows...")
        vid = row["victim_char_id"]
        if vid not in victim_corp_alliance:
            victim_corp_alliance[vid] = {
                "corporation_id": row["victim_corp_id"],
                "alliance_id": row["victim_alliance_id"],
            }

    # Get corp/alliance for each nemesis — try new columns first, then raw_json fallback
    nemesis_ids = list({data["nemesis"]["id"] for data in results.values()})
    print(f"  Looking up corp/alliance for {len(nemesis_ids)} nemeses...")
    c.execute("""
        SELECT final_blow_char_id, final_blow_corp_id, final_blow_alliance_id, raw_json
        FROM kills
        WHERE final_blow_char_id IN ({0})
        ORDER BY killmail_time DESC
    """.format(','.join('?' * len(nemesis_ids))), nemesis_ids)

    nemesis_corp_alliance = {}
    for i, row in enumerate(c, 1):
        if i % 50000 == 0:
            print(f"    Processed {i} rows...")
        nid = row["final_blow_char_id"]
        if nid in nemesis_corp_alliance:
            continue
        # Use new columns if available
        if row["final_blow_corp_id"] is not None or row["final_blow_alliance_id"] is not None:
            nemesis_corp_alliance[nid] = {
                "corporation_id": row["final_blow_corp_id"],
                "alliance_id": row["final_blow_alliance_id"],
            }
            continue
        # Fallback: parse raw_json
        try:
            km = json.loads(row["raw_json"])
            for a in km.get("attackers", []):
                if a.get("character_id") == nid:
                    nemesis_corp_alliance[nid] = {
                        "corporation_id": a.get("corporation_id"),
                        "alliance_id": a.get("alliance_id"),
                    }
                    break
        except Exception:
            pass

    conn.close()

    # Resolve corp/alliance names
    corp_ids = set()
    alliance_ids = set()
    for info in victim_corp_alliance.values():
        if info.get("corporation_id"): corp_ids.add(info["corporation_id"])
        if info.get("alliance_id"): alliance_ids.add(info["alliance_id"])
    for info in nemesis_corp_alliance.values():
        if info.get("corporation_id"): corp_ids.add(info["corporation_id"])
        if info.get("alliance_id"): alliance_ids.add(info["alliance_id"])

    print(f"  Resolving {len(corp_ids)} corporation names, {len(alliance_ids)} alliance names...")
    corp_names = resolve_ids(corp_ids, category_filter="corporation", cache=name_cache)
    alliance_names = resolve_ids(alliance_ids, category_filter="alliance", cache=name_cache)
    save_name_cache(name_cache, cache_path)

    # Fill in corp/alliance data
    for char_id, data in results.items():
        info = victim_corp_alliance.get(char_id, {})
        data["corporation_id"] = info.get("corporation_id")
        data["alliance_id"] = info.get("alliance_id")
        data["corporation_name"] = corp_names.get(info.get("corporation_id")) if info.get("corporation_id") else None
        data["alliance_name"] = alliance_names.get(info.get("alliance_id")) if info.get("alliance_id") else None

        n_info = nemesis_corp_alliance.get(data["nemesis"]["id"], {})
        data["nemesis"]["corporation_id"] = n_info.get("corporation_id")
        data["nemesis"]["alliance_id"] = n_info.get("alliance_id")
        data["nemesis"]["corporation_name"] = corp_names.get(n_info.get("corporation_id")) if n_info.get("corporation_id") else None
        data["nemesis"]["alliance_name"] = alliance_names.get(n_info.get("alliance_id")) if n_info.get("alliance_id") else None

    return results


def load_name_cache(cache_path):
    """Load cached name resolutions from disk."""
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_name_cache(cache, cache_path):
    """Save cached name resolutions to disk."""
    if cache_path:
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
        except Exception as e:
            print(f"  Warning: could not save name cache: {e}")


def resolve_ids(ids, category_filter=None, cache=None):
    """
    Resolve IDs to names via ESI /universe/names/ (batch up to 1000).
    Returns dict: id -> name (filtered by category if specified).
    Uses optional cache dict to avoid re-resolving known names.
    """
    if not ids:
        return {}

    names = {}
    ids_to_resolve = []

    # Check cache first
    for eid in ids:
        key = f"{category_filter or 'any'}:{eid}"
        if cache and key in cache:
            names[eid] = cache[key]
        else:
            ids_to_resolve.append(eid)

    if not ids_to_resolve:
        return names

    ids_list = list(ids_to_resolve)
    total_batches = (len(ids_list) + 999) // 1000

    for i in range(0, len(ids_list), 1000):
        batch = ids_list[i:i+1000]
        batch_num = i // 1000 + 1
        pct = 100 * batch_num / total_batches
        bar = '=' * (batch_num * 30 // total_batches)
        print(f"\r  ESI: [{bar:<30}] {pct:.1f}% ({batch_num}/{total_batches} batches)", end='', flush=True)
        for attempt in range(5):
            try:
                r = requests.post(ESI_NAMES_URL, json=batch, timeout=30)
                if r.status_code == 200:
                    for entry in r.json():
                        eid = entry.get("id")
                        name = entry.get("name")
                        cat = entry.get("category")
                        if name and (category_filter is None or cat == category_filter):
                            names[eid] = name
                            if cache is not None:
                                cache[f"{category_filter or 'any'}:{eid}"] = name
                    break
                elif r.status_code == 429:
                    retry_after = int(r.headers.get('retry-after', 2))
                    print(f"\n  ESI rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                elif r.status_code >= 500:
                    print(f"\n  ESI error {r.status_code}, retrying...")
                    time.sleep(2 ** attempt)
                else:
                    print(f"\n  ESI error {r.status_code}: {r.text[:200]}")
                    break
            except Exception as e:
                print(f"\n  ESI resolution error: {e}")
                time.sleep(2 ** attempt)
        time.sleep(0.1)  # Rate limit between batches
    print()  # newline after progress bar

    return names


def resolve_character_names(char_ids, cache=None):
    """Resolve character IDs to names."""
    names = resolve_ids(char_ids, category_filter="character", cache=cache)
    for cid in char_ids:
        if cid not in names:
            names[cid] = f"Character {cid}"
    return names


def export_nemesis_data(db_path, output_dir, min_losses=3):
    """Export nemesis JSON files for static site."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = compute_nemesis(db_path, min_losses=min_losses)
    print(f"Exporting {len(results)} characters...")

    # Save individual files
    index = {}
    total = len(results)
    for i, (char_id, data) in enumerate(results.items(), 1):
        if i % 50000 == 0:
            print(f"  Saved {i}/{total} character files...")
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

    # Save index (full metadata for backward compatibility)
    with open(out / "index.json", "w") as f:
        json.dump(index, f, indent=2)

    # Save minimal names index — include ALL characters (victims + nemeses)
    names_index = {name: data["id"] for name, data in index.items()}
    # Add nemeses who have 0 losses (not in index)
    for char_id, data in results.items():
        nemesis_id = data["nemesis"]["id"]
        nemesis_name = data["nemesis"]["name"]
        if nemesis_name and not nemesis_name.startswith("Character ") and nemesis_name not in names_index:
            names_index[nemesis_name] = nemesis_id
        for k in data["top_killers"]:
            if k["name"] and not k["name"].startswith("Character ") and k["name"] not in names_index:
                names_index[k["name"]] = k["id"]
    with open(out / "names.json", "w") as f:
        json.dump(names_index, f, indent=2)

    # Get date range from DB
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT MIN(killmail_time), MAX(killmail_time) FROM kills")
    min_time, max_time = c.fetchone()
    conn.close()

    # Save metadata
    meta = {
        "count": len(results),
        "date_from": min_time[:10] if min_time else None,
        "date_to": max_time[:10] if max_time else None,
    }
    with open(out / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

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

    # Build top nemesis leaderboard (characters who are nemesis of the most others)
    # Also include corp/alliance from results where available
    top_nemesis = []
    for nemesis_id, victims in reverse.items():
        # Find corp/alliance for this nemesis from any victim's data
        nemesis_corp_id = None
        nemesis_corp_name = None
        nemesis_alliance_id = None
        nemesis_alliance_name = None
        for char_id, data in results.items():
            if data["nemesis"]["id"] == nemesis_id:
                nemesis_corp_id = data["nemesis"].get("corporation_id")
                nemesis_corp_name = data["nemesis"].get("corporation_name")
                nemesis_alliance_id = data["nemesis"].get("alliance_id")
                nemesis_alliance_name = data["nemesis"].get("alliance_name")
                break

        # Get nemesis character name from any victim's nemesis data
        nemesis_char_name = None
        for char_id, data in results.items():
            if data["nemesis"]["id"] == nemesis_id:
                nemesis_char_name = data["nemesis"]["name"]
                break
        if not nemesis_char_name:
            nemesis_char_name = f"Character {nemesis_id}"
        top_nemesis.append({
            "id": nemesis_id,
            "name": nemesis_char_name,
            "nemesis_count": len(victims),
            "total_final_blows": sum(v["kill_count"] for v in victims),
            "top_victim": victims[0] if victims else None,
            "corporation_id": nemesis_corp_id,
            "corporation_name": nemesis_corp_name,
            "alliance_id": nemesis_alliance_id,
            "alliance_name": nemesis_alliance_name,
        })

    top_nemesis.sort(key=lambda x: x["nemesis_count"], reverse=True)

    with open(out / "top_nemesis.json", "w") as f:
        json.dump(top_nemesis, f, indent=2)

    print(f"Saved to {out}")
    print(f"  Characters: {len(results)}")
    print(f"  Index entries: {len(index)}")
    print(f"  Reverse entries: {len(reverse)}")
    print(f"  Top nemesis entries: {len(top_nemesis)}")


def trim_old_data(db_path, keep_days=365):
    """Delete killmails older than keep_days from DB and exported JSON."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime('%Y-%m-%d')

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Count what we're about to delete
    c.execute("SELECT COUNT(*) FROM kills WHERE killmail_time < ?", (cutoff,))
    to_delete = c.fetchone()[0]

    if to_delete == 0:
        conn.close()
        print("No old data to trim.")
        return 0

    # Delete old kills
    c.execute("DELETE FROM kills WHERE killmail_time < ?", (cutoff,))

    conn.commit()
    conn.close()
    print(f"Trimmed {to_delete:,} kills before {cutoff}")
    return to_delete


def update_database(db_path):
    """Add any new days since last import. Re-imports the latest day to catch incomplete dumps."""
    init_db(db_path)
    imported = get_imported_days(db_path)
    available = get_available_days()

    print(f"Available days from zKill: {len(available)} (from {available[0]} to {available[-1]})")
    print(f"Already imported: {len(imported)} days")

    to_import = [d for d in available if d not in imported]

    # Always re-import the most recent already-imported day (may have been incomplete)
    if available and available[-1] in imported:
        to_import.append(available[-1])
        print(f"Re-importing latest day {available[-1]} to ensure completeness...")

    if not to_import:
        print("Database is up to date.")
        return

    print(f"Importing {len(to_import)} days...")
    total = 0
    for day in sorted(to_import):
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
    parser.add_argument("--fill", help="Fill from START_DATE to now (YYYYMMDD)")
    parser.add_argument("--force", action="store_true", help="Re-import already-imported days")
    args = parser.parse_args()

    if args.init_db:
        build_database(args.db, start_day=args.start, end_day=args.end, force=args.force)
    elif args.fill:
        fill_range(args.db, args.fill)
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
