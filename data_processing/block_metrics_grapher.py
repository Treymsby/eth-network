#!/usr/bin/env python3
import argparse
import json
import os

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator


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
        rows.append(
            {
                "block_number": b["block_number"],
                "timestamp": pd.to_datetime(b["timestamp"]),
                "gas_used": b["block"]["gas"]["used"],
                "gas_used_pct": b["block"]["gas"]["used_percentage"],
                "block_size_kb": b["block"]["size_kb"],
                "tx_count": b["transactions"]["count"],
                "tx_success_rate": b["transactions"]["success"]["success_rate_percent"],
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
    """Create a modern single-metric line plot and save to PNG."""

    # Metric-specific colors
    metric_colors = {
        "gas_used": "#1f77b4",
        "gas_used_pct": "#ff7f0e",
        "block_size_kb": "#2ca02c",
        "tx_count": "#d62728",
        "tx_success_rate": "#9467bd",
    }
    color = metric_colors.get(metric_col, "#4c72b0")

    fig, ax = plt.subplots(figsize=(11, 4.5))

    x = df[x_col]
    y = df[metric_col]

    # Line + subtle area fill
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
    ax.set_ylabel(y_label, fontsize=10)

    # Nicer x-axis
    if x_col == "block_index":
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Human-readable y ticks
    if metric_col in ("gas_used_pct", "tx_success_rate"):
        # percentages: 85%
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda val, pos: f"{val:.0f}%")
        )
        ax.set_ylim(0, 105)

        # helper line around "high usage"
        if metric_col == "gas_used_pct":
            ax.axhline(80, linestyle="--", linewidth=1, alpha=0.3)
    else:
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda val, pos: human_format(val))
        )
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, prune="both"))
        ax.set_ylim(bottom=0)

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

    # Small legend in top-left (mainly a label)
    ax.legend(loc="upper left", frameon=False, fontsize=8)

    fig.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Visualise block metrics (gas, size, tx count, success rate) from JSON."
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
        help="Use 'block' for relative block index, or 'time' for timestamp.",
    )
    parser.add_argument(
        "--min-block",
        type=int,
        default=2,  # default: start at block 2
        help="Minimum original block_number to include (default: 2).",
    )
    parser.add_argument(
        "--max-block",
        type=int,
        default=65,  # default: end at block 65
        help="Maximum original block_number to include (default: 65).",
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

    # For block x-axis: re-index to start at 1
    # (e.g. original blocks 2–65 become x = 1–64)
    if args.x_axis == "block":
        df = df.reset_index(drop=True)
        df["block_index"] = range(1, len(df) + 1)
        x_col = "block_index"
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
        ("tx_success_rate", "Tx success %", "Transaction success rate per block"),
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


if __name__ == "__main__":
    main()
