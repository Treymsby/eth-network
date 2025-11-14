#!/usr/bin/env python3
"""
fetch_slots.py

Fetch slots from Dora and save to one JSON file.

- By default, reads ./ports.json and uses its "dora" entry, appending /api/v1/slot.
- Calls {dora_url}/api/v1/slot/<slot> for slots in the range.
- Writes one combined JSON file at the end.

Usage examples:
  python3 fetch_slots.py --start 0 --end 200 --only-data -o dora_slots.json
  python3 fetch_slots.py --ports-file /path/to/ports.json
  # To bypass ports.json and hardcode a URL:
  python3 fetch_slots.py --base-url http://127.0.0.1:35002/api/v1/slot
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import sys
import requests


def load_dora_base_url(ports_file: Path) -> str:
    """Load Dora base URL from ports.json and return the /api/v1/slot base."""
    if not ports_file.exists():
        raise FileNotFoundError(f"ports.json not found at: {ports_file}")
    try:
        ports = json.loads(ports_file.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {ports_file}: {e}") from e

    dora = ports.get("dora")
    if not isinstance(dora, str) or not dora:
        raise KeyError(f'"dora" key missing or invalid in {ports_file}')
    return dora.rstrip("/") + "/api/v1/slot"


def fetch_slot(session: requests.Session, base_url: str, slot: int,
               timeout: float, retries: int, backoff: float):
    """Fetch one slot with simple exponential backoff retries."""
    url = f"{base_url.rstrip('/')}/{slot}"
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    return {"status": "ERROR", "error": str(last_err), "slot": slot, "url": url}


def main():
    parser = argparse.ArgumentParser(description="Fetch slot data from Dora and save to one JSON file.")
    parser.add_argument("--ports-file", default="ports.json", help="Path to ports.json in the project root.")
    parser.add_argument("--base-url", default=None,
                        help="Optional override: full base URL up to /slot "
                             "(e.g. http://127.0.0.1:35002/api/v1/slot).")
    parser.add_argument("--start", type=int, default=0, help="Start slot (inclusive).")
    parser.add_argument("--end", type=int, default=200, help="End slot (inclusive).")
    parser.add_argument("-o", "--outfile", default=None, help="Output JSON file path.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per slot on failure.")
    parser.add_argument("--backoff", type=float, default=0.5, help="Exponential backoff base in seconds.")
    parser.add_argument("--only-data", dest="only_data", action="store_true",
                        help="Store only the 'data' field when status=='OK'; otherwise store an error entry.")
    args = parser.parse_args()

    if args.end < args.start:
        print("--end must be >= --start", file=sys.stderr)
        sys.exit(2)

    # Determine base URL
    if args.base_url:
        base_url = args.base_url.rstrip("/")
    else:
        base_url = load_dora_base_url(Path(args.ports_file))

    out_path = Path(args.outfile) if args.outfile else Path(f"data/slots_{args.start}_{args.end}.json")

    results = {}
    meta = {
        "source": "dora",
        "base_url": base_url,
        "start": args.start,
        "end": args.end,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    with requests.Session() as session:
        for slot in range(args.start, args.end + 1):
            res = fetch_slot(session, base_url, slot, args.timeout, args.retries, args.backoff)

            if args.only_data:
                if isinstance(res, dict) and res.get("status") == "OK" and "data" in res:
                    results[str(slot)] = res["data"]
                else:
                    results[str(slot)] = {"error": "request failed or bad status", "raw": res}
            else:
                results[str(slot)] = res

            # Light progress feedback
            if slot % 25 == 0 or slot == args.end:
                print(f"Fetched slot {slot}")

    payload = {"meta": meta, "results": results}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
