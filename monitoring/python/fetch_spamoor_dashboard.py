#!/usr/bin/env python3
"""
Reads 'spamoor' from ports.json, calls /api/graphs/dashboard,
and saves the response to data/spamoor_dashboard.json.

No flags, standard-library only.
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PORTS_PATH = "ports.json"
OUT_PATH = os.path.join("data", "spamoor_dashboard.json")

def main():
    # Load ports.json
    try:
        with open(PORTS_PATH, "r", encoding="utf-8") as f:
            ports = json.load(f)
    except FileNotFoundError:
        print(f"ports.json not found at: {PORTS_PATH}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in ports.json: {e}", file=sys.stderr)
        sys.exit(1)

    base = ports.get("spamoor")
    if not base:
        print("Key 'spamoor' not found in ports.json", file=sys.stderr)
        sys.exit(1)

    url = base.rstrip("/") + "/api/graphs/dashboard"

    # Make request
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "fetch_spamoor_dashboard/0.1"})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"HTTP error {e.code} for {url}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Request failed for {url}: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse JSON (fallback to wrapping raw text)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"_non_json_response": raw}

    # Ensure output dir and write file
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[ok] wrote {OUT_PATH}")
    except OSError as e:
        print(f"Failed to write {OUT_PATH}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
