#!/usr/bin/env python3
"""
Fetch per-block transactions from Blockscout and save 1 JSON per block.

Defaults:
- ports.json: ./ports.json
- start block: 0
- end block: 200 (inclusive)
- out dir: ./data/txs_per_block
- rate limit: 10 requests/second

Usage (optional overrides):
  python fetch_block_txs.py --start 1 --end 200 --ports ports.json --out-dir data/txs_per_block --rps 10
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, List, Optional

try:
    import requests
except ImportError:
    print("This script requires the 'requests' package. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class RateLimiter:
    """Simple per-request rate limiter: ensures at most RPS requests per second."""
    def __init__(self, rps: float):
        if rps <= 0:
            raise ValueError("RPS must be > 0")
        self.min_interval = 1.0 / rps
        self._last_time = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_time
        sleep_for = self.min_interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last_time = time.monotonic()


def read_blockscout_base(ports_path: str) -> str:
    if not os.path.exists(ports_path):
        raise FileNotFoundError(f"ports.json not found at: {ports_path}")
    with open(ports_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    base = data.get("blockscout")
    if not base:
        raise KeyError("No 'blockscout' key found in ports.json")
    return str(base).rstrip("/")  # normalize


def robust_get(session: requests.Session, url: str, params: Optional[Dict[str, Any]], limiter: RateLimiter,
               timeout: float = 30.0, max_retries: int = 5) -> requests.Response:
    """
    GET with basic retry/backoff handling for 429/5xx and network errors.
    Respects provided RateLimiter for each HTTP call.
    """
    backoff = 0.5
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            limiter.wait()
            resp = session.get(url, params=params, timeout=timeout)
            # Retry on 429 or 5xx
            if resp.status_code == 429 or (500 <= resp.status_code < 600):
                # If server indicates retry-after, respect (bounded by a few seconds)
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        ra = float(retry_after)
                        time.sleep(min(max(ra, 0.1), 5.0))
                    except ValueError:
                        time.sleep(backoff)
                else:
                    time.sleep(backoff)
                backoff = min(backoff * 2.0, 8.0)
                continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 8.0)
    # If we get here, we failed all retries
    if last_exc:
        raise last_exc
    raise RuntimeError("robust_get failed without exception (unexpected)")


def fetch_block_all_transactions(session: requests.Session, base_url: str, block_number: int,
                                 limiter: RateLimiter) -> Dict[str, Any]:
    """
    Fetch all transactions for a block, following Blockscout v2 pagination (next_page_params).
    Returns a dict with:
      {
        "block": <int>,
        "transactions": [ ... ],   # concatenated items across all pages (if available)
        "page_count": <int>        # how many HTTP calls/pages were fetched
      }
    If the endpoint does not return 'items', falls back to storing raw JSON as 'transactions_raw'.
    """
    endpoint = f"{base_url}/api/v2/blocks/{block_number}/transactions"
    params: Dict[str, Any] = {}
    all_items: List[Any] = []
    page_count = 0

    while True:
        resp = robust_get(session, endpoint, params=params or None, limiter=limiter)
        page_count += 1

        # 404 means the block may not exist yet; return empty structure
        if resp.status_code == 404:
            return {"block": block_number, "transactions": [], "page_count": page_count, "note": "404 Not Found"}

        resp.raise_for_status()
        data = resp.json()

        # Typical v2 response shape has 'items' and 'next_page_params'
        items = data.get("items")
        npp = data.get("next_page_params")

        if items is not None:
            all_items.extend(items)
        else:
            # If no 'items', just return the raw payload
            return {
                "block": block_number,
                "transactions_raw": data,
                "page_count": page_count
            }

        # Continue if server says there are more pages
        if npp:
            # npp should be a dict of query params
            if isinstance(npp, dict):
                params = npp
            else:
                # Fallback: if it's not a dict, store it under a generic cursor
                params = {"cursor": npp}
            continue
        else:
            break

    return {"block": block_number, "transactions": all_items, "page_count": page_count}


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Fetch per-block transactions from Blockscout into JSON files.")
    parser.add_argument("--ports", default="ports.json", help="Path to ports.json (default: ports.json)")
    parser.add_argument("--start", type=int, default=0, help="Start block number (default: 0)")
    parser.add_argument("--end", type=int, default=200, help="End block number, inclusive (default: 200)")
    parser.add_argument("--out-dir", default=os.path.join("data", "txs_per_block"),
                        help="Output directory (default: data/txs_per_block)")
    parser.add_argument("--rps", type=float, default=10.0, help="Max requests per second (default: 10)")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds (default: 30)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    if args.end < args.start:
        print(f"--end ({args.end}) must be >= --start ({args.start})", file=sys.stderr)
        sys.exit(2)

    try:
        base_url = read_blockscout_base(args.ports)
    except Exception as e:
        print(f"Error reading ports.json: {e}", file=sys.stderr)
        sys.exit(2)

    ensure_dir(args.out_dir)

    limiter = RateLimiter(args.rps)
    headers = {
        "Accept": "application/json",
        "User-Agent": "fetch_block_txs/1.0 (+https://blockscout)"
    }

    with requests.Session() as session:
        session.headers.update(headers)

        for block in range(args.start, args.end + 1):
            out_path = os.path.join(args.out_dir, f"{block}.json")
            if os.path.exists(out_path) and not args.overwrite:
                print(f"[skip] {out_path} already exists")
                continue

            try:
                data = fetch_block_all_transactions(session, base_url, block, limiter)
            except requests.HTTPError as e:
                # Keep moving even if a block fails
                print(f"[error] Block {block}: HTTP {getattr(e.response, 'status_code', '?')}: {e}", file=sys.stderr)
                data = {"block": block, "error": str(e)}
            except Exception as e:
                print(f"[error] Block {block}: {e}", file=sys.stderr)
                data = {"block": block, "error": str(e)}

            # Write one JSON per block
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[ok] wrote {out_path} (pages: {data.get('page_count', 1)})")
            except Exception as e:
                print(f"[error] Could not write {out_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
