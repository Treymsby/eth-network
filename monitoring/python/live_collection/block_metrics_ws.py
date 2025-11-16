#!/usr/bin/env python3
"""
Monitor Ethereum blocks via WebSocket endpoints from eth-network-services.json and
record per-block metrics to a JSON file *incrementally*.

This version connects to exactly one node at a time.
If the connection to that node fails or the monitor task stops,
it automatically fails over to the next node in the list.

JSON layout (one object per block inside a single top-level JSON array):

{
  "block_number": int,
  "hash": str,
  "timestamp": ISO-8601 UTC string,

  "block": {
    "size_kb": float | null,
    "gas": {
      "used": int,
      "limit": int,
      "used_percentage": float
    }
  },

  "transactions": {
    "count": int,
    "success": {
      "successful": int,
      "failed": int,
      "success_rate_percent": float
    },
    "fees": {
      "total_wei": int
    }
  }
}

Data is *streamed* to disk via JsonBlockWriter, which flushes buffered
records whenever the accumulated transactions in the buffer reach
--flush-tx-count (default: 100).
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import websockets


def ts_to_iso(ts: int | float) -> str:
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


class JsonBlockWriter:
    """
    Stream block records to a JSON file as a single top-level array.

    - Buffer records in memory.
    - Flush to disk when the buffered records cover at least `flush_tx_count`
      transactions (sum of record["transactions"]["count"]).
    """

    def __init__(self, path: Path, flush_tx_count: int = 100) -> None:
        self.path = path
        self.flush_tx_count = flush_tx_count

        self.buffer: List[Dict[str, Any]] = []
        self.buffer_tx: int = 0

        self.total_blocks: int = 0
        self.total_txs: int = 0

        # Ensure output directory exists
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Open file and start JSON array
        self._fh = path.open("w", encoding="utf-8")
        self._fh.write("[\n")
        self._first = True

    def add_record(self, record: Dict[str, Any]) -> None:
        """Add a single block record and flush if needed."""
        tx_count = int(record.get("transactions", {}).get("count", 0))

        self.buffer.append(record)
        self.buffer_tx += tx_count

        self.total_blocks += 1
        self.total_txs += tx_count

        if self.buffer_tx >= self.flush_tx_count:
            self.flush()

    def flush(self) -> None:
        """Write buffered records to disk."""
        if not self.buffer:
            return

        for rec in self.buffer:
            if not self._first:
                self._fh.write(",\n")
            json.dump(rec, self._fh, separators=(",", ":"))
            self._first = False

        self.buffer.clear()
        self.buffer_tx = 0
        self._fh.flush()

    def close(self) -> None:
        """Flush any remaining records and close the JSON array/file."""
        if self.buffer:
            self.flush()
        self._fh.write("\n]\n")
        self._fh.close()


def build_block_record(agg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a per-block aggregation dict into the final JSON record layout.

    Expected keys in `agg`:
      - block_hash
      - block_number
      - block_time_iso
      - block_size_kb
      - gas_used
      - gas_limit
      - total_transactions
      - success_count
      - fee_total_wei
    """
    gas_used = agg["gas_used"]
    gas_limit = agg["gas_limit"]
    total_tx = agg["total_transactions"]
    success_count = agg.get("success_count", 0)
    fee_total_wei = agg["fee_total_wei"]

    gas_used_percentage = (gas_used / gas_limit * 100.0) if gas_limit > 0 else 0.0
    if total_tx > 0:
        success_rate = success_count / total_tx * 100.0
    else:
        success_rate = 0.0

    failed_count = max(total_tx - success_count, 0)

    return {
        "block_number": agg["block_number"],
        "hash": agg["block_hash"],
        "timestamp": agg["block_time_iso"],
        "block": {
            "size_kb": agg["block_size_kb"],
            "gas": {
                "used": gas_used,
                "limit": gas_limit,
                "used_percentage": gas_used_percentage,
            },
        },
        "transactions": {
            "count": total_tx,
            "success": {
                "successful": success_count,
                "failed": failed_count,
                "success_rate_percent": success_rate,
            },
            "fees": {
                "total_wei": fee_total_wei,
            },
        },
    }


