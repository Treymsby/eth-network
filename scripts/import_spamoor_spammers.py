#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import requests


TASK_URLS = {
    "bigblock": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/bigblock-tasks.yaml",
    "highcompute": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/highcompute-tasks.yaml",
    "highgas": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/highgas-task.yaml",
    "max-tx": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/max-tx-tasks.yaml",
}


def load_spamoor_url(ports_file: Path) -> str:
    """Read ports.json and return the spamoor base URL."""
    if not ports_file.is_file():
        raise FileNotFoundError(f"ports file not found: {ports_file}")

    with ports_file.open("r", encoding="utf-8") as f:
        ports = json.load(f)

    # key is "spamoor" in your example
    try:
        base_url = ports["spamoor"]
    except KeyError:
        raise KeyError('"spamoor" key not found in ports.json')

    # strip trailing slash if any
    return base_url.rstrip("/")


def post_json(url: str, payload: dict):
    """Helper to POST JSON and print status."""
    print(f"[POST] {url}  payload={payload}")
    try:
        resp = requests.post(url, json=payload, headers={"accept": "application/json"})
    except requests.RequestException as e:
        print(f"  ERROR: request failed: {e}")
        return None

    print(f"  -> status {resp.status_code}")
    if resp.content:
        try:
            print(f"  response JSON: {resp.json()}")
        except ValueError:
            print(f"  response text: {resp.text[:500]}")
    return resp


def simple_post(url: str):
    """Helper to POST with no body."""
    print(f"[POST] {url}")
    try:
        resp = requests.post(url, headers={"accept": "application/json"})
    except requests.RequestException as e:
        print(f"  ERROR: request failed: {e}")
        return None

    print(f"  -> status {resp.status_code}")
    if resp.content:
        try:
            print(f"  response JSON: {resp.json()}")
        except ValueError:
            print(f"  response text: {resp.text[:500]}")
    return resp


def main():
    parser = argparse.ArgumentParser(
        description="Control spamoor via its HTTP API using ports.json"
    )
    parser.add_argument(
        "--ports-file",
        default="ports.json",
        help="Path to ports.json (default: ports.json)",
    )
    parser.add_argument(
        "--import",
        dest="imports",
        nargs="+",
        choices=TASK_URLS.keys(),
        metavar="TASK",
        help=(
            "Which spamoor task(s) to import. "
            "Choices: bigblock, highcompute, highgas, max-tx. "
            "You can specify more than one."
        ),
    )
    parser.add_argument(
        "--no-timers",
        action="store_true",
        help="If set, only perform imports and skip the 384s start/pause sequence.",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=384,
        help="Delay (in seconds) between actions, default: 384",
    )

    args = parser.parse_args()

    ports_file = Path(args.ports_file)
    base_url = load_spamoor_url(ports_file)
    print(f"Using spamoor base URL: {base_url}")

    # 1) Run imports (if any)
    if args.imports:
        for task_name in args.imports:
            task_url = TASK_URLS[task_name]
            print(f"\n=== Importing task '{task_name}' ===")
            import_url = f"{base_url}/api/spammers/import"
            payload = {"input": task_url}
            post_json(import_url, payload)
    else:
        print("No --import TASK specified; skipping import step.")

    if args.no_timers:
        print("\n--no-timers specified, skipping start/pause sequence.")
        return

    # 2) After delay, start spammer 102
    print(f"\nWaiting {args.delay} seconds before starting spammer 102...")
    time.sleep(args.delay)

    start_url = f"{base_url}/api/spammer/102/start"
    print("\n=== Starting spammer 102 ===")
    simple_post(start_url)

    # 3) After another delay, pause spammers 100, 101, 102
    print(f"\nWaiting another {args.delay} seconds before pausing 100, 101, 102...")
    time.sleep(args.delay)

    print("\n=== Pausing spammers 100, 101, 102 ===")
    for spammer_id in (100, 101, 102):
        pause_url = f"{base_url}/api/spammer/{spammer_id}/pause"
        simple_post(pause_url)


if __name__ == "__main__":
    main()
