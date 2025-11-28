#!/usr/bin/env python3
"""
Plot network node traffic over time from two Grafana CSV exports
(Received + Transmitted) like the ones produced for the
network_node_bytes_total_* metrics.

X-axis: seconds since the first sample.
Y-axis: Kb/s or Mb/s (chosen automatically per chart).

Usage example:
    python plot_network_traffic.py \
        --input network_node_bytes_total_received-....csv \
                network_node_bytes_total_transmit-....csv \
        --output ./plots

The --input flag takes *both* CSV files (order does not matter).
The script will try to detect which one is "received" vs "transmit"
from the file name; if that fails and there are exactly two files,
the first is treated as "received" and the second as "transmit".
"""

import argparse
import os
import re
from typing import Tuple, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize per-node network traffic from Grafana CSV exports."
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        required=True,
        help="Two input CSV files: one for *received* and one for *transmitted* bytes.",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Directory where PNG charts will be written.",
    )
    return parser.parse_args()


def detect_metric_kind(path: str) -> str:
    """Return 'received' / 'transmit' / '' based on the file name."""
    name = os.path.basename(path).lower()
    if "receiv" in name or "rx" in name:
        return "received"
    if "transmit" in name or "sent" in name or name.endswith("tx.csv") or "_tx." in name:
        return "transmit"
    return ""


