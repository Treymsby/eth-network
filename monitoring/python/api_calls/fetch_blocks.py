#!/usr/bin/env python3
"""
fetch_blocks.py

Fetch blocks from Blockscout (URL read from ports.json) and save to one JSON file.

- Reads ./ports.json and uses its "blockscout" entry, appending /api/v2/blocks.
- Calls {blockscout_url}/api/v2/blocks/<block_number> for the given range.
- By default writes to /data/blockscout_blocks.json (creates /data if needed).

"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import sys
import requests


def load_blockscout_base_url(ports_file: Path) -> str:
    """Load Blockscout base URL from ports.json and return the /api/v2/blocks base."""
    if not ports_file.exists():
        raise FileNotFoundError(f"ports.json not found at: {ports_file}")
    try:
        ports = json.loads(ports_file.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {ports_file}: {e}") from e

    base = ports.get("blockscout")
    if not isinstance(base, str) or not base:
        raise KeyError(f'"blockscout" key missing or invalid in {ports_file}')
    return base.rstrip("/") + "/api/v2/blocks"


def fetch_block(session: requests.Session, base_url: str, height: int,
                timeout: float, retries: int, backoff: float):
    """Fetch one block with simple exponential-backoff retries."""
    url = f"{base_url.rstrip('/')}/{height}"
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            # Treat 404/other HTTP errors as failures we report in output
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    return {"status": "ERROR", "error": str(last_err), "block": height, "url": url}


def main():
    parser = argparse.ArgumentParser(description="Fetch block data from Blockscout and save to one JSON file.")
    parser.add_argument("--ports-file", default="ports.json", help="Path to ports.json in the project root.")
    parser.add_argument("--base-url", default=None,
                        help="Optional override: full base URL up to /api/v2/blocks "
                             "(e.g. http://127.0.0.1:35009/api/v2/blocks).")
    parser.add_argument("--start", type=int, default=0, help="Start block number (inclusive).")
    parser.add_argument("--end", type=int, default=200, help="End block number (inclusive).")
    parser.add_argument("-o", "--outfile", default=None,
                        help="Output JSON file path.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per block on failure.")
    parser.add_argument("--backoff", type=float, default=0.5, help="Exponential backoff base in seconds.")
    args = parser.parse_args()

    if args.end < args.start:
        print("--end must be >= --start", file=sys.stderr)
        sys.exit(2)

    # Determine base URL
    if args.base_url:
        base_url = args.base_url.rstrip("/")
    else:
        base_url = load_blockscout_base_url(Path(args.ports_file))

    # Default output path: data/blockscout_blocks.json (unless -o provided)
    out_path = Path(args.outfile) if args.outfile else Path(f"data/blocks_{args.start}_{args.end}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = {}
    meta = {
        "source": "blockscout",
        "base_url": base_url,
        "start": args.start,
        "end": args.end,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    with requests.Session() as session:
        for height in range(args.start, args.end + 1):
            res = fetch_block(session, base_url, height, args.timeout, args.retries, args.backoff)
            # Blockscout returns the block object directly; store as-is (or an error dict)
            results[str(height)] = res

            # Light progress feedback
            if height % 25 == 0 or height == args.end:
                print(f"Fetched block {height}")

    payload = {"meta": meta, "results": results}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
