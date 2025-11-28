#!/usr/bin/env python3
"""
Visualize client metrics JSON-lines file.

Input format:
- One JSON object per line (no commas, not a single big JSON array).
- Each object has:
    {
        "timestamp": "...",
        "interval_seconds": 1,
        "processes": [
            {
                "node_name": "...",
                "cpu_usage_seconds": ...,
                "cpu_usage_percent": ...,
                "memory_usage_kb": ...,
                "memory_usage_percent": ...
            },
            ...
        ],
        "totals": {
            "cpu_usage_seconds": ...,
            "cpu_usage_percent": ...,
            "memory_usage_kb": ...,
            "memory_usage_percent": ...
        }
    }

Usage:
    python plot_client_metrics.py --input client_metrics.json --output plots/

Requirements:
    pip install matplotlib pandas
"""

import argparse
import json
import math
import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot client metrics per 10-second time scale."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSON-lines metrics file (one JSON object per line).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory where PNG plots will be written.",
    )
    return parser.parse_args()


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO8601 timestamp with optional trailing 'Z'."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def load_records(path: str):
    """Load JSON objects line-by-line from file, skipping empty lines."""
    records = []
    node_names = set()

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            records.append(obj)
            for proc in obj.get("processes", []):
                node_names.add(proc["node_name"])

    if not records:
        raise ValueError("No records found in input file.")

    node_names = sorted(node_names)
    return records, node_names


def build_times(records):
    """Build elapsed-seconds timeline from timestamps."""
    t0 = parse_timestamp(records[0]["timestamp"])
    times = []
    for rec in records:
        t = parse_timestamp(rec["timestamp"])
        elapsed = (t - t0).total_seconds()
        times.append(elapsed)
    return times


def build_data(records, node_names):
    """Build per-node and totals data structures."""
    times = build_times(records)

    # Per-node metrics: dict[node_name] -> list[values]
    cpu_per_node = {n: [] for n in node_names}
    mem_per_node_mb = {n: [] for n in node_names}
    mem_pct_per_node = {n: [] for n in node_names}

    # Totals
    total_cpu_pct = []
    total_mem_mb = []
    total_mem_pct = []

    for rec in records:
        # Build row dictionaries for this timestamp to handle missing nodes robustly
        row_cpu = {n: float("nan") for n in node_names}
        row_mem_mb = {n: float("nan") for n in node_names}
        row_mem_pct = {n: float("nan") for n in node_names}

        for proc in rec.get("processes", []):
            n = proc["node_name"]
            if n not in row_cpu:
                # New node we didn't see earlier; initialize everywhere with NaNs
                row_cpu[n] = float("nan")
                row_mem_mb[n] = float("nan")
                row_mem_pct[n] = float("nan")
                cpu_per_node.setdefault(n, [])
                mem_per_node_mb.setdefault(n, [])
                mem_pct_per_node.setdefault(n, [])

            # CPU % per node, normalized by dividing by 20 (internal only)
            cpu_pct_raw = proc.get("cpu_usage_percent", 0.0)
            row_cpu[n] = cpu_pct_raw / 20.0

            mem_kb = proc.get("memory_usage_kb", 0.0)
            row_mem_mb[n] = mem_kb / 1024.0
            row_mem_pct[n] = proc.get("memory_usage_percent", 0.0)

        # Append to master lists in a consistent node order
        for n in node_names:
            cpu_per_node[n].append(row_cpu.get(n, float("nan")))
            mem_per_node_mb[n].append(row_mem_mb.get(n, float("nan")))
            mem_pct_per_node[n].append(row_mem_pct.get(n, float("nan")))

        totals = rec.get("totals", {})
        # Total CPU % also normalized by dividing by 20
        total_cpu_pct.append(totals.get("cpu_usage_percent", 0.0) / 20.0)
        total_mem_mb.append(totals.get("memory_usage_kb", 0.0) / 1024.0)
        total_mem_pct.append(totals.get("memory_usage_percent", 0.0))

    # Build DataFrames for easier plotting
    df_cpu_node = pd.DataFrame(cpu_per_node, index=times)
    df_mem_node_mb = pd.DataFrame(mem_per_node_mb, index=times)
    df_mem_node_pct = pd.DataFrame(mem_pct_per_node, index=times)

    totals_dict = {
        "time": times,
        "total_cpu_pct": total_cpu_pct,
        "total_mem_mb": total_mem_mb,
        "total_mem_pct": total_mem_pct,
    }

    return df_cpu_node, df_mem_node_mb, df_mem_node_pct, totals_dict


