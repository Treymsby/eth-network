#!/usr/bin/env python3
"""
tx_latency.py — fire 1 EOA transfer per second and log confirmation latency.

Usage examples:
  python tx_latency.py --rpc rpc.json
  python tx_latency.py --rpc rpc.json --tps 1 --count 60 --log data/tx_latency_log.jsonl --value-ether 0

Notes:
- Logs are JSON Lines (one JSON object per line) in the --log file.
- Default transfer value is 0 ether to avoid draining balances (set --value-ether to change).
- Handles both EIP-1559 and legacy gas (falls back automatically).
"""

import argparse
import concurrent.futures
import json
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from web3 import Web3
from eth_account import Account

# ---------------------- Prefunded accounts (from prompt) ----------------------

PRE_FUNDED_ACCOUNTS = [
    {"address": "0x8943545177806ED17B9F23F0a21ee5948eCaa776", "private_key": "bcdf20249abf0ed6d944c0288fad489e33f66b3960d9e6229c1cd214ed3bbe31"},
    {"address": "0xE25583099BA105D9ec0A67f5Ae86D90e50036425", "private_key": "39725efee3fb28614de3bacaffe4cc4bd8c436257e2c8bb887c4b5c4be45e76d"},
    {"address": "0x614561D2d143621E126e87831AEF287678B442b8", "private_key": "53321db7c1e331d93a11a41d16f004d7ff63972ec8ec7c25db329728ceeb1710"},
    {"address": "0xf93Ee4Cf8c6c40b329b0c0626F28333c132CF241", "private_key": "ab63b23eb7941c1251757e24b3d2350d2bc05c3c388d06f8fe6feafefb1e8c70"},
    {"address": "0x802dCbE1B1A97554B4F50DB5119E37E8e7336417", "private_key": "5d2344259f42259f82d2c140aa66102ba89b57b4883ee441a8b312622bd42491"},
    {"address": "0xAe95d8DA9244C37CaC0a3e16BA966a8e852Bb6D6", "private_key": "27515f805127bebad2fb9b183508bdacb8c763da16f54e0678b16e8f28ef3fff"},
    {"address": "0x2c57d1CFC6d5f8E4182a56b4cf75421472eBAEa4", "private_key": "7ff1a4c1d57e5e784d327c4c7651e952350bc271f156afb3d00d20f5ef924856"},
    {"address": "0x741bFE4802cE1C4b5b00F9Df2F5f179A1C89171A", "private_key": "3a91003acaf4c21b3953d94fa4a6db694fa69e5242b2e37be05dd82761058899"},
    {"address": "0xc3913d4D8bAb4914328651C2EAE817C8b78E1f4c", "private_key": "bb1d0f125b4fb2bb173c318cdead45468474ca71474e2247776b2b4c0fa2d3f5"},
    {"address": "0x65D08a056c17Ae13370565B04cF77D2AfA1cB9FA", "private_key": "850643a0224065ecce3882673c21f56bcf6eef86274cc21cadff15930b59fc8c"},
    {"address": "0x3e95dFbBaF6B348396E6674C7871546dCC568e56", "private_key": "94eb3102993b41ec55c241060f47daa0f6372e2e3ad7e91612ae36c364042e44"},
    {"address": "0x5918b2e647464d4743601a865753e64C8059Dc4F", "private_key": "daf15504c22a352648a71ef2926334fe040ac1d5005019e09f6c979808024dc7"},
    {"address": "0x589A698b7b7dA0Bec545177D3963A2741105C7C9", "private_key": "eaba42282ad33c8ef2524f07277c03a776d98ae19f581990ce75becb7cfa1c23"},
    {"address": "0x4d1CB4eB7969f8806E2CaAc0cbbB71f88C8ec413", "private_key": "3fd98b5187bf6526734efaa644ffbb4e3670d66f5d0268ce0323ec09124bff61"},
    {"address": "0xF5504cE2BcC52614F121aff9b93b2001d92715CA", "private_key": "5288e2f440c7f0cb61a9be8afdeb4295f786383f96f5e35eb0c94ef103996b64"},
    {"address": "0xF61E98E7D47aB884C244E39E031978E33162ff4b", "private_key": "f296c7802555da2a5a662be70e078cbd38b44f96f8615ae529da41122ce8db05"},
    {"address": "0xf1424826861ffbbD25405F5145B5E50d0F1bFc90", "private_key": "bf3beef3bd999ba9f2451e06936f0423cd62b815c9233dd3bc90f7e02a1e8673"},
    {"address": "0xfDCe42116f541fc8f7b0776e2B30832bD5621C85", "private_key": "6ecadc396415970e91293726c3f5775225440ea0844ae5616135fd10d66b5954"},
    {"address": "0xD9211042f35968820A3407ac3d80C725f8F75c14", "private_key": "a492823c3e193d6c595f37a18e3c06650cf4c74558cc818b16130b293716106f"},
    {"address": "0xD8F3183DEF51A987222D845be228e0Bbb932C222", "private_key": "c5114526e042343c6d1899cad05e1c00ba588314de9b96929914ee0df18d46b2"},
    {"address": "0xafF0CA253b97e54440965855cec0A8a2E2399896", "private_key": "04b9f63ecf84210c5366c66d68fa1f5da1fa4f634fad6dfc86178e4d79ff9e59"},
]

