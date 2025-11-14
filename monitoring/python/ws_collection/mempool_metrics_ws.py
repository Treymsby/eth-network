#!/usr/bin/env python3
"""
Mempool monitor for multiple Ethereum WebSocket EL endpoints.

- Reads eth-network-services.json: a list of objects like:
    {
      "name": "el-1-geth-lighthouse",
      "uuid": "...",
      "ws": "127.0.0.1:33536",
      "rpc": "127.0.0.1:33535",
      "http": null
    }

- Connects to each EL endpoint (entries where name starts with "el-"
  and 'ws' is a non-empty string) via WebSocket.
- Subscribes to:
    - eth_subscribe "newPendingTransactions"
    - eth_subscribe "newHeads"
- Treats "mempool" as: tx hashes seen in newPendingTransactions that have
  not yet appeared in a block.

Every `interval` seconds (default: 10s), it writes a JSON snapshot line to
the output file (JSON Lines format: one JSON object per line):

{
  "timestamp": "<ISO8601 UTC>",
  "total_mempool_size": <int>,
  "total_new_pending": <int>,           # last interval
  "total_confirmed": <int>,             # last interval
  "total_net_pending_delta": <int>,     # last interval
  "nodes": {
    "<node-name>": {
      "mempool_size": <int>,            # pending tx count
      "new_pending": <int>,             # last interval
      "confirmed": <int>,               # last interval (included in blocks)
      "net_pending_delta": <int>,       # new_pending - confirmed
      "total_seen_pending": <int>,      # since script start
      "total_confirmed": <int>          # since script start
    },
    ...
  }
}

This is an approximate mempool view limited to:
- transactions that hit this node's WS "newPendingTransactions"
- and are later observed in blocks via "newHeads" + eth_getBlockByHash.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Set, Any, Tuple

import websockets


def ts_to_iso(ts: float) -> str:
    """Convert a Unix timestamp (seconds) to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@dataclass
class NodeMempoolState:
    name: str
    pending: Set[str] = field(default_factory=set)
    new_pending_since_last: int = 0
    confirmed_since_last: int = 0
    total_seen_pending: int = 0
    total_confirmed: int = 0

    def snapshot_and_reset_interval(self) -> Dict[str, Any]:
        """Return interval metrics and reset per-interval counters."""
        data = {
            "mempool_size": len(self.pending),
            "new_pending": self.new_pending_since_last,
            "confirmed": self.confirmed_since_last,
            "net_pending_delta": self.new_pending_since_last
            - self.confirmed_since_last,
            "total_seen_pending": self.total_seen_pending,
            "total_confirmed": self.total_confirmed,
        }
        self.new_pending_since_last = 0
        self.confirmed_since_last = 0
        return data


async def monitor_node(
    name: str,
    ws_address: str,
    state: NodeMempoolState,
) -> None:
    """
    Connect to a single WebSocket endpoint and track its mempool.

    - Subscribe to "newPendingTransactions" to grow `state.pending`
    - Subscribe to "newHeads", then fetch full blocks and remove included
      transactions from `state.pending`.
    """
    ws_url = f"ws://{ws_address}"
    print(f"[{name}] Connecting to {ws_url}")

    # Map JSON-RPC id -> (kind, metadata)
    # kind is "block"
    outstanding: Dict[int, Tuple[str, Dict[str, Any]]] = {}

    # IDs: 1 and 2 reserved for subscriptions. Dynamic requests start at 100.
    next_request_id = 100

    def get_request_id() -> int:
        nonlocal next_request_id
        rid = next_request_id
        next_request_id += 1
        return rid

    pending_sub_id = None
    heads_sub_id = None

    try:
        async with websockets.connect(ws_url) as ws:
            # Subscribe to pending txs
            pending_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newPendingTransactions"],
            }
            await ws.send(json.dumps(pending_req))

            # Subscribe to new heads
            heads_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "eth_subscribe",
                "params": ["newHeads"],
            }
            await ws.send(json.dumps(heads_req))

            print(f"[{name}] Subscriptions sent")

            while True:
                raw_msg = await ws.recv()
                msg = json.loads(raw_msg)

                # Handle subscription responses (ids 1 & 2)
                if "id" in msg and "result" in msg:
                    if msg["id"] == 1:
                        pending_sub_id = msg["result"]
                        print(f"[{name}] newPendingTransactions sub id: {pending_sub_id}")
                        continue
                    elif msg["id"] == 2:
                        heads_sub_id = msg["result"]
                        print(f"[{name}] newHeads sub id: {heads_sub_id}")
                        continue

                    # Responses to other JSON-RPC requests (block)
                    req_id = msg["id"]
                    if req_id in outstanding:
                        kind, meta = outstanding.pop(req_id)
                        result = msg.get("result")

                        # ----- Handle full block from eth_getBlockByHash -----
                        if kind == "block" and result:
                            block = result
                            txs = block.get("transactions", []) or []
                            removed_here = 0

                            for tx in txs:
                                tx_hash = (
                                    tx if isinstance(tx, str) else tx.get("hash")
                                )
                                if not tx_hash:
                                    continue
                                if tx_hash in state.pending:
                                    state.pending.remove(tx_hash)
                                    state.confirmed_since_last += 1
                                    state.total_confirmed += 1
                                    removed_here += 1

                            if removed_here:
                                print(
                                    f"[{name}] Removed {removed_here} pending txs "
                                    f"due to new block"
                                )

                    continue  # done with id-handling

                # Handle subscription notifications
                if msg.get("method") == "eth_subscription":
                    params = msg.get("params", {})
                    sub_id = params.get("subscription")
                    result = params.get("result")

                    # Pending transaction seen
                    if pending_sub_id and sub_id == pending_sub_id:
                        # 'result' is a tx hash string
                        tx_hash = result
                        if isinstance(tx_hash, str):
                            if tx_hash not in state.pending:
                                state.pending.add(tx_hash)
                                state.new_pending_since_last += 1
                                state.total_seen_pending += 1

                    # New head seen
                    elif heads_sub_id and sub_id == heads_sub_id:
                        # 'result' is a block header object
                        block = result or {}
                        block_hash = block.get("hash")
                        if not block_hash:
                            continue

                        # Fetch full block (with tx objects or hashes)
                        rid = get_request_id()
                        outstanding[rid] = ("block", {})
                        block_req = {
                            "jsonrpc": "2.0",
                            "id": rid,
                            "method": "eth_getBlockByHash",
                            "params": [block_hash, True],
                        }
                        await ws.send(json.dumps(block_req))

                # Ignore anything else (errors, logs, etc.)

    except asyncio.CancelledError:
        print(f"[{name}] Mempool monitor task cancelled")
        raise
    except Exception as e:
        print(f"[{name}] ERROR: {e}")


