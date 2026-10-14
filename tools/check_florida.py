#!/usr/bin/env python3
"""Format check for the Florida resident rates file (data/florida.json).

  python3 tools/check_florida.py data/florida.json

Written by tools/fetch_florida.py on the owner's AI PC (signed in to a Florida resident NCL
account). Only numbers and category codes are allowed: any key outside the lists below fails
the check, so nothing personal from the account can reach the public repo.
"""
import datetime as dt
import json
import re
import sys

EXPECTED_SAILING = "joy-2026-11-20"
TOP_KEYS = {"schema_version", "saved_at", "sailing_id", "package_id", "guests", "source", "categories"}
CAT_KEYS = {"type", "website_fare_pp", "florida_fare_pp", "off_pp", "checked_at", "source"}
TYPES = {"STUDIO", "INSIDE", "OCEANVIEW", "BALCONY", "MINISUITE", "SUITE", "HAVEN"}
SOURCES = {"logged-in NCL account", "owner's screenshots of NCL's Florida resident view"}


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_time(v):
    for f in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt.datetime.strptime(v, f)
            return True
        except (TypeError, ValueError):
            pass
    return False


def check(data):
    errors = []
    err = errors.append
    if not isinstance(data, dict):
        return ["the file is not a JSON object"]
    extra = set(data) - TOP_KEYS
    if extra:
        err(f"unexpected keys {sorted(extra)}")
    if data.get("schema_version") != 1:
        err("schema_version must be 1")
    if not is_time(data.get("saved_at")):
        err("saved_at must be a time like 2026-10-14T11:00:00Z")
    if data.get("sailing_id") != EXPECTED_SAILING:
        err(f"sailing_id must be {EXPECTED_SAILING}")
    if not re.fullmatch(r"\d+", str(data.get("package_id", ""))):
        err("package_id must be digits")
    if data.get("guests") != 2:
        err("guests must be 2")
    if not isinstance(data.get("source"), str) or len(data["source"]) > 200:
        err("source must be short text")
    cats = data.get("categories")
    if not isinstance(cats, dict) or not cats:
        return errors + ["categories must be a non-empty object keyed by category code"]
    for code, c in cats.items():
        p = f"category {code}"
        if not re.fullmatch(r"[A-Z0-9]{2}", code):
            err(f"{p}: code must be 2 letters or digits")
        if not isinstance(c, dict):
            err(f"{p}: must be an object")
            continue
        extra = set(c) - CAT_KEYS
        if extra:
            err(f"{p}: unexpected keys {sorted(extra)}")
        if c.get("type") not in TYPES:
            err(f"{p}: type must be one of {sorted(TYPES)}")
        w, f, o = c.get("website_fare_pp"), c.get("florida_fare_pp"), c.get("off_pp")
        if not (is_num(w) and w > 0 and is_num(f) and f >= 0 and is_num(o)):
            err(f"{p}: website_fare_pp, florida_fare_pp and off_pp must be numbers")
        elif abs((w - f) - o) > 0.01:
            err(f"{p}: off_pp must be website_fare_pp minus florida_fare_pp")
        if not is_time(c.get("checked_at")):
            err(f"{p}: checked_at must be a date or time")
        if c.get("source") not in SOURCES:
            err(f"{p}: source must be one of {sorted(SOURCES)}")
    return errors


def main():
    if len(sys.argv) != 2:
        print("usage: check_florida.py PATH", file=sys.stderr)
        return 2
    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL {path}: cannot read JSON ({e})")
        return 1
    errors = check(data)
    if errors:
        print(f"FAIL {path}: {len(errors)} problem(s)")
        for e in errors:
            print("  - " + e)
        return 1
    print(f"OK {path}: {len(data['categories'])} categories, saved_at {data['saved_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
