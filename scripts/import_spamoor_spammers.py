#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import requests

"""
python spamoor_script.py --import bigblock
python spamoor_script.py --import highcompute
python spamoor_script.py --import highgas
python spamoor_script.py --import max-tx
"""
PORTS_DEFAULT_PATH = "ports.json"

SPAMMER_CTRL_BASE = "http://127.0.0.1:32829/api/spammer"
SLEEP_SECONDS = 384

IMPORT_URLS = {
    "bigblock": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/bigblock-tasks.yaml",
    "highcompute": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/highcompute-tasks.yaml",
    "highgas": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/highgas-task.yaml",
    "max-tx": "https://raw.githubusercontent.com/Treymsby/eth-network/refs/heads/main/spammer_scripts/contracts/spamoor/max-tx-tasks.yaml",
}


def load_ports(ports_path: str) -> dict:
    path = Path(ports_path)
    if not path.is_file():
        raise FileNotFoundError(f"ports.json not found at: {path.resolve()}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_spamoor_url(ports: dict) -> str:
    try:
        base = ports["spamoor"]
    except KeyError:
        raise KeyError("Key 'spamoor' not found in ports.json")

    # Ensure no trailing slash
    return base.rstrip("/")


def import_spammer_tasks(spamoor_base: str, import_name: str) -> None:
    if import_name not in IMPORT_URLS:
        raise ValueError(f"Unknown import '{import_name}'. "
                         f"Expected one of: {', '.join(IMPORT_URLS)}")

    import_url = IMPORT_URLS[import_name]
    endpoint = f"{spamoor_base}/api/spammers/import"
    payload = {"input": import_url}

    print(f"[+] Importing '{import_name}' tasks via {endpoint}")
    print(f"    input: {import_url}")

    resp = requests.post(
        endpoint,
        json=payload,
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Import request failed ({resp.status_code}): {resp.text}"
        )

    print(f"[+] Import successful: {resp.status_code}")
    try:
        print("    Response:", resp.json())
    except Exception:
        print("    Response (raw):", resp.text)


def spammer_post(path: str) -> None:
    """Helper to POST to the spammer control API."""
    url = f"{SPAMMER_CTRL_BASE}/{path.lstrip('/')}"
    print(f"[+] POST {url}")
    resp = requests.post(url, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Request to {url} failed ({resp.status_code}): {resp.text}"
        )
    try:
        print("    Response:", resp.json())
    except Exception:
        print("    Response (raw):", resp.text)


def main():
    parser = argparse.ArgumentParser(
        description="Import spamoor tasks and control spammers."
    )
    parser.add_argument(
        "--ports",
        default=PORTS_DEFAULT_PATH,
        help="Path to ports.json (default: ports.json)",
    )
    parser.add_argument(
        "--import",
        dest="import_name",
        choices=list(IMPORT_URLS.keys()),
        required=True,
        help="Which task set to import "
             "(bigblock | highcompute | highgas | max-tx)",
    )

    args = parser.parse_args()

    # 1) Load ports.json and get spamoor URL
    print(f"[+] Loading ports from: {args.ports}")
    ports = load_ports(args.ports)
    spamoor_base = get_spamoor_url(ports)
    print(f"[+] spamoor base URL: {spamoor_base}")

    # 2) Import selected spammer tasks
    import_spammer_tasks(spamoor_base, args.import_name)

    # 3) Wait 384 seconds, then start spammer 102
    print(f"[+] Sleeping {SLEEP_SECONDS} seconds before starting spammer 102...")
    time.sleep(SLEEP_SECONDS)
    spammer_post("102/start")

    # 4) Wait another 384 seconds, then pause 100, 101, 102
    print(f"[+] Sleeping another {SLEEP_SECONDS} seconds before pausing 100, 101, 102...")
    time.sleep(SLEEP_SECONDS)
    for spammer_id in (100, 101, 102):
        spammer_post(f"{spammer_id}/pause")

    print("[+] Done.")


if __name__ == "__main__":
    main()
