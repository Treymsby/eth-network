#!/usr/bin/env python3
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
import statistics

import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(
        description="Visualize per-block metrics from tx_metrics JSON."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to input JSON file"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Directory to write PNG charts to"
    )
    return parser.parse_args()


def load_records(path):
    """
    Load records from JSON file.

    Supports:
      - A JSON array of objects
      - One JSON object per line (NDJSON)
    """
    with open(path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            # Fallback: NDJSON
            f.seek(0)
            data = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data.append(json.loads(line))

    if isinstance(data, list):
        return data
    else:
        return [data]


def parse_iso8601(ts):
    """
    Parse ISO8601 timestamps like 2025-11-16T02:37:34.729001+00:00
    """
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        # handle potential 'Z' suffix
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        raise


def aggregate_by_block(records, max_block=64):
    """
    Aggregate metrics per block.
    Returns several dicts keyed by block_number.
    """
    block_tx_counts = defaultdict(int)
    block_latencies_ms = defaultdict(list)
    block_first_seen = {}
    block_last_confirmed = {}
    block_effective_gas_price_wei = defaultdict(list)

    for rec in records:
        tx = rec.get("tx", {})
        time_info = rec.get("time", {})
        gas_info = rec.get("gas", {})

        block = tx.get("block_number")
        if block is None:
            continue

        # only consider blocks up to max_block
        if block > max_block:
            continue

        block_tx_counts[block] += 1

        # latency
        latency_ms = time_info.get("latency_ms")
        if latency_ms is not None:
            block_latencies_ms[block].append(latency_ms)

        # timestamps for TPS
        fs = parse_iso8601(time_info.get("first_seen_utc"))
        conf = parse_iso8601(time_info.get("confirmed_utc"))

        if fs is not None:
            if block not in block_first_seen or fs < block_first_seen[block]:
                block_first_seen[block] = fs
        if conf is not None:
            if block not in block_last_confirmed or conf > block_last_confirmed[block]:
                block_last_confirmed[block] = conf

        # effective gas price
        eff_price = gas_info.get("effective_price")
        if eff_price is not None:
            block_effective_gas_price_wei[block].append(eff_price)

    return (
        block_tx_counts,
        block_latencies_ms,
        block_first_seen,
        block_last_confirmed,
        block_effective_gas_price_wei,
    )


def compute_tps(block_tx_counts, block_first_seen, block_last_confirmed):
    """
    Compute TPS per block: tx_count / (last_confirmed - first_seen).
    Returns dict {block: tps}.
    """
    block_tps = {}
    for block in sorted(block_tx_counts.keys()):
        if block not in block_first_seen or block not in block_last_confirmed:
            continue

        start = block_first_seen[block]
        end = block_last_confirmed[block]
        duration = (end - start).total_seconds()
        if duration <= 0:
            # avoid division by zero or negative intervals
            continue

        block_tps[block] = block_tx_counts[block] / duration

    return block_tps


def compute_success_rate(records, max_block=64):
    """
    Compute success rate per block in percent.
    Tries several common fields to determine success:
    - rec["success"], rec["status"]
    - rec["tx"]["success"], rec["tx"]["status"], rec["tx"]["receipt_status"]
    Treats True, 1, "1", "success", "ok", "confirmed" as success.
    """
    success_counts = defaultdict(int)
    total_counts = defaultdict(int)

    def is_success(value):
        if value is None:
            return False
        # booleans
        if value is True:
            return True
        if value is False:
            return False
        # numbers
        if isinstance(value, (int, float)):
            # 1 or >0 considered success, 0 failure
            return value != 0
        # strings
        s = str(value).strip().lower()
        return s in {"1", "true", "success", "ok", "confirmed"}

    for rec in records:
        tx = rec.get("tx", {})
        block = tx.get("block_number")
        if block is None or block > max_block:
            continue

        # try multiple fields for status
        status_fields = [
            rec.get("success"),
            rec.get("status"),
            tx.get("success"),
            tx.get("status"),
            tx.get("receipt_status"),
        ]

        status_value = None
        for v in status_fields:
            if v is not None:
                status_value = v
                break

        if status_value is None:
            # no status information, skip this tx
            continue

        total_counts[block] += 1
        if is_success(status_value):
            success_counts[block] += 1

    block_success_rate = {}
    for block, total in total_counts.items():
        if total > 0:
            block_success_rate[block] = (success_counts[block] / total) * 100.0

    return block_success_rate


def plot_tx_per_block(block_tx_counts, output_dir):
    if not block_tx_counts:
        return

    blocks = sorted(block_tx_counts.keys())
    counts = [block_tx_counts[b] for b in blocks]

    plt.figure(figsize=(10, 6))
    plt.bar(blocks, counts)
    plt.xlabel("Block number")
    plt.ylabel("Transactions per block")
    plt.title("Transactions per block (blocks ≤ 64)")
    plt.tight_layout()

    out_path = os.path.join(output_dir, "tx_per_block.png")
    plt.savefig(out_path)
    plt.close()


def plot_latency_boxplot(block_latencies_ms, output_dir):
    if not block_latencies_ms:
        return

    blocks = sorted(block_latencies_ms.keys())
    data_ms = [block_latencies_ms[b] for b in blocks]

    all_latencies = [v for sub in data_ms for v in sub]
    if not all_latencies:
        return

    median_ms = statistics.median(all_latencies)
    # simple heuristic: if median >= 2 seconds, show seconds, otherwise ms
    if median_ms >= 2000:
        factor = 1.0 / 1000.0
        unit = "s"
    else:
        factor = 1.0
        unit = "ms"

    data_scaled = [[lat * factor for lat in lat_list] for lat_list in data_ms]

    plt.figure(figsize=(max(12, len(blocks) * 0.3), 6))
    positions = list(range(1, len(blocks) + 1))
    plt.boxplot(data_scaled, positions=positions, showmeans=False)
    plt.xticks(positions, blocks, rotation=90)
    plt.xlabel("Block number")
    plt.ylabel(f"Confirmation latency ({unit})")
    plt.title("Transaction confirmation latency per block")
    plt.tight_layout()

    out_path = os.path.join(output_dir, "latency_boxplot.png")
    plt.savefig(out_path)
    plt.close()


def plot_tps(block_tps, output_dir):
    if not block_tps:
        return

    blocks = sorted(block_tps.keys())
    tps_vals = [block_tps[b] for b in blocks]

    plt.figure(figsize=(10, 6))
    plt.bar(blocks, tps_vals)
    plt.xlabel("Block number")
    plt.ylabel("Transactions per second (TPS)")
    plt.title("TPS per block")
    plt.tight_layout()

    out_path = os.path.join(output_dir, "tps_per_block.png")
    plt.savefig(out_path)
    plt.close()


def plot_effective_gas_price(block_effective_gas_price_wei, output_dir):
    if not block_effective_gas_price_wei:
        return

    blocks = sorted(block_effective_gas_price_wei.keys())
    avg_gwei = []
    for b in blocks:
        prices_wei = block_effective_gas_price_wei[b]
        if prices_wei:
            avg_wei = statistics.mean(prices_wei)
            avg_gwei.append(avg_wei / 1e9)
        else:
            avg_gwei.append(float("nan"))

    plt.figure(figsize=(10, 6))
    plt.plot(blocks, avg_gwei, marker="o")
    plt.xlabel("Block number")
    plt.ylabel("Average effective gas price (gwei)")
    plt.title("Average effective gas price per block")
    plt.tight_layout()

    out_path = os.path.join(output_dir, "effective_gas_price_per_block.png")
    plt.savefig(out_path)
    plt.close()


def plot_success_rate_zoomed(block_success_rate, output_dir):
    """
    Plot transaction success rate per block, zoomed to 80–100%.
    """
    if not block_success_rate:
        return

    blocks = sorted(block_success_rate.keys())
    rates = [block_success_rate[b] for b in blocks]

    plt.figure(figsize=(10, 6))
    plt.plot(blocks, rates, marker="o")
    plt.xlabel("Block number")
    plt.ylabel("Success rate (%)")
    plt.title("Transaction success rate per block (zoomed 80–100%)")
    # Zoom the Y axis to 80–100%
    plt.ylim(80, 100)
    plt.tight_layout()

    out_path = os.path.join(output_dir, "success_rate_per_block_zoomed_80_100.png")
    plt.savefig(out_path)
    plt.close()


def main():
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    records = load_records(args.input)

    (
        block_tx_counts,
        block_latencies_ms,
        block_first_seen,
        block_last_confirmed,
        block_effective_gas_price_wei,
    ) = aggregate_by_block(records, max_block=64)

    block_tps = compute_tps(block_tx_counts, block_first_seen, block_last_confirmed)
    block_success_rate = compute_success_rate(records, max_block=64)

    plot_tx_per_block(block_tx_counts, args.output)
    plot_latency_boxplot(block_latencies_ms, args.output)
    plot_tps(block_tps, args.output)
    plot_effective_gas_price(block_effective_gas_price_wei, args.output)
    plot_success_rate_zoomed(block_success_rate, args.output)


if __name__ == "__main__":
    main()
