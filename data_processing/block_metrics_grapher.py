#!/usr/bin/env python3
import argparse
import json
import os

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator

# Metric-specific colors
METRIC_COLORS = {
    "gas_used": "#1f77b4",
    "gas_used_pct": "#ff7f0e",
    "block_size_kb": "#2ca02c",
    "tx_count": "#d62728",
    "tx_success_rate": "#9467bd",
    "base_fee_gwei": "#8c564b",
    "effective_gas_price_gwei": "#e377c2",
    "priority_fee_gwei": "#7f7f7f",
    "tx_fee_eth": "#bcbd22",
}


def load_blocks(json_path: str):
    """Load the JSON file (array of block objects)."""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data


def build_dataframe(blocks):
    """
    Flatten the nested JSON structure into a tabular DataFrame
    with one row per block.
    """
    rows = []
    for b in blocks:
        gas_used = b["block"]["gas"]["used"]
        fees = b["transactions"].get("fees", {})

        base_fee_per_gas_wei = fees.get("base_fee_per_gas_wei")
        priority_fee_total_wei = fees.get("priority_fee_wei")
        tx_fee_total_wei = fees.get("transaction_fee_wei")

        # Derived fee metrics
        if gas_used and gas_used > 0:
            effective_gas_price_gwei = (
                tx_fee_total_wei / gas_used / 1e9
                if tx_fee_total_wei is not None
                else None
            )
            priority_fee_gwei = (
                priority_fee_total_wei / gas_used / 1e9
                if priority_fee_total_wei is not None
                else None
            )
        else:
            effective_gas_price_gwei = None
            priority_fee_gwei = None

        base_fee_gwei = (
            base_fee_per_gas_wei / 1e9 if base_fee_per_gas_wei is not None else None
        )
        tx_fee_eth = tx_fee_total_wei / 1e18 if tx_fee_total_wei is not None else None

        rows.append(
            {
                "block_number": b["block_number"],
                "timestamp": pd.to_datetime(b["timestamp"]),
                "gas_used": gas_used,
                "gas_used_pct": b["block"]["gas"]["used_percentage"],
                "block_size_kb": b["block"]["size_kb"],
                "tx_count": b["transactions"]["count"],
                "tx_success_rate": b["transactions"]["success"][
                    "success_rate_percent"
                ],
                # New metrics
                "base_fee_gwei": base_fee_gwei,
                "effective_gas_price_gwei": effective_gas_price_gwei,
                "priority_fee_gwei": priority_fee_gwei,
                "tx_fee_eth": tx_fee_eth,
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("block_number").reset_index(drop=True)
    return df


def filter_block_range(df: pd.DataFrame, min_block: int | None, max_block: int | None):
    """Filter DataFrame to a given block_number range."""
    if min_block is not None:
        df = df[df["block_number"] >= min_block]
    if max_block is not None:
        df = df[df["block_number"] <= max_block]
    df = df.sort_values("block_number").reset_index(drop=True)
    return df


def human_format(num: float) -> str:
    """Format large numbers as 1.2K, 3.4M, etc."""
    if num == 0:
        return "0"
    magnitude = 0
    units = ["", "K", "M", "B", "T", "P"]
    n = float(num)
    while abs(n) >= 1000 and magnitude < len(units) - 1:
        magnitude += 1
        n /= 1000.0
    # Use no decimals if it's almost an int, else one decimal
    if abs(n - int(n)) < 1e-6:
        return f"{int(n)}{units[magnitude]}"
    return f"{n:.1f}{units[magnitude]}"


def plot_metric(
    df: pd.DataFrame,
    x_col: str,
    metric_col: str,
    y_label: str,
    title: str,
    x_label: str,
    output_path: str,
):
    """Create a modern single-metric plot (line or bar) and save to PNG."""
    color = METRIC_COLORS.get(metric_col, "#4c72b0")

    fig, ax = plt.subplots(figsize=(11, 4.5))

    x = df[x_col]
    y = df[metric_col]

    # --- Different chart types per metric ---
    if metric_col in ("block_size_kb", "tx_count"):
        # Bar charts for block size and tx count
        ax.bar(x, y, label=y_label, color=color, alpha=0.9)
    elif metric_col == "tx_success_rate":
        # Line + dot markers for each x; no legend label text
        ax.plot(
            x,
            y,
            linewidth=1.8,
            marker="o",
            markersize=3.5,
            label=None,
            color=color,
        )
    else:
        # Default: line + subtle area fill
        ax.plot(
            x,
            y,
            linewidth=2.0,
            label=y_label,
            color=color,
        )
        ax.fill_between(x, y, alpha=0.12, color=color)

    ax.set_title(title, fontsize=13, pad=14, loc="left")
    ax.set_xlabel(x_label, fontsize=10)

    # Don't show y-axis label text if y_label is empty
    ax.set_ylabel(y_label, fontsize=10 if y_label else 0)

    # Nicer x-axis
    if x_col == "block_number":
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Human-readable y ticks
    if metric_col in ("gas_used_pct", "tx_success_rate"):
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda val, pos: f"{val:.0f}%")
        )
        ax.set_ylim(0, 105)
    else:
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda val, pos: human_format(val))
        )
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
        ax.set_ylim(bottom=0)

        # Gas limit helper line at 45M for gas_used
        if metric_col == "gas_used":
            ax.axhline(
                45_000_000,
                linestyle="--",
                linewidth=1,
                alpha=0.5,
            )

    # Grid & ticks
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
    ax.margins(x=0.01)
    ax.tick_params(axis="both", labelsize=8, length=3)

    # Clean up spines: keep left + bottom, hide top + right
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    for spine in ("left", "bottom"):
        ax.spines[spine].set_linewidth(0.8)
        ax.spines[spine].set_alpha(0.5)

    # Rotate time labels if needed
    if x_col == "timestamp":
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    # Legend only if we have a non-empty label
    handles, labels = ax.get_legend_handles_labels()
    if y_label and labels:
        ax.legend(loc="upper left", frameon=False, fontsize=8)

    fig.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")