def parse_throughput_to_bytes_per_second(value) -> float:
    """Convert Grafana-style values like '3.32 kb/s', '1.1 Mb/s' into bytes/second.

    Returns np.nan for missing / unparsable values.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan

    s = str(value).strip()
    if not s:
        return np.nan

    # Match '<number> <prefix><b|B>/s', e.g. '3.32 kb/s', '1.1 Mb/s'
    m = re.match(r'^([0-9]*\.?[0-9]+)\s*([kMGT]?)([bB])/s$', s)
    if not m:
        # Maybe it's already a bare number
        try:
            return float(s)
        except ValueError:
            return np.nan

    num = float(m.group(1))
    prefix = m.group(2)
    unit_char = m.group(3)

    multiplier = {
        "": 1.0,
        "k": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
    }.get(prefix, 1.0)

    # Convert to bits/s first
    if unit_char == "b":  # bits
        bits_per_s = num * multiplier
    else:  # "B" -> bytes, so multiply by 8 to get bits
        bits_per_s = num * multiplier * 8.0

    # Then convert bits/s -> bytes/s
    bytes_per_s = bits_per_s / 8.0
    return bytes_per_s


def extract_label_from_column(col_name: str) -> str:
    """Pull the 'service' (or 'instance') label out of a Prometheus-style column name."""
    for lbl in ("service", "instance", "job"):
        m = re.search(rf'{lbl}="([^"]+)"', col_name)
        if m:
            return m.group(1)
    return col_name


def rename_job(service: str) -> str:
    """Rename cl-xx-lighthouse-besu -> el-xx-besu-lighthouse.

    For everything else we just return the original string.
    """
    m = re.match(r"cl-(\d+)-lighthouse-besu$", service)
    if m:
        index = m.group(1)
        return f"el-{index}-besu-lighthouse"
    return service


def load_grafana_csv(path: str) -> pd.DataFrame:
    """Read one of the provided CSVs and return a cleaned DataFrame.

    - Parses 'Time' as datetime
    - Keeps only metric value columns (ignores the '.1' helper columns)
    - Converts values into numeric bytes/second
    - Renames series based on the job/service mapping.
    """
    df = pd.read_csv(path, nrows=51)

    if "Time" not in df.columns:
        raise ValueError(f"CSV '{path}' does not have a 'Time' column")

    df["Time"] = pd.to_datetime(df["Time"])

    value_cols: List[str] = [
        c for c in df.columns
        if c != "Time" and not c.endswith("}.1")
    ]

    cleaned = pd.DataFrame({"Time": df["Time"]})

    for col in value_cols:
        raw_label = extract_label_from_column(col)
        label = rename_job(raw_label)

        series = df[col].apply(parse_throughput_to_bytes_per_second)
        cleaned[label] = series

    # Make sure columns (nodes) are in a stable order
    ordered_cols = ["Time"] + sorted([c for c in cleaned.columns if c != "Time"])
    cleaned = cleaned[ordered_cols]

    return cleaned


def choose_scale_from_df(df: pd.DataFrame) -> Tuple[float, str]:
    """Decide whether to plot in Kb/s or Mb/s for a multi-column DF.

    Returns (scale_factor, unit_label).

    scale_factor multiplies bytes/s to get the plotted unit:
      - Kb/s: value_plot = bytes_per_s * (8 / 1e3)
      - Mb/s: value_plot = bytes_per_s * (8 / 1e6)
    """
    data_cols = [c for c in df.columns if c != "Time"]
    if not data_cols:
        return 1.0, "bytes/s"

    arr = df[data_cols].to_numpy(dtype=float)
    if arr.size == 0:
        return 1.0, "bytes/s"

    max_bytes = np.nanmax(np.abs(arr))
    if not np.isfinite(max_bytes) or max_bytes == 0:
        return 1.0, "bytes/s"

    max_bits = max_bytes * 8.0

    if max_bits >= 1e6:
        # Use Mb/s
        return 8.0 / 1e6, "Mb/s"
    else:
        # Use Kb/s
        return 8.0 / 1e3, "Kb/s"


def choose_scale_from_series(series: pd.Series) -> Tuple[float, str]:
    """Same as choose_scale_from_df, but for a single series."""
    arr = series.to_numpy(dtype=float)
    if arr.size == 0:
        return 1.0, "bytes/s"

    max_bytes = np.nanmax(np.abs(arr))
    if not np.isfinite(max_bytes) or max_bytes == 0:
        return 1.0, "bytes/s"

    max_bits = max_bytes * 8.0

    if max_bits >= 1e6:
        return 8.0 / 1e6, "Mb/s"
    else:
        return 8.0 / 1e3, "Kb/s"


def plot_per_node(
    df: pd.DataFrame,
    kind_label: str,
    title: str,
    output_path: str,
    t0: pd.Timestamp,
) -> None:
    """Plot all node series on the same figure and save to output_path.

    X-axis: seconds since t0.
    Y-axis: Kb/s or Mb/s (auto).
    """
    if "Time" not in df.columns:
        raise ValueError("DataFrame must contain a 'Time' column")

    seconds = (df["Time"] - t0).dt.total_seconds()
    scale, unit = choose_scale_from_df(df)

    fig, ax = plt.subplots(figsize=(14, 7))

    for col in df.columns:
        if col == "Time":
            continue
        ax.plot(seconds, df[col] * scale, label=col)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel(f"{kind_label} [{unit}]")
    ax.set_title(title)

    ax.grid(True, which="both", linestyle="--", alpha=0.3)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0.0, fontsize="small")

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_total_traffic(
    time: pd.Series,
    total_bytes_per_s: pd.Series,
    output_path: str,
    t0: pd.Timestamp,
) -> None:
    """Plot total network traffic (sum over all nodes & Rx+Tx).

    X-axis: seconds since t0.
    Y-axis: Kb/s or Mb/s (auto).
    """
    seconds = (time - t0).dt.total_seconds()
    scale, unit = choose_scale_from_series(total_bytes_per_s)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(seconds, total_bytes_per_s * scale)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel(f"Total traffic [{unit}]")
    ax.set_title("Total Network Traffic (all nodes, Rx + Tx)")

    ax.grid(True, which="both", linestyle="--", alpha=0.3)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def compute_total_traffic(
    recv_df: pd.DataFrame,
    tx_df: pd.DataFrame,
) -> Tuple[pd.Series, pd.Series]:
    """Return (time_index, total_bytes_per_s) for all nodes and Rx+Tx.

    We align both dataframes on the union of their timestamps.
    """
    recv_wide = recv_df.set_index("Time")
    tx_wide = tx_df.set_index("Time")

    all_times = sorted(set(recv_wide.index).union(set(tx_wide.index)))
    all_times = pd.to_datetime(all_times)

    recv_aligned = recv_wide.reindex(all_times)
    tx_aligned = tx_wide.reindex(all_times)

    total_recv = recv_aligned.sum(axis=1, skipna=True)
    total_tx = tx_aligned.sum(axis=1, skipna=True)
    total = total_recv + total_tx

    return pd.Series(all_times), total


def main() -> None:
    args = parse_args()

    if len(args.input) < 2:
        raise SystemExit("Please provide two CSV files to --input (received and transmitted).")

    recv_path: str = ""
    tx_path: str = ""

    # Try to detect by file name
    for path in args.input:
        kind = detect_metric_kind(path)
        if kind == "received" and not recv_path:
            recv_path = path
        elif kind == "transmit" and not tx_path:
            tx_path = path

    # Fallback if detection fails
    if not recv_path or not tx_path:
        if len(args.input) == 2:
            recv_path, tx_path = args.input[0], args.input[1]
        else:
            raise SystemExit(
                "Could not determine which CSV is 'received' vs 'transmit'.\n"
                "Either:\n"
                "  * use filenames containing 'received'/'transmit', or\n"
                "  * provide exactly two files so the first can be treated as 'received' and the second as 'transmit'."
            )

    os.makedirs(args.output, exist_ok=True)

    print(f"Reading RECEIVED metrics from:   {recv_path}")
    print(f"Reading TRANSMITTED metrics from: {tx_path}")
    recv_df = load_grafana_csv(recv_path)
    tx_df = load_grafana_csv(tx_path)

    # Common reference time for x-axis = seconds
    start_time = min(recv_df["Time"].min(), tx_df["Time"].min())

    # Plot per-node received
    recv_png = os.path.join(args.output, "bytes_received_per_node.png")
    plot_per_node(
        recv_df,
        kind_label="Received traffic",
        title="Bytes Received per Node",
        output_path=recv_png,
        t0=start_time,
    )
    print(f"Wrote {recv_png}")

    # Plot per-node transmitted
    tx_png = os.path.join(args.output, "bytes_transmitted_per_node.png")
    plot_per_node(
        tx_df,
        kind_label="Transmitted traffic",
        title="Bytes Transmitted per Node",
        output_path=tx_png,
        t0=start_time,
    )
    print(f"Wrote {tx_png}")

    # Total traffic
    time_index, total = compute_total_traffic(recv_df, tx_df)
    total_png = os.path.join(args.output, "total_network_traffic.png")
    plot_total_traffic(
        time_index,
        total,
        output_path=total_png,
        t0=start_time,
    )
    print(f"Wrote {total_png}")


if __name__ == "__main__":
    main()
