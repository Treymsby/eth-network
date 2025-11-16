#!/usr/bin/env python3
"""
Monitor Ethereum WebSocket endpoints from ws.json and
record transaction latency + gas/fee + type details.

This version connects to **one** node at a time. If the connection
to that node fails or the monitor task stops, it automatically
fails over to the next node in the ws.json list.

The script streams results directly to a JSON file instead of
keeping everything in memory. Transactions are written in batches
of 100 records to reduce memory usage.

JSON output layout (single JSON array, one object per transaction):

[
  {
    "node": "<node-name>",

    "tx": {
      "hash": "<tx-hash>",
      "block_number": <int>,
      "index_in_block": <int or null>,
      "global_sequence": <int>,        # global counter across all nodes
      "encoding_type": "<legacy|eip1559|blob|...>",
      "categories": ["coin_transfer", "contract_call", "token_transfer", ...],
      "success": <bool>
    },

    "time": {
      "first_seen_utc": "<ISO8601>",
      "confirmed_utc": "<ISO8601>",
      "latency_ms": <int>
    },

    "gas": {
      "used": <int or null>,
      "limit": <int or null>,
      "effective_price": <int or null>,
      "max_fee_per_gas": <int or null>,
      "base_fee_per_gas": <int or null>,
      "priority_fee_per_gas": <int or null>
    }
  },
  ...
]
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import websockets

# ERC-20 / ERC-721 Transfer event topic:
# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


def ts_to_iso(ts: float) -> str:
    """Convert a Unix timestamp (seconds) to an ISO 8601 string in UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def hex_to_int(value: Any) -> Optional[int]:
    """Convert a hex string like '0xabc' to int, or return None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith(("0x", "0X")):
            return int(value, 16)
        if value.isdigit():
            return int(value)
    return None


def classify_tx_type(raw_type: Any) -> str:
    """
    Map the 'type' field to a friendly label:

    - missing / 0x0 -> legacy
    - 0x1           -> access_list
    - 0x2           -> eip1559
    - 0x3           -> blob (EIP-4844)
    - other         -> unknown-<int>
    """
    if raw_type is None:
        return "legacy"

    t_int = hex_to_int(raw_type)
    if t_int is None:
        return f"unknown-{raw_type}"

    if t_int == 0:
        return "legacy"
    if t_int == 1:
        return "access_list"
    if t_int == 2:
        return "eip1559"
    if t_int == 3:
        return "blob"  # EIP-4844 blob txs

    return f"unknown-{t_int}"


async def json_writer(
    path: Path,
    queue: "asyncio.Queue",
    flush_every: int = 100,
) -> int:
    """
    Consume transaction records from `queue` and stream them to `path` as
    a single JSON array. Flush to disk every `flush_every` txs.

    Special value `None` from the queue signals that no more records will
    be produced and the JSON array should be closed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    first = True
    batch: List[Dict[str, Any]] = []

    with path.open("w") as f:
        f.write("[\n")
        while True:
            item = await queue.get()
            try:
                if item is None:
                    # Flush remaining batch, close array and exit
                    if batch:
                        for rec in batch:
                            if not first:
                                f.write(",\n")
                            json.dump(rec, f)
                            first = False
                            written += 1
                        batch.clear()
                    f.write("\n]\n")
                    f.flush()
                    break

                # Normal record
                batch.append(item)

                if len(batch) >= flush_every:
                    for rec in batch:
                        if not first:
                            f.write(",\n")
                        json.dump(rec, f)
                        first = False
                        written += 1
                    f.flush()
                    batch.clear()
            finally:
                queue.task_done()

    return written