def plot_effective_gas_with_gas_pct(
    df: pd.DataFrame,
    x_col: str,
    x_label: str,
    output_path: str,
):
    """
    Plot effective gas price (Gwei) overlaid with gas used % on a secondary axis.
    Uses a logarithmic scale for effective gas price to tame large spikes.
    """
    fig, ax1 = plt.subplots(figsize=(11, 4.5))

    x = df[x_col]
    y_price = df["effective_gas_price_gwei"].astype(float)
    y_pct = df["gas_used_pct"]

    # Log scale can't handle zero or negative values: drop them for plotting
    y_price = y_price.where(y_price > 0)

    color_price = METRIC_COLORS.get("effective_gas_price_gwei", "#e377c2")
    color_pct = METRIC_COLORS.get("gas_used_pct", "#ff7f0e")

    # Left axis: effective gas price (log scale)
    ax1.plot(
        x,
        y_price,
        color=color_price,
        linewidth=2.0,
        label="Effective gas price (Gwei, log scale)",
    )
    ax1.set_xlabel(x_label, fontsize=10)
    ax1.set_ylabel("Effective gas price (Gwei, log)", color=color_price, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=color_price)

    # Logarithmic scale for price
    ax1.set_yscale("log")
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.3g}"))

    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
    ax1.margins(x=0.01)

    if x_col == "block_number":
        ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    if x_col == "timestamp":
        plt.setp(ax1.get_xticklabels(), rotation=30, ha="right")

    # Right axis: gas used % (linear)
    ax2 = ax1.twinx()
    ax2.plot(
        x,
        y_pct,
        color=color_pct,
        linewidth=1.8,
        linestyle="--",
        label="Gas used %",
    )
    ax2.set_ylabel("Gas used %", color=color_pct, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=color_pct)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.0f}%"))
    ax2.set_ylim(0, 105)

    # Title & legend
    ax1.set_title(
        "Effective gas price (log) vs gas used %",
        fontsize=13,
        pad=14,
        loc="left",
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper left",
        frameon=False,
        fontsize=8,
    )

    # Clean up spines
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)
    ax1.spines["left"].set_linewidth(0.8)
    ax1.spines["left"].set_alpha(0.5)
    ax1.spines["bottom"].set_linewidth(0.8)
    ax1.spines["bottom"].set_alpha(0.5)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")