async def monitor_node(
    name: str,
    ws_address: str,
    writer: JsonBlockWriter,
) -> None:
    """
    Connect to a single WebSocket endpoint and record per-block metrics.

    - name: logical name of the node, used only for logs
    - ws_address: "host:port" from eth-network-services.json
    - writer: JsonBlockWriter instance for streaming results to disk
    """
    ws_url = f"ws://{ws_address}"
    print(f"[{name}] Connecting to {ws_url}")

    # JSON-RPC outstanding requests: id -> (kind, metadata)
    # kind is "block" or "receipt"
    outstanding: Dict[int, Tuple[str, Dict[str, Any]]] = {}

    # Per-block aggregation, keyed by block_hash
    blocks_in_progress: Dict[str, Dict[str, Any]] = {}

    # IDs: 1 reserved for newHeads subscription. Others start at 100.
    next_request_id = 100

    def get_request_id() -> int:
        nonlocal next_request_id
        rid = next_request_id
        next_request_id += 1
        return rid

    heads_sub_id = None

    try:
        async with websockets.connect(ws_url) as ws:
            # Subscribe to new heads
            heads_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": ["newHeads"],
            }
            await ws.send(json.dumps(heads_req))

            print(f"[{name}] newHeads subscription sent")

            while True:
                raw_msg = await ws.recv()
                msg = json.loads(raw_msg)

                # --- Handle responses to our JSON-RPC requests ---
                if "id" in msg and "result" in msg:
                    if msg["id"] == 1:
                        # newHeads subscription confirmation
                        heads_sub_id = msg["result"]
                        print(f"[{name}] newHeads sub id: {heads_sub_id}")
                        continue

                    req_id = msg["id"]
                    if req_id in outstanding:
                        kind, meta = outstanding.pop(req_id)
                        result = msg.get("result")

                        # ----- Full block from eth_getBlockByHash -----
                        if kind == "block" and result:
                            block = result
                            block_hash = block.get("hash")
                            if not block_hash:
                                continue

                            block_number_hex = block.get("number")
                            if block_number_hex is None:
                                continue
                            block_number = int(block_number_hex, 16)

                            ts_hex = block.get("timestamp")
                            ts_int = hex_to_int(ts_hex) or 0
                            block_time_iso = ts_to_iso(ts_int)

                            size_bytes = hex_to_int(block.get("size"))
                            block_size_kb = (
                                float(size_bytes) / 1024.0
                                if size_bytes is not None
                                else None
                            )

                            gas_used = hex_to_int(block.get("gasUsed")) or 0
                            gas_limit = hex_to_int(block.get("gasLimit")) or 0

                            txs = block.get("transactions", []) or []
                            total_tx = len(txs)

                            # Create aggregator for this block
                            agg = {
                                "block_hash": block_hash,
                                "block_number": block_number,
                                "block_time_iso": block_time_iso,
                                "block_size_kb": block_size_kb,
                                "gas_used": gas_used,
                                "gas_limit": gas_limit,
                                "total_transactions": total_tx,
                                "pending_receipts": total_tx,
                                "success_count": 0,
                                "fee_total_wei": 0,
                            }
                            blocks_in_progress[block_hash] = agg

                            if total_tx == 0:
                                # No tx, finalize immediately
                                record = build_block_record(agg)
                                writer.add_record(record)

                                print(
                                    f"[{name}] block {block_number} "
                                    f"(no tx, gas_used%="
                                    f"{record['block']['gas']['used_percentage']:.2f})"
                                )
                                blocks_in_progress.pop(block_hash, None)
                            else:
                                # Request receipts for each tx
                                for tx in txs:
                                    tx_hash = tx.get("hash")
                                    if not tx_hash:
                                        continue
                                    rid = get_request_id()
                                    outstanding[rid] = (
                                        "receipt",
                                        {
                                            "block_hash": block_hash,
                                        },
                                    )
                                    receipt_req = {
                                        "jsonrpc": "2.0",
                                        "id": rid,
                                        "method": "eth_getTransactionReceipt",
                                        "params": [tx_hash],
                                    }
                                    await ws.send(json.dumps(receipt_req))

                        # ----- Receipt from eth_getTransactionReceipt -----
                        elif kind == "receipt" and result:
                            meta = dict(meta)
                            block_hash = meta["block_hash"]
                            agg = blocks_in_progress.get(block_hash)
                            if not agg:
                                # Block already finalized or unknown; skip
                                continue

                            receipt = result
                            status = receipt.get("status")
                            success = status == "0x1"

                            gas_used_tx = hex_to_int(receipt.get("gasUsed")) or 0
                            effective_gas_price = hex_to_int(
                                receipt.get("effectiveGasPrice")
                                or receipt.get("gasPrice")
                            ) or 0

                            fee = gas_used_tx * effective_gas_price

                            if success:
                                agg["success_count"] += 1
                            agg["fee_total_wei"] += fee
                            agg["pending_receipts"] -= 1

                            # All receipts for this block collected?
                            if agg["pending_receipts"] <= 0:
                                block_number = agg["block_number"]
                                total_tx = agg["total_transactions"]

                                record = build_block_record(agg)
                                writer.add_record(record)

                                gas_used_pct = record["block"]["gas"]["used_percentage"]
                                success_rate = record["transactions"]["success"][
                                    "success_rate_percent"
                                ]

                                print(
                                    f"[{name}] block {block_number} "
                                    f"txs={total_tx} "
                                    f"gas_used%={gas_used_pct:.2f} "
                                    f"success_rate={success_rate:.2f}%"
                                )

                                # Remove aggregator
                                blocks_in_progress.pop(block_hash, None)

                    continue  # done with id-handling

                # --- Handle subscription notifications (newHeads) ---
                if msg.get("method") == "eth_subscription":
                    params = msg.get("params", {})
                    sub_id = params.get("subscription")
                    result = params.get("result")

                    if heads_sub_id and sub_id == heads_sub_id:
                        # result is a block header object
                        block = result or {}
                        block_hash = block.get("hash")
                        if not block_hash:
                            continue

                        # Fetch full block (with tx objects)
                        rid = get_request_id()
                        outstanding[rid] = ("block", {})
                        block_req = {
                            "jsonrpc": "2.0",
                            "id": rid,
                            "method": "eth_getBlockByHash",
                            "params": [block_hash, True],
                        }
                        await ws.send(json.dumps(block_req))

                # Ignore other notifications/errors

    except asyncio.CancelledError:
        print(f"[{name}] Monitor task cancelled")
        raise
    except Exception as e:
        print(f"[{name}] ERROR: {e}")