# --------------------------- Helpers & core logic -----------------------------

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def fmt_duration(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds*1e6:.0f} µs"
    if seconds < 1:
        return f"{seconds*1e3:.1f} ms"
    if seconds < 60:
        return f"{seconds:.3f} s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.1f}s"
    h, rem = divmod(m, 60)
    return f"{int(h)}h {int(rem)}m"

def load_rpc_url(rpc_path: Path) -> str:
    with open(rpc_path, "r") as f:
        data = json.load(f)
    for name, url in data.items():
        if url:
            # ensure http(s) prefix
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://" + url
            return url
    raise RuntimeError("No available RPC URL found in rpc.json")

class JsonlLogger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Touch file
        with open(self.path, "a", encoding="utf-8") as _:
            pass

    def write(self, obj: Dict):
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

def supports_eip1559(w3: Web3) -> bool:
    try:
        latest = w3.eth.get_block("latest")
        return "baseFeePerGas" in latest and latest["baseFeePerGas"] is not None
    except Exception:
        return False

def get_fee_params(w3: Web3) -> Tuple[Dict, bool]:
    """
    Returns (fee_fields, is_dynamic).
    fee_fields is either {'gasPrice': ...} or {'maxFeePerGas': ..., 'maxPriorityFeePerGas': ...}
    """
    if supports_eip1559(w3):
        # Try to fetch priority fee; fall back to a sane default if not available
        try:
            prio = w3.eth.max_priority_fee  # web3 may expose as property
        except Exception:
            try:
                prio = w3.eth.max_priority_fee_per_gas  # some nodes expose this
            except Exception:
                prio = Web3.to_wei(2, "gwei")
        try:
            base = w3.eth.gas_price  # often = base + tip suggestion
        except Exception:
            # As a fallback, pull from block
            base = w3.eth.get_block("latest").get("baseFeePerGas", Web3.to_wei(1, "gwei"))
        # Be generous to avoid underpricing in devnets
        max_fee = int(base + prio * 2)
        return ({"maxFeePerGas": max_fee, "maxPriorityFeePerGas": int(prio)}, True)
    else:
        gas_price = w3.eth.gas_price
        if gas_price == 0:
            gas_price = Web3.to_wei(1, "gwei")
        return ({"gasPrice": int(gas_price)}, False)

def pick_recipients(addresses, sender_addr):
    # simple round-robin/random pick excluding sender
    others = [a for a in addresses if a.lower() != sender_addr.lower()]
    return random.choice(others)