def plot_tx_count_with_gas_used(
    df: pd.DataFrame,
    x_col: str,
    x_label: str,
    output_path: str,
):
    """
    Plot transactions per block overlaid with gas used:
      - Left axis: tx_count (bars, with value labels inside)
      - Right axis: gas_used (line)
    """
    fig, ax1 = plt.subplots(figsize=(11, 4.5))

    x = df[x_col]
    y_tx = df["tx_count"]
    y_gas = df["gas_used"]

    color_tx = METRIC_COLORS.get("tx_count", "#d62728")
    color_gas = METRIC_COLORS.get("gas_used", "#1f77b4")

    # Left axis: tx count as bars
    bars = ax1.bar(
        x,
        y_tx,
        color=color_tx,
        alpha=0.85,
        label="Tx count",
    )
    ax1.set_xlabel(x_label, fontsize=10)
    ax1.set_ylabel("Transactions per block", color=color_tx, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=color_tx)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: human_format(v)))
    ax1.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
    ax1.set_ylim(bottom=0)

    # Add tx_count labels inside each bar (vertical, white text)
    for rect in bars:
        height = rect.get_height()
        if height <= 0:
            continue
        ax1.text(
            rect.get_x() + rect.get_width() / 2,
            height * 0.5,  # middle of the bar
            f"{int(height)}",
            ha="center",
            va="center",
            fontsize=7,
            color="white",
            rotation=90,
        )

    if x_col == "block_number":
        ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    if x_col == "timestamp":
        plt.setp(ax1.get_xticklabels(), rotation=30, ha="right")

    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
    ax1.margins(x=0.01)

    # Right axis: gas used as line
    ax2 = ax1.twinx()
    ax2.plot(
        x,
        y_gas,
        color=color_gas,
        linewidth=2.0,
        label="Gas used",
    )
    ax2.set_ylabel("Gas used", color=color_gas, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=color_gas)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: human_format(v)))
    ax2.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
    ax2.set_ylim(bottom=0)

    # Title & combined legend
    ax1.set_title(
        "Transactions per block vs gas used",
        fontsize=13,
        pad=14,
        loc="left",
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper left",
        frameon=False,
        fontsize=8,
    )

    # Clean up spines
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)
    ax1.spines["left"].set_linewidth(0.8)
    ax1.spines["left"].set_alpha(0.5)
    ax1.spines["bottom"].set_linewidth(0.8)
    ax1.spines["bottom"].set_alpha(0.5)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")