def configure_time_axis(ax, times):
    """
    Configure X axis as 'time since start' in mm:ss with
    a reasonable number of ticks (~up to 8).
    """
    if not times:
        return

    max_t = max(times)
    if max_t <= 0:
        ax.set_xlim(0, 1)
        ax.set_xticks([0])
        ax.set_xticklabels(["00:00"])
        ax.set_xlabel("Time since start (mm:ss)")
        return

    # Aim for ~8 ticks, with step rounded to a multiple of 10 seconds
    target_ticks = 8
    raw_step = max_t / target_ticks
    step = max(10.0, math.ceil(raw_step / 10.0) * 10.0)

    ticks = []
    t = 0.0
    while t <= max_t * 1.001:  # small margin
        ticks.append(t)
        t += step

    # Format as mm:ss
    labels = [f"{int(tt // 60):02d}:{int(tt % 60):02d}" for tt in ticks]

    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_xlabel("Time since start (mm:ss)")


def plot_per_node(df, ylabel, title, output_path):
    """Plot one line per node for a given per-node metric DataFrame."""
    fig, ax = plt.subplots(figsize=(12, 6))
    for col in df.columns:
        ax.plot(df.index, df[col], label=col)

    configure_time_axis(ax, df.index.to_list())
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.4)

    # Put legend outside the plot on the right
    ax.legend(
        title="Nodes",
        bbox_to_anchor=(1.04, 0.5),
        loc="center left",
        borderaxespad=0,
        fontsize=8,
    )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_total(times, values, ylabel, title, output_path, color=None):
    """Plot a single total metric over time with a nicer design."""
    fig, ax = plt.subplots(figsize=(12, 5))

    # Main line
    ax.plot(times, values, linewidth=2.0, color=color)

    # Soft area fill under the curve
    baseline = 0.0
    ax.fill_between(times, values, baseline, alpha=0.2, color=color)

    configure_time_axis(ax, times)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main():
    args = parse_args()

    os.makedirs(args.output, exist_ok=True)

    records, node_names = load_records(args.input)
    (
        df_cpu_node,
        df_mem_node_mb,
        df_mem_node_pct,
        totals,
    ) = build_data(records, node_names)

    # Per-node plots (all nodes on one graph for each metric)
    plot_per_node(
        df_cpu_node,
        ylabel="CPU % per node",
        title="CPU % per Node",
        output_path=os.path.join(args.output, "cpu_percent_per_node.png"),
    )

    plot_per_node(
        df_mem_node_mb,
        ylabel="Memory per node (MB)",
        title="Memory Usage per Node (MB)",
        output_path=os.path.join(args.output, "memory_per_node_mb.png"),
    )

    plot_per_node(
        df_mem_node_pct,
        ylabel="Memory % per node",
        title="Memory % per Node",
        output_path=os.path.join(args.output, "memory_percent_per_node.png"),
    )

    # Totals plots with nicer area-style design
    times = totals["time"]

    plot_total(
        times,
        totals["total_cpu_pct"],
        ylabel="Total CPU %",
        title="Total CPU Usage (%)",
        output_path=os.path.join(args.output, "total_cpu_percent.png"),
        color="tab:red",
    )

    plot_total(
        times,
        totals["total_mem_mb"],
        ylabel="Total Memory Usage (MB)",
        title="Total Memory Usage (MB)",
        output_path=os.path.join(args.output, "total_memory_usage_mb.png"),
        color="tab:blue",
    )

    plot_total(
        times,
        totals["total_mem_pct"],
        ylabel="Total Memory Usage (%)",
        title="Total Memory Usage (%)",
        output_path=os.path.join(args.output, "total_memory_percent.png"),
        color="tab:green",
    )


if __name__ == "__main__":
    main()
