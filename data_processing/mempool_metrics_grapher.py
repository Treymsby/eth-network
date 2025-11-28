#!/usr/bin/env python3
import argparse
import json
import os

import matplotlib.pyplot as plt

# Spammer IDs we care about
SPAMMER_IDS = ["100", "101", "102"]

# Block range filter (inclusive)
MIN_BLOCK = 1
MAX_BLOCK = 64


def parse_args():
    parser = argparse.ArgumentParser(
        description="Visualize spammer transaction metrics per block."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input JSON file (spamoor_dashboard export).",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Directory where PNG charts will be written.",
    )
    return parser.parse_args()


def load_data(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_block_series(payload):
    """
    Extracts (only for blocks in [MIN_BLOCK, MAX_BLOCK]):
      - blocks: list of block numbers (x-axis)
      - metrics: dict[metric][spammer_id] -> list of values per block
      - totals: dict[metric] -> list of total values per block (sum over SPAMMER_IDS)
      - id_to_name: mapping from spammer id string to human-readable name
      - gas_by_spammer: dict[spammer_id] -> list of gas used per block
      - total_gas: list of total gas used per block (network-wide)
    """
    data_points = payload.get("data", [])
    if not data_points:
        raise ValueError("No 'data' array found in JSON or it is empty.")

    # Map spammer id -> name using the top-level 'spammers' list if present
    id_to_name = {}
    for s in payload.get("spammers", []):
        sid = str(s.get("id"))
        if sid:
            id_to_name[sid] = s.get("name", sid)

    # Append '(Baseline)' behind EOA and ERC labels
    if "100" in id_to_name:
        id_to_name["100"] = f"{id_to_name['100']} (Baseline)"
    if "101" in id_to_name:
        id_to_name["101"] = f"{id_to_name['101']} (Baseline)"

    blocks = []
    metrics = {
        "pending": {sid: [] for sid in SPAMMER_IDS},
        "submitted": {sid: [] for sid in SPAMMER_IDS},
        "confirmed": {sid: [] for sid in SPAMMER_IDS},
    }
    totals = {
        "pending": [],
        "submitted": [],
        "confirmed": [],
    }
    gas_by_spammer = {sid: [] for sid in SPAMMER_IDS}
    total_gas = []

    for entry in data_points:
        # Use endBlock, fall back to startBlock
        block = entry.get("endBlock") or entry.get("startBlock")

        # Skip blocks outside [MIN_BLOCK, MAX_BLOCK]
        if block is None or block < MIN_BLOCK or block > MAX_BLOCK:
            continue

        blocks.append(block)

        spammers_block = entry.get("spammers", {})

        block_totals = {"pending": 0, "submitted": 0, "confirmed": 0}

        for sid in SPAMMER_IDS:
            spammer_metrics = spammers_block.get(sid, {})
            for key in ("pending", "submitted", "confirmed"):
                value = spammer_metrics.get(key, 0)
                metrics[key][sid].append(value)
                block_totals[key] += value

            # Gas per spammer per block
            gas_by_spammer[sid].append(spammer_metrics.get("gas", 0))

        for key in ("pending", "submitted", "confirmed"):
            totals[key].append(block_totals[key])

        # Total gas for this block (network wide)
        total_gas.append(entry.get("totalGas", 0))

    if not blocks:
        raise ValueError(
            f"No data points found in block range [{MIN_BLOCK}, {MAX_BLOCK}]."
        )

    return blocks, metrics, totals, id_to_name, gas_by_spammer, total_gas


def ensure_output_dir(path: str):
    os.makedirs(path, exist_ok=True)


def plot_metric_per_spammer(
    blocks, metrics_for_metric, id_to_name, metric_name: str, output_dir: str
):
    """
    One chart per metric (pending/submitted/confirmed),
    lines = each spammer id with its name.
    """
    plt.figure(figsize=(10, 6))

    for sid in SPAMMER_IDS:
        series = metrics_for_metric.get(sid)
        if series is None or len(series) == 0:
            continue
        label = id_to_name.get(sid, sid)
        plt.plot(blocks, series, label=label)

    plt.xlabel("Block")
    plt.ylabel(f"{metric_name.capitalize()} transactions")
    plt.title(
        f"{metric_name.capitalize()} transactions per block "
        f"(blocks {MIN_BLOCK}-{MAX_BLOCK})"
    )
    plt.grid(True, linestyle="--", alpha=0.3)
    plt.legend()
    plt.tight_layout()

    filename = f"{metric_name}_per_spammer.png"
    plt.savefig(os.path.join(output_dir, filename))
    plt.close()


def plot_totals(blocks, totals, output_dir: str):
    """
    One chart with:
      - TOTAL Pending Transactions  = SUM(100,101,102)
      - TOTAL Submitted Transactions = SUM(100,101,102)
      - TOTAL Confirmed Transactions = SUM(100,101,102)
    """
    plt.figure(figsize=(10, 6))

    plt.plot(blocks, totals["pending"], label="Total pending")
    plt.plot(blocks, totals["submitted"], label="Total submitted")
    plt.plot(blocks, totals["confirmed"], label="Total confirmed")

    plt.xlabel("Block")
    plt.ylabel("Transactions")
    plt.title(
        f"Total pending / submitted / confirmed per block "
        f"(blocks {MIN_BLOCK}-{MAX_BLOCK})"
    )
    plt.grid(True, linestyle="--", alpha=0.3)
    plt.legend()
    plt.tight_layout()

    filename = "totals_pending_submitted_confirmed.png"
    plt.savefig(os.path.join(output_dir, filename))
    plt.close()


def plot_stacked_gas(blocks, gas_by_spammer, total_gas, id_to_name, output_dir: str):
    """
    Stacked bar chart per block, showing gas used by each spammer type (100/101/102).
    The bar height is total gas from all three; a dashed line shows total network gas.
    """
    plt.figure(figsize=(12, 6))

    bottom = [0] * len(blocks)

    for sid in SPAMMER_IDS:
        values = gas_by_spammer.get(sid)
        if not values:
            continue
        label = id_to_name.get(sid, sid)
        plt.bar(blocks, values, bottom=bottom, label=label)
        bottom = [bottom[i] + values[i] for i in range(len(values))]

    if total_gas:
        plt.plot(
            blocks,
            total_gas,
            label="Total gas (network)",
            linestyle="--",
            marker="o",
            linewidth=1,
        )

    plt.xlabel("Block")
    plt.ylabel("Gas used")
    plt.title(
        f"Gas usage per block (stacked by type, blocks {MIN_BLOCK}-{MAX_BLOCK})"
    )
    plt.grid(True, axis="y", linestyle="--", alpha=0.3)
    plt.legend()
    plt.tight_layout()

    filename = "gas_stacked_per_block.png"
    plt.savefig(os.path.join(output_dir, filename))
    plt.close()


def main():
    args = parse_args()
    ensure_output_dir(args.output)

    payload = load_data(args.input)
    (
        blocks,
        metrics,
        totals,
        id_to_name,
        gas_by_spammer,
        total_gas,
    ) = extract_block_series(payload)

    # Individual metrics
    plot_metric_per_spammer(
        blocks, metrics["pending"], id_to_name, "pending", args.output
    )
    plot_metric_per_spammer(
        blocks, metrics["submitted"], id_to_name, "submitted", args.output
    )
    plot_metric_per_spammer(
        blocks, metrics["confirmed"], id_to_name, "confirmed", args.output
    )

    # Totals chart
    plot_totals(blocks, totals, args.output)

    # Stacked gas usage chart
    plot_stacked_gas(blocks, gas_by_spammer, total_gas, id_to_name, args.output)


if __name__ == "__main__":
    main()