def plot_tx_count_with_fees(
    df: pd.DataFrame,
    x_col: str,
    x_label: str,
    output_path: str,
):
    """
    Plot transactions per block overlaid with base fee and priority fee:
      - Left axis: tx_count (bars, with value labels inside, vertical)
      - Right axis: base_fee_gwei and priority_fee_gwei (lines, Gwei)

    Priority fee outliers are removed using a 95th percentile cutoff.
    """
    fig, ax1 = plt.subplots(figsize=(11, 4.5))

    x = df[x_col]
    y_tx = df["tx_count"]
    y_base = df["base_fee_gwei"].astype(float)
    y_priority = df["priority_fee_gwei"].astype(float)

    # --- Remove outliers from priority fee using 95th percentile ---
    priority_valid = y_priority.dropna()
    if len(priority_valid) >= 4:
        upper = priority_valid.quantile(0.95)
        # mask values above upper as NaN so they won't be plotted
        y_priority_filtered = y_priority.where(y_priority <= upper)
    else:
        # Not enough data to define outliers robustly; keep as-is
        y_priority_filtered = y_priority

    color_tx = METRIC_COLORS.get("tx_count", "#d62728")
    color_base = METRIC_COLORS.get("base_fee_gwei", "#8c564b")
    color_priority = METRIC_COLORS.get("priority_fee_gwei", "#7f7f7f")

    # Left axis: tx count as bars
    bars = ax1.bar(
        x,
        y_tx,
        color=color_tx,
        alpha=0.85,
        label="Tx count",
    )
    ax1.set_xlabel(x_label, fontsize=10)
    ax1.set_ylabel("Transactions per block", color=color_tx, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=color_tx)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: human_format(v)))
    ax1.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
    ax1.set_ylim(bottom=0)

    # Add tx_count labels inside each bar (vertical, white text)
    for rect in bars:
        height = rect.get_height()
        if height <= 0:
            continue
        ax1.text(
            rect.get_x() + rect.get_width() / 2,
            height * 0.5,  # middle of the bar
            f"{int(height)}",
            ha="center",
            va="center",
            fontsize=7,
            color="white",
            rotation=90,
        )

    if x_col == "block_number":
        ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    if x_col == "timestamp":
        plt.setp(ax1.get_xticklabels(), rotation=30, ha="right")

    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
    ax1.margins(x=0.01)

    # Right axis: base fee + (outlier-filtered) priority fee (Gwei, lines)
    ax2 = ax1.twinx()
    ax2.plot(
        x,
        y_base,
        color=color_base,
        linewidth=2.0,
        label="Base fee (Gwei)",
    )
    ax2.plot(
        x,
        y_priority_filtered,
        color=color_priority,
        linewidth=1.8,
        linestyle="--",
        label="Priority fee",
    )
    ax2.set_ylabel("Fees per gas (Gwei)", fontsize=10)
    ax2.tick_params(axis="y")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:g}"))
    ax2.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
    ax2.set_ylim(bottom=0)

    # Title & combined legend
    ax1.set_title(
        "Transactions per block vs base & priority fee",
        fontsize=13,
        pad=14,
        loc="left",
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper left",
        frameon=False,
        fontsize=8,
    )

    # Clean up spines on main axis
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)
    ax1.spines["left"].set_linewidth(0.8)
    ax1.spines["left"].set_alpha(0.5)
    ax1.spines["bottom"].set_linewidth(0.8)
    ax1.spines["bottom"].set_alpha(0.5)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Visualise block metrics (gas, size, tx count, success rate, "
            "fees/gas prices) from JSON."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to the input JSON file (array of block metrics).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="Directory to write individual PNGs for each metric.",
    )
    parser.add_argument(
        "--x-axis",
        choices=["block", "time"],
        default="block",
        help="Use 'block' for block_number on the x-axis, or 'time' for timestamp.",
    )
    parser.add_argument(
        "--min-block",
        type=int,
        default=1,  # default: start at block 1
        help="Minimum original block_number to include (default: 1).",
    )
    parser.add_argument(
        "--max-block",
        type=int,
        default=64,  # default: end at block 64
        help="Maximum original block_number to include (default: 64).",
    )

    args = parser.parse_args()

    blocks = load_blocks(args.input)
    df = build_dataframe(blocks)

    # Filter to desired original block_number range
    df = filter_block_range(df, args.min_block, args.max_block)

    if df.empty:
        raise SystemExit(
            f"No blocks in range [{args.min_block}, {args.max_block}] "
            f"found in {args.input}"
        )

    # For block x-axis: use real block_number (no shifting)
    if args.x_axis == "block":
        df = df.sort_values("block_number").reset_index(drop=True)
        x_col = "block_number"
        x_label = "Block"
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)
        x_col = "timestamp"
        x_label = "Block time"

    # Which metrics to plot -> one PNG each
    metrics = [
        ("gas_used", "Gas used", "Gas used per block"),
        ("gas_used_pct", "Gas used %", "Gas used percentage per block"),
        ("block_size_kb", "Block size (KB)", "Block size per block"),
        ("tx_count", "Tx count", "Transaction count per block"),
        # y_label is empty here so "Tx success %" text is not shown
        ("tx_success_rate", "", "Transaction success rate per block"),
        # New fee/gas-price metrics
        ("base_fee_gwei", "Base fee (Gwei)", "Base fee per gas"),
        (
            "effective_gas_price_gwei",
            "Effective gas price (Gwei)",
            "Effective gas price per block",
        ),
        (
            "priority_fee_gwei",
            "Priority fee (Gwei)",
            "Priority fee per gas",
        ),
        (
            "tx_fee_eth",
            "Tx fees (ETH)",
            "Total transaction fees per block (ETH)",
        ),
    ]

    base_dir = args.output_dir
    os.makedirs(base_dir, exist_ok=True)

    for metric_col, y_label, title in metrics:
        filename = f"{metric_col}.png"
        output_path = os.path.join(base_dir, filename)
        plot_metric(
            df=df,
            x_col=x_col,
            metric_col=metric_col,
            y_label=y_label,
            title=title,
            x_label=x_label,
            output_path=output_path,
        )

    # Special overlay chart: effective gas price vs gas used %
    overlay_filename = "effective_gas_price_vs_gas_used_pct.png"
    overlay_output_path = os.path.join(base_dir, overlay_filename)
    plot_effective_gas_with_gas_pct(
        df=df,
        x_col=x_col,
        x_label=x_label,
        output_path=overlay_output_path,
    )

    # New overlay chart: tx count vs gas used
    tx_gas_filename = "tx_count_vs_gas_used.png"
    tx_gas_output_path = os.path.join(base_dir, tx_gas_filename)
    plot_tx_count_with_gas_used(
        df=df,
        x_col=x_col,
        x_label=x_label,
        output_path=tx_gas_output_path,
    )

    # New overlay chart: tx count vs base/priority fees (Gwei, with priority outliers removed)
    tx_fees_filename = "tx_count_vs_fees_gwei.png"
    tx_fees_output_path = os.path.join(base_dir, tx_fees_filename)
    plot_tx_count_with_fees(
        df=df,
        x_col=x_col,
        x_label=x_label,
        output_path=tx_fees_output_path,
    )


if __name__ == "__main__":
    main()