async def monitor_with_failover(
    endpoints: List[Tuple[str, str]],
    writer: JsonBlockWriter,
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

    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration

    idx = 0
    current_task: Optional[asyncio.Task] = None
    current_name: Optional[str] = None

    print(
        f"Starting failover monitoring over {len(endpoints)} endpoints "
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

                name, addr = endpoints[idx]
                idx = (idx + 1) % len(endpoints)
                current_name = name
                print(f"[failover] Switching to endpoint {name} ({addr})")
                current_task = asyncio.create_task(
                    monitor_node(name, addr, writer)
                )

            # Sleep a bit, but not past the overall end_time
            await asyncio.sleep(min(1.0, max(0.1, remaining)))
    finally:
        if current_task and not current_task.done():
            print(f"[failover] Cancelling monitor task for {current_name}")
            current_task.cancel()
            await asyncio.gather(current_task, return_exceptions=True)


async def main_async(args: argparse.Namespace, writer: JsonBlockWriter) -> None:
    """
    Load eth-network-services.json, collect all EL nodes (name starts with 'el-')
    that have a non-null/non-empty 'ws' field, and monitor them with
    single-connection failover.
    """
    services_path = Path(args.ws_file)
    if not services_path.is_file():
        raise FileNotFoundError(f"Services file not found at {services_path}")

    with services_path.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected {services_path} to contain a JSON array as in eth-network-services.json"
        )

    endpoints: List[Tuple[str, str]] = []

    for entry in data:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        ws_addr = entry.get("ws")

        # Only EL nodes
        if not isinstance(name, str) or not name.startswith("el-"):
            continue

        if isinstance(ws_addr, str) and ws_addr.strip():
            endpoints.append((name, ws_addr.strip()))

    if not endpoints:
        raise RuntimeError(
            "No valid EL WebSocket endpoints found in eth-network-services.json "
            "(looked for entries with name starting with 'el-' and non-empty 'ws')."
        )

    print("Discovered EL endpoints:")
    for n, a in endpoints:
        print(f"  - {n}: {a}")

    # Run a single monitor at a time, with automatic failover
    await monitor_with_failover(endpoints, writer, args.duration)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Ethereum blocks from WebSocket endpoints "
        "defined in eth-network-services.json and record per-block metrics."
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
        help="Monitoring duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--output",
        default="data/block_metrics.json",
        help=(
            "Output JSON file for collected metrics "
            "(default: data/block_metrics.json)"
        ),
    )
    parser.add_argument(
        "--flush-tx-count",
        type=int,
        default=100,
        help=(
            "Flush buffered records to disk after at least this many "
            "new transactions (default: 100)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_path = Path(args.output)

    writer = JsonBlockWriter(out_path, flush_tx_count=args.flush_tx_count)

    try:
        asyncio.run(main_async(args, writer))
    except KeyboardInterrupt:
        print("Interrupted by user, no additional data will be collected.")
    finally:
        writer.close()

    print(
        f"Saved {writer.total_blocks} block records "
        f"covering {writer.total_txs} transactions to {out_path}"
    )


if __name__ == "__main__":
    main()
