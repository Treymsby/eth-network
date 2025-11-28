#!/usr/bin/env python3
import argparse
import json
import os

import matplotlib.pyplot as plt


WEI_PER_GWEI = 10**9


def load_blocks(json_path):
    """
    Load blocks from a JSON file with structure:
    {
        "meta": {...},
        "results": {
            "1": {...block...},
            "2": {...},
            ...
        }
    }
    Returns a list of per-block dicts sorted by block height.
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    # Support both {"results": {...}} and raw dict of blocks
    results = data.get("results", data)

    blocks = []
    for key, block in results.items():
        # Figure out block height
        height = block.get("height")
        if height is None:
            try:
                height = int(key)
            except ValueError:
                continue

        # Parse fields (strings -> ints where needed)
        gas_used_raw = block.get("gas_used")
        gas_used = int(gas_used_raw) if gas_used_raw is not None else None

        gas_used_percentage = block.get("gas_used_percentage")

        # total transaction fees in wei
        tx_fees_raw = block.get("transaction_fees")
        tx_fees = int(tx_fees_raw) if tx_fees_raw is not None else None

        # base fee per gas in wei -> gwei
        base_fee_raw = block.get("base_fee_per_gas")
        base_fee = (
            int(base_fee_raw) / WEI_PER_GWEI if base_fee_raw is not None else None
        )

        # priority fee per gas in wei -> gwei (assuming the field is per-gas)
        priority_fee_raw = block.get("priority_fee")
        priority_fee = (
            int(priority_fee_raw) / WEI_PER_GWEI
            if priority_fee_raw is not None
            else None
        )

        # Compute effective_gas_price (average gwei per gas in the block)
        # effective_gas_price_gwei = (total_fees_wei / gas_used) / 1e9
        if gas_used and gas_used > 0 and tx_fees is not None:
            effective_gas_price = (tx_fees / gas_used) / WEI_PER_GWEI
        else:
            effective_gas_price = None  # no gas used or fees; skip/leave empty

        blocks.append(
            {
                "height": height,
                "gas_used": gas_used,
                "gas_used_percentage": gas_used_percentage,
                "transaction_fees": tx_fees,          # still in wei
                "base_fee_per_gas": base_fee,         # now in gwei
                "priority_fee": priority_fee,         # now in gwei
                "effective_gas_price": effective_gas_price,  # gwei
            }
        )

    # Sort by height
    blocks.sort(key=lambda b: b["height"])
    return blocks


def compute_upper_iqr_fence(values, k=3.0):
    """
    Compute an upper fence for outlier detection using the IQR method:
    upper_fence = Q3 + k * IQR

    Returns None if there are not enough data points.
    """
    xs = sorted(v for v in values if v is not None)
    if len(xs) < 4:
        return None

    def percentile(p):
        # p in [0, 1]
        pos = (len(xs) - 1) * p
        lower = int(pos)
        upper = min(lower + 1, len(xs) - 1)
        weight = pos - lower
        return xs[lower] + (xs[upper] - xs[lower]) * weight

    q1 = percentile(0.25)
    q3 = percentile(0.75)
    iqr = q3 - q1
    return q3 + k * iqr


def plot_metric(heights, values, metric_key, ylabel, output_dir, color, title=None):
    """
    Plot a single metric against block height and save as PNG.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(heights, values, marker="o", linestyle="-", color=color)
    plt.xlabel("Block height")
    plt.ylabel(ylabel)
    plt.title(title or metric_key.replace("_", " ").title())
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    out_path = os.path.join(output_dir, f"{metric_key}.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Saved {out_path}")


def plot_normalized_with_gas_pct(heights, eff_norm_values, gas_pct_values, output_dir):
    """
    Plot Effective Gas Price (Normalized) with Gas Used (%) overlaid on a
    secondary y-axis in the same chart.
    """
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Primary axis: normalized effective gas price
    ax1.plot(
        heights,
        eff_norm_values,
        marker="o",
        linestyle="-",
        color="tab:brown",
        label="Effective gas price (normalized)",
    )
    ax1.set_xlabel("Block height")
    ax1.set_ylabel("Effective gas price (gwei)", color="tab:brown")
    ax1.tick_params(axis="y", labelcolor="tab:brown")
    ax1.grid(True, linestyle="--", alpha=0.5)

    # Secondary axis: gas used percentage (line only, no markers)
    ax2 = ax1.twinx()
    ax2.plot(
        heights,
        gas_pct_values,
        linestyle="-",
        color="tab:blue",
        label="Gas used (%)",
    )
    ax2.set_ylabel("Gas used (%)", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    fig.suptitle("Effective Gas Price (Normalized)")
    fig.tight_layout()

    out_path = os.path.join(output_dir, "effective_gas_price_normalized.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Saved {out_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Visualize per-block metrics from a block JSON file."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input JSON file (e.g. blocks_1_64.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Directory to write PNG files into",
    )

    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    blocks = load_blocks(args.input)
    if not blocks:
        print("No blocks loaded from input file.")
        return

    heights = [b["height"] for b in blocks]

    # Compute a "normalized" effective gas price series by removing big spikes
    eff_values = [
        b.get("effective_gas_price")
        for b in blocks
        if b.get("effective_gas_price") is not None
    ]
    upper_fence = compute_upper_iqr_fence(eff_values, k=3.0)

    if upper_fence is not None:
        for b in blocks:
            v = b.get("effective_gas_price")
            # Treat values above the upper fence as spikes and drop them
            b["effective_gas_price_normalized"] = (
                v if (v is not None and v <= upper_fence) else None
            )
    else:
        # If we couldn't compute a fence, just copy the original series
        for b in blocks:
            b["effective_gas_price_normalized"] = b.get("effective_gas_price")

    # Standard single-metric charts (still generated as before)
    metrics = [
        ("gas_used", "Gas used (units of gas)", "tab:blue", None),
        ("gas_used_percentage", "Gas used (%)", "tab:orange", None),
        ("transaction_fees", "Transaction fees (wei)", "tab:green", None),
        ("base_fee_per_gas", "Base fee per gas (gwei)", "tab:red", None),
        ("priority_fee", "Priority fee per gas (gwei)", "tab:purple", None),
        ("effective_gas_price", "Effective gas price (gwei)", "tab:brown", "Effective Gas Price"),
        # Note: normalized version is plotted with overlay below,
        # not via this generic helper.
    ]

    for metric_key, ylabel, color, title in metrics:
        values = [b.get(metric_key) for b in blocks]
        plot_metric(heights, values, metric_key, ylabel, args.output, color, title=title)

    # Overlay chart: Effective Gas Price (Normalized) + Gas Used (%)
    eff_norm_values = [b.get("effective_gas_price_normalized") for b in blocks]
    gas_pct_values = [b.get("gas_used_percentage") for b in blocks]

    plot_normalized_with_gas_pct(
        heights,
        eff_norm_values,
        gas_pct_values,
        args.output,
    )


if __name__ == "__main__":
    main()