async def sampler_task(
    states: Dict[str, NodeMempoolState],
    output_path: Path,
    duration: int,
    interval: float,
) -> None:
    """
    Periodically (every `interval` seconds) take a snapshot of all node states
    and append it as one JSON object (line) to `output_path`.
    """
    start = time.time()

    # Ensure output directory exists
    if output_path.parent:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # open in write mode once; we write a JSON line each interval
    with output_path.open("w") as f:
        while True:
            now = time.time()
            if duration is not None and now - start >= duration:
                break

            snapshot_time = ts_to_iso(now)

            nodes_section: Dict[str, Dict[str, Any]] = {}
            total_mempool_size = 0
            total_new_pending = 0
            total_confirmed = 0
            total_net_delta = 0

            # snapshot and reset per-node interval counters
            for name, state in states.items():
                node_data = state.snapshot_and_reset_interval()
                nodes_section[name] = node_data
                total_mempool_size += node_data["mempool_size"]
                total_new_pending += node_data["new_pending"]
                total_confirmed += node_data["confirmed"]
                total_net_delta += node_data["net_pending_delta"]

            snapshot = {
                "timestamp": snapshot_time,
                "total_mempool_size": total_mempool_size,
                "total_new_pending": total_new_pending,
                "total_confirmed": total_confirmed,
                "total_net_pending_delta": total_net_delta,
                "nodes": nodes_section,
            }

            f.write(json.dumps(snapshot) + "\n")
            f.flush()

            await asyncio.sleep(interval)


async def main_async(args) -> None:
    # Load eth-network-services.json
    services_path = Path(args.ws_file)
    if not services_path.is_file():
        raise FileNotFoundError(f"eth-network-services.json not found at {services_path}")

    with services_path.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected {services_path} to contain a JSON array as in eth-network-services.json"
        )

    # Build endpoints from EL nodes (name starts with "el-") with non-empty ws
    endpoints: Dict[str, str] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        ws_addr = entry.get("ws")

        if not isinstance(name, str) or not name.startswith("el-"):
            continue
        if not isinstance(ws_addr, str) or not ws_addr.strip():
            continue

        endpoints[name] = ws_addr.strip()

    if not endpoints:
        print(
            "No valid EL WebSocket endpoints found in eth-network-services.json "
            "(looked for entries with name starting with 'el-' and non-empty 'ws')."
        )
        return

    print(f"Found {len(endpoints)} EL WebSocket endpoints:")
    for n, a in endpoints.items():
        print(f"  - {n}: {a}")

    # Create NodeMempoolState per node
    states: Dict[str, NodeMempoolState] = {
        name: NodeMempoolState(name=name) for name in endpoints.keys()
    }

    # Start one monitor task per node
    monitor_tasks = [
        asyncio.create_task(monitor_node(name, addr, states[name]))
        for name, addr in endpoints.items()
    ]

    # Start sampler
    out_path = Path(args.output)
    sampler = asyncio.create_task(
        sampler_task(states, out_path, duration=args.duration, interval=args.interval)
    )

    try:
        await sampler
    finally:
        # Stop node monitors
        for t in monitor_tasks:
            t.cancel()
        await asyncio.gather(*monitor_tasks, return_exceptions=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Monitor mempool via Ethereum EL WebSocket endpoints "
        "described in eth-network-services.json and write JSONL snapshots."
    )
    parser.add_argument(
        "--ws-file",
        default="eth-network-services.json",
        help=(
            "Path to eth-network-services.json "
            "(default: eth-network-services.json in current directory)"
        ),
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="How long to run in seconds (default: 60). "
             "Use a large number for longer runs.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Snapshot interval in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--output",
        default="data/mempool_metrics.jsonl",
        help="Output file for JSONL snapshots (default: data/mempool_metrics.jsonl)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Interrupted by user; shutting down.")


if __name__ == "__main__":
    main()