def main():
    parser = argparse.ArgumentParser(description="Send EOA transfers at a fixed TPS and log confirmation latency.")
    parser.add_argument("--rpc", type=Path, default=Path("rpc.json"), help="Path to rpc.json")
    parser.add_argument("--tps", type=float, default=1.0, help="Transactions per second (default 1.0)")
    parser.add_argument("--count", type=int, default=0, help="Number of transactions to send (0 = infinite)")
    parser.add_argument("--log", type=Path, default=Path("data/tx_latency_log.jsonl"), help="Path to JSONL log file")
    parser.add_argument("--value-ether", type=float, default=0.0, help="ETH value to send per tx (default 0)")
    parser.add_argument("--receipt-timeout", type=float, default=120.0, help="Seconds to wait for a tx receipt before giving up")
    parser.add_argument("--sender-index", type=int, default=0, help="Index of the sender in the prefunded list (default 0)")
    args = parser.parse_args()

    if args.tps <= 0:
        print("tps must be > 0", file=sys.stderr)
        sys.exit(1)

    rpc_url = load_rpc_url(args.rpc)
    print(f"Using RPC: {rpc_url}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("ERROR: Could not connect to RPC.", file=sys.stderr)
        sys.exit(2)

    chain_id = w3.eth.chain_id
    print(f"Connected. chainId={chain_id}")

    # Accounts setup
    if args.sender_index < 0 or args.sender_index >= len(PRE_FUNDED_ACCOUNTS):
        print("Invalid --sender-index", file=sys.stderr)
        sys.exit(3)
    sender = PRE_FUNDED_ACCOUNTS[args.sender_index]
    sender_addr = Web3.to_checksum_address(sender["address"])
    sender_key = sender["private_key"]
    if not sender_key.startswith("0x"):
        sender_key = "0x" + sender_key

    all_addresses = [Web3.to_checksum_address(a["address"]) for a in PRE_FUNDED_ACCOUNTS]
    value_wei = Web3.to_wei(args.value_ether, "ether")

    fee_fields, dynamic = get_fee_params(w3)
    print("Fee mode:", "EIP-1559" if dynamic else "legacy")
    logger = JsonlLogger(args.log)

    # Graceful shutdown handling
    stop_flag = threading.Event()

    def handle_sigint(sig, frame):
        print("\nStopping… (Ctrl+C)")
        stop_flag.set()
    signal.signal(signal.SIGINT, handle_sigint)

    # Nonce management for the single sender
    next_nonce = w3.eth.get_transaction_count(sender_addr, block_identifier="pending")

    # Worker to wait for receipts without blocking the sending cadence
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

    pending: Dict[str, Dict] = {}  # tx_hash_hex -> meta (send_time, number)
    pending_lock = threading.Lock()

    def wait_and_log(tx_hash_hex: str, send_time_iso: str, tx_number: int):
        t0 = time.perf_counter()
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=args.receipt_timeout, poll_latency=0.5)
            confirmed_iso = iso_now()
            latency_s = time.perf_counter() - t0
            log_obj = {
                "tx_number": tx_number,
                "tx_time_sent": send_time_iso,
                "tx_time_confirmed": confirmed_iso,
                "tx_confirmation_time": fmt_duration(latency_s),
                "tx_hash": tx_hash_hex,
                "block_number": int(receipt.blockNumber),
                "status": int(receipt.status),
            }
        except Exception as e:
            confirmed_iso = iso_now()
            latency_s = time.perf_counter() - t0
            log_obj = {
                "tx_number": tx_number,
                "tx_time_sent": send_time_iso,
                "tx_time_confirmed": confirmed_iso,
                "tx_confirmation_time": fmt_duration(latency_s),
                "tx_hash": tx_hash_hex,
                "error": str(e),
            }
        logger.write(log_obj)
        with pending_lock:
            pending.pop(tx_hash_hex, None)

    # Sending loop at fixed cadence
    period = 1.0 / args.tps
    tx_counter = 0
    start = time.perf_counter()
    next_deadline = start

    print("Starting send loop. Press Ctrl+C to stop.")
    while not stop_flag.is_set():
        if args.count and tx_counter >= args.count:
            break

        # Maintain cadence
        now = time.perf_counter()
        if now < next_deadline:
            time.sleep(next_deadline - now)
        next_deadline += period

        # Prepare tx
        recipient = pick_recipients(all_addresses, sender_addr)
        tx = {
            "to": recipient,
            "value": value_wei,
            "nonce": next_nonce,
            "chainId": chain_id,
            "gas": 21000,
        }
        tx.update(fee_fields)

        # Sign & send
        signed = Account.sign_transaction(tx, private_key=sender_key)
        try:
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception as e:
            # Log a failed send attempt as well
            send_iso = iso_now()
            tx_counter += 1
            next_nonce += 1  # still bump to avoid nonce reuse loop; adjust if you prefer to retry
            logger.write({
                "tx_number": tx_counter,
                "tx_time_sent": send_iso,
                "tx_time_confirmed": send_iso,
                "tx_confirmation_time": "0 ms",
                "tx_hash": None,
                "error": f"send_failed: {e}",
            })
            print(f"[{tx_counter}] SEND ERROR: {e}", file=sys.stderr)
            continue

        send_iso = iso_now()
        tx_counter += 1
        next_nonce += 1
        tx_hash_hex = tx_hash.hex()

        # Track pending and dispatch receipt waiter
        with pending_lock:
            pending[tx_hash_hex] = {"send_time": send_iso, "number": tx_counter}
        executor.submit(wait_and_log, tx_hash_hex, send_iso, tx_counter)

        print(f"[{tx_counter}] sent -> {tx_hash_hex}  to {recipient}  at {send_iso}")

    # Draining pending confirmations before exit
    print("Draining pending confirmations…")
    while True:
        with pending_lock:
            if not pending:
                break
        time.sleep(0.1)

    executor.shutdown(wait=True)
    print(f"Done. Wrote JSONL logs to: {args.log.resolve()}")

if __name__ == "__main__":
    main()