async def monitor_node(
    name: str,
    ws_address: str,
    queue: "asyncio.Queue",
    global_counter: Dict[str, int],
) -> None:
    """
    Connect to a single WebSocket endpoint and monitor pending tx -> confirmed tx.

    - name: logical name of the node
    - ws_address: "host:port" from ws.json
    - queue: shared asyncio.Queue to put transaction records into
    - global_counter: shared dict with key "value" as global tx counter
    """
    ws_url = f"ws://{ws_address}"
    print(f"[{name}] Connecting to {ws_url}")

    # Map tx_hash -> first_seen_timestamp (float seconds since epoch)
    pending_seen: Dict[str, float] = {}

    # Map JSON-RPC id -> (kind, metadata)
    # kind is "block" or "receipt"
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
        # Disable max_size limit so large messages don't trigger 1009
        async with websockets.connect(ws_url, max_size=None) as ws:
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

                    # Responses to other JSON-RPC requests (block / receipt)
                    req_id = msg["id"]
                    if req_id in outstanding:
                        kind, meta = outstanding.pop(req_id)
                        result = msg.get("result")

                        # ----- Handle full block from eth_getBlockByHash -----
                        if kind == "block" and result:
                            block = result
                            block_number_hex = block.get("number")
                            if block_number_hex is None:
                                continue
                            block_number = int(block_number_hex, 16)

                            base_fee_hex = block.get("baseFeePerGas")
                            block_base_fee = base_fee_hex  # hex string; convert later

                            txs = block.get("transactions", []) or []

                            for tx in txs:
                                tx_hash = tx.get("hash")
                                if not tx_hash:
                                    continue
                                if tx_hash not in pending_seen:
                                    # We never saw this tx as pending during our run
                                    continue

                                send_ts = pending_seen.pop(tx_hash)
                                tx_index_hex = tx.get("transactionIndex")
                                tx_index = (
                                    int(tx_index_hex, 16)
                                    if tx_index_hex is not None
                                    else None
                                )

                                rid = get_request_id()
                                outstanding[rid] = (
                                    "receipt",
                                    {
                                        "node_name": meta["node_name"],
                                        "tx_hash": tx_hash,
                                        "transaction_number_in_block": tx_index,
                                        "tx_type_raw": tx.get("type"),
                                        "gas": tx.get("gas"),
                                        "gasPrice": tx.get("gasPrice"),
                                        "maxFeePerGas": tx.get("maxFeePerGas"),
                                        "maxPriorityFeePerGas": tx.get(
                                            "maxPriorityFeePerGas"
                                        ),
                                        "value": tx.get("value"),
                                        "input": tx.get("input"),
                                        "to": tx.get("to"),
                                        "block_number": block_number,
                                        "block_base_fee": block_base_fee,
                                        "send_ts": send_ts,
                                    },
                                )
                                receipt_req = {
                                    "jsonrpc": "2.0",
                                    "id": rid,
                                    "method": "eth_getTransactionReceipt",
                                    "params": [tx_hash],
                                }
                                await ws.send(json.dumps(receipt_req))

                        # ----- Handle receipt from eth_getTransactionReceipt -----
                        elif kind == "receipt":
                            meta = dict(meta)  # copy
                            receipt = result or {}

                            status = receipt.get("status")
                            success = status == "0x1"

                            confirm_ts = time.time()
                            send_ts = meta["send_ts"]
                            latency_ms = int((confirm_ts - send_ts) * 1000)

                            # Gas & fee details
                            gas_used = hex_to_int(receipt.get("gasUsed"))
                            gas_limit = hex_to_int(meta.get("gas"))

                            effective_gas_price = hex_to_int(
                                receipt.get("effectiveGasPrice")
                                or meta.get("gasPrice")
                            )
                            max_fee_per_gas = hex_to_int(
                                meta.get("maxFeePerGas") or meta.get("gasPrice")
                            )
                            base_fee_per_gas = hex_to_int(meta.get("block_base_fee"))

                            if (
                                effective_gas_price is not None
                                and base_fee_per_gas is not None
                            ):
                                priority_fee_per_gas = max(
                                    effective_gas_price - base_fee_per_gas, 0
                                )
                            else:
                                priority_fee_per_gas = None

                            # ----- Transaction types classification -----
                            value_int = hex_to_int(meta.get("value"))
                            input_data = meta.get("input") or "0x"
                            to_addr = meta.get("to")
                            logs = receipt.get("logs") or []

                            transaction_types: List[str] = []

                            # Simple ETH transfer (no data, just value)
                            if value_int is not None and value_int > 0:
                                if input_data in ("0x", "0x0", ""):
                                    transaction_types.append("coin_transfer")

                            # Contract call (any tx with non-empty input to a non-null address)
                            if input_data not in ("0x", "0x0", "") and to_addr:
                                transaction_types.append("contract_call")

                            # Token transfer if Transfer(address,address,uint256) event emitted
                            for log in logs:
                                topics = log.get("topics") or []
                                if not topics:
                                    continue
                                topic0 = topics[0]
                                if isinstance(topic0, str) and topic0.lower() == TRANSFER_TOPIC.lower():
                                    transaction_types.append("token_transfer")
                                    break

                            if not transaction_types:
                                transaction_types.append("other")

                            tx_type_label = classify_tx_type(meta.get("tx_type_raw"))

                            # ---- Global tx counter ----
                            global_counter["value"] += 1
                            total_tx_number = global_counter["value"]

                            # ---- Build new JSON layout record ----
                            record = {
                                "node": meta["node_name"],
                                "tx": {
                                    "hash": meta["tx_hash"],
                                    "block_number": meta["block_number"],
                                    "index_in_block": meta[
                                        "transaction_number_in_block"
                                    ],
                                    "global_sequence": total_tx_number,
                                    "encoding_type": tx_type_label,
                                    "categories": transaction_types,
                                    "success": success,
                                },
                                "time": {
                                    "first_seen_utc": ts_to_iso(send_ts),
                                    "confirmed_utc": ts_to_iso(confirm_ts),
                                    "latency_ms": latency_ms,
                                },
                                "gas": {
                                    "used": gas_used,
                                    "limit": gas_limit,
                                    "effective_price": effective_gas_price,
                                    "max_fee_per_gas": max_fee_per_gas,
                                    "base_fee_per_gas": base_fee_per_gas,
                                    "priority_fee_per_gas": priority_fee_per_gas,
                                },
                            }

                            # Push record to writer queue (streaming to disk)
                            await queue.put(record)

                            print(
                                f"[{meta['node_name']}] tx {meta['tx_hash']} "
                                f"block {meta['block_number']} "
                                f"type={tx_type_label} "
                                f"types={transaction_types} "
                                f"success={success} latency={latency_ms}ms "
                                f"global_tx={total_tx_number}"
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
                        now = time.time()
                        # Keep first time we saw it
                        pending_seen.setdefault(tx_hash, now)

                    # New head seen
                    elif heads_sub_id and sub_id == heads_sub_id:
                        # 'result' is a block header object
                        block = result or {}
                        block_hash = block.get("hash")
                        if not block_hash:
                            continue

                        # Fetch full block (with tx objects)
                        rid = get_request_id()
                        outstanding[rid] = ("block", {"node_name": name})
                        block_req = {
                            "jsonrpc": "2.0",
                            "id": rid,
                            "method": "eth_getBlockByHash",
                            "params": [block_hash, True],
                        }
                        await ws.send(json.dumps(block_req))

                # Ignore anything else (errors, logs, etc.)

    except asyncio.CancelledError:
        print(f"[{name}] Monitor task cancelled")
        raise
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[{name}] Connection closed: code={e.code} reason={e.reason}")
    except Exception as e:
        print(f"[{name}] ERROR: {e}")


async def monitor_with_failover(
    endpoints: Dict[str, str],
    queue: "asyncio.Queue",
    global_counter: Dict[str, int],
    duration: int,
) -> None:
    """
    Run monitor_node on exactly one endpoint at a time.

    If the current monitor task exits (connection error, unexpected stop,
    etc.), automatically switch to the next endpoint in `endpoints`.

    This loop continues until `duration` seconds have elapsed.
    """
    if not endpoints:
        print("No endpoints provided to monitor_with_failover()")
        return

    endpoint_items: List[Tuple[str, str]] = list(endpoints.items())
    idx = 0

    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration

    current_task: Optional[asyncio.Task] = None
    current_name: Optional[str] = None

    print(
        f"Starting failover monitoring over {len(endpoint_items)} endpoints "
        f"for ~{duration} seconds"
    )

    try:
        while True:
            now = loop.time()
            remaining = end_time - now
            if remaining <= 0:
                print("Monitoring duration elapsed, stopping failover loop.")
                break

            # If no task is running or the current one finished, start/rotate
            if current_task is None or current_task.done():
                if current_task is not None:
                    # Consume exception so it doesn't get reported as "never retrieved"
                    try:
                        _ = current_task.exception()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(
                            f"[failover] Previous monitor task for {current_name} "
                            f"ended with error: {e}"
                        )

                name, addr = endpoint_items[idx]
                idx = (idx + 1) % len(endpoint_items)
                current_name = name
                print(f"[failover] Switching to endpoint {name} ({addr})")
                current_task = asyncio.create_task(
                    monitor_node(name, addr, queue, global_counter)
                )

            # Sleep a bit, but not past the overall end_time
            await asyncio.sleep(min(1.0, max(0.1, remaining)))
    finally:
        if current_task and not current_task.done():
            print(f"[failover] Cancelling monitor task for {current_name}")
            current_task.cancel()
            await asyncio.gather(current_task, return_exceptions=True)


async def main_async(args: argparse.Namespace) -> int:
    # Load ws.json (new format: list of objects with "name" and "ws")
    ws_path = Path(args.ws_file)
    if not ws_path.is_file():
        raise FileNotFoundError(f"ws.json not found at {ws_path}")

    with ws_path.open() as f:
        ws_data = json.load(f)

    if not isinstance(ws_data, list):
        raise ValueError("ws.json must be a JSON array of objects")

    # Extract only EL nodes (name starts with "el-") that have a non-empty ws field
    endpoints: Dict[str, str] = {}
    for entry in ws_data:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        ws_addr = entry.get("ws")

        if (
            isinstance(name, str)
            and name.startswith("el-")
            and isinstance(ws_addr, str)
            and ws_addr.strip()
        ):
            endpoints[name] = ws_addr.strip()

    if not endpoints:
        print("No valid EL WebSocket endpoints found in ws.json")
        return 0

    print(f"Found {len(endpoints)} WebSocket endpoints: {', '.join(endpoints.keys())}")

    # shared global counter across all nodes
    global_counter = {"value": 0}

    out_path = Path(args.output)
    queue: asyncio.Queue = asyncio.Queue()

    # Start the JSON writer
    writer_task = asyncio.create_task(
        json_writer(out_path, queue, flush_every=100)
    )

    # Run a single monitor at a time, with automatic failover
    await monitor_with_failover(endpoints, queue, global_counter, args.duration)

    # Signal writer that no more records will arrive
    await queue.put(None)
    # Wait for writer to finish closing the file
    total_written = await writer_task

    return total_written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Ethereum WebSocket endpoints from ws.json "
        "and record transaction latency + gas/fee + type data."
    )
    parser.add_argument(
        "--ws-file",
        default="eth-network-services.json",
        help="Path to ws.json (default: ws.json in current directory)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Monitoring duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--output",
        default="data/tx_metrics.json",
        help="Output JSON file for collected metrics (default: data/tx_metrics.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        total_records = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(
            "Interrupted by user. Output file may contain partial JSON "
            "(missing closing bracket)."
        )
        return

    print(f"Saved {total_records} transaction records to {args.output}")


if __name__ == "__main__":
    main()
