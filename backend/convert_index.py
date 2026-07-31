#!/usr/bin/env python3
"""
One-time conversion: index.json -> names.json

Usage:
    python convert_index.py <index.json> <names.json>
    python convert_index.py ../docs/data/index.json ../docs/data/names.json
"""

import json
import sys
from pathlib import Path


def convert_index_to_names(index_path, names_path):
    """Read index.json and write minimal names.json (name -> id only)."""
    index_path = Path(index_path)
    names_path = Path(names_path)

    print(f"Reading {index_path}...")
    with open(index_path, "r") as f:
        index = json.load(f)

    print(f"Entries: {len(index)}")

    names = {name: data["id"] for name, data in index.items()}

    print(f"Writing {names_path}...")
    with open(names_path, "w") as f:
        json.dump(names, f, indent=2)

    # Report size difference
    index_size = index_path.stat().st_size
    names_size = names_path.stat().st_size
    print(f"  index.json: {index_size:,} bytes")
    print(f"  names.json: {names_size:,} bytes")
    print(f"  Reduction: {index_size - names_size:,} bytes ({100 * (1 - names_size/index_size):.1f}%)")
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_index.py <index.json> <names.json>")
        sys.exit(1)

    convert_index_to_names(sys.argv[1], sys.argv[2])
