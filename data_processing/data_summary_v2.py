import os
import glob
import json
import math
import statistics
from datetime import datetime, timedelta

import pandas as pd


CLIENT_COLUMN_MAP = {
    "besu_lighthouse": "Besu - Lighthouse",
    "equalweight_mixed_el_lighthouse": "Equalweight - Lighthouse",
    "geth_lighthouse": "Geth - Lighthouse",
    "mainnet_mixed_el_lighthouse": "Mainnet - Lighthouse",
    "nethermind_lighthouse": "Nethermind - Lighthouse",
}

TEST_NAME_MAP = {
    "bigblock": "BigBlock",
    "highcompute": "HighCompute",
    "highgas": "HighGas",
    "max-tx": "MaxTx",
}

TEST_ORDER = ["BigBlock", "HighCompute", "HighGas", "MaxTx"]

METRIC_BASE_ORDER = [
    "CPU %",
    "CPU % per node",
    "Gas Gwei",
    "Latency ms",
    "Net RX MB/s",
    "Net TX MB/s",
    "RAM GB",
    "RAM GB per node",
    "TPS",
    "TX Count",
    "Spam Submitted",
    "Spam Pending",
    "Spam Confirmed",
    "Block Gas Used %",
    "Block Size kB",
    "Total Gas Used",
    "Total TX Count",
    "Total Spam Submitted",
]


def parse_iso_ts(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def safe_mean(values):
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def wei_to_gwei(v):
    return v / 1e9 if v is not None else None


def kb_to_gb(kb):
    return kb / (1024.0 * 1024.0)


def parse_rate_to_mbps(rate_str):
    if rate_str is None or (isinstance(rate_str, float) and pd.isna(rate_str)):
        return None
    s = str(rate_str).strip()
    if not s:
        return None

    parts = s.split()
    if len(parts) < 2:
        return None

    try:
        value = float(parts[0])
    except ValueError:
        return None

    unit = parts[1].lower()
    unit = unit.replace("/s", "").replace("b/s", "b")

    if unit in ("b", "byte"):
        factor = 1.0 / (1024.0 * 1024.0)
    elif unit in ("kb", "kib"):
        factor = 1024.0 / (1024.0 * 1024.0)
    elif unit in ("mb", "mib"):
        factor = 1.0
    elif unit in ("gb", "gib"):
        factor = 1024.0
    else:
        return None

    return value * factor


def calc_stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"avg": None, "median": None, "min": None, "max": None}
    return {
        "avg": statistics.mean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
    }


def format_value(val):
    if val is None:
        return ""

    if isinstance(val, int) and not isinstance(val, bool):
        return str(val)

    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)

    decimals = 4 if abs(v) < 1.0 else 2
    factor = 10 ** decimals
    truncated = math.trunc(v * factor) / factor

    return f"{truncated:.{decimals}f}"


def compute_block_splits(block_metrics_path):
    if not os.path.exists(block_metrics_path):
        return [], [], {"phase1": None, "phase2": None}, None, None

    with open(block_metrics_path) as f:
        blocks = json.load(f)

    blocks = [b for b in blocks if 1 <= b.get("block_number", 0) <= 64]

    blocks_phase1 = [b for b in blocks if 1 <= b["block_number"] <= 31]
    blocks_phase2 = [b for b in blocks if 32 <= b["block_number"] <= 64]

    def compute_duration(sub_blocks):
        if not sub_blocks:
            return None
        ts_values = [parse_iso_ts(b["timestamp"]) for b in sub_blocks]
        return max(1.0, (max(ts_values) - min(ts_values)).total_seconds())

    durations = {
        "phase1": compute_duration(blocks_phase1),
        "phase2": compute_duration(blocks_phase2),
    }

    first_block_ts = parse_iso_ts(blocks[0]["timestamp"]) if blocks else None
    last_block_ts_64 = parse_iso_ts(blocks[-1]["timestamp"]) if blocks else None

    return blocks_phase1, blocks_phase2, durations, first_block_ts, last_block_ts_64


def compute_tx_metrics(tx_metrics_path, durations):
    series = {}
    aggregates = {}

    if not os.path.exists(tx_metrics_path):
        return series, aggregates

    with open(tx_metrics_path) as f:
        txs = json.load(f)

    txs = [t for t in txs if 1 <= t.get("tx", {}).get("block_number", 0) <= 64]

    txs_phase1 = [t for t in txs if 1 <= t["tx"]["block_number"] <= 31]
    txs_phase2 = [t for t in txs if 32 <= t["tx"]["block_number"] <= 64]

    gas1 = [wei_to_gwei(t["gas"]["effective_price"]) for t in txs_phase1 if t.get("gas")]
    gas2 = [wei_to_gwei(t["gas"]["effective_price"]) for t in txs_phase2 if t.get("gas")]

    lat1 = [
        t["time"]["latency_ms"]
        for t in txs_phase1
        if t.get("time") and t["time"].get("latency_ms") is not None
    ]
    lat2 = [
        t["time"]["latency_ms"]
        for t in txs_phase2
        if t.get("time") and t["time"].get("latency_ms") is not None
    ]

    series["Gas Gwei"] = {"phase1": gas1, "phase2": gas2}
    series["Latency ms"] = {"phase1": lat1, "phase2": lat2}

    count1 = len(txs_phase1)
    count2 = len(txs_phase2)
    dur1 = durations.get("phase1") or 1.0
    dur2 = durations.get("phase2") or 1.0

    aggregates["TX Count"] = {"phase1": count1, "phase2": count2}
    aggregates["TPS"] = {
        "phase1": count1 / dur1 if dur1 else None,
        "phase2": count2 / dur2 if dur2 else None,
    }
    aggregates["Total TX Count 1-64"] = len(txs)

    return series, aggregates


def compute_block_level_metrics(blocks_phase1, blocks_phase2):
    series = {}
    aggregates = {}

    gas_pct1 = [b["block"]["gas"]["used_percentage"] for b in blocks_phase1 if b.get("block")]
    gas_pct2 = [b["block"]["gas"]["used_percentage"] for b in blocks_phase2 if b.get("block")]

    size1 = [b["block"]["size_kb"] for b in blocks_phase1 if b.get("block")]
    size2 = [b["block"]["size_kb"] for b in blocks_phase2 if b.get("block")]

    series["Block Gas Used %"] = {"phase1": gas_pct1, "phase2": gas_pct2}
    series["Block Size kB"] = {"phase1": size1, "phase2": size2}

    gas_used1 = [b["block"]["gas"]["used"] for b in blocks_phase1 if b.get("block")]
    gas_used2 = [b["block"]["gas"]["used"] for b in blocks_phase2 if b.get("block")]

    aggregates["Total Gas Used"] = {
        "phase1": sum(gas_used1) if gas_used1 else None,
        "phase2": sum(gas_used2) if gas_used2 else None,
    }

    return series, aggregates


def compute_client_metrics(client_metrics_path):
    series = {}
    aggregates = {}

    if not os.path.exists(client_metrics_path):
        return series, aggregates

    rows = []
    with open(client_metrics_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    if not rows:
        return series, aggregates

    for r in rows:
        r["_ts"] = parse_iso_ts(r["timestamp"])

    rows.sort(key=lambda r: r["_ts"])
    start_ts = rows[0]["_ts"]
    phase1_end = start_ts + timedelta(seconds=400)
    phase2_end = start_ts + timedelta(seconds=800)

    phase1_rows = [r for r in rows if start_ts <= r["_ts"] < phase1_end]
    phase2_rows = [r for r in rows if phase1_end <= r["_ts"] < phase2_end]

    cpu1 = [r["totals"]["cpu_usage_percent"] for r in phase1_rows if r.get("totals")]
    cpu2 = [r["totals"]["cpu_usage_percent"] for r in phase2_rows if r.get("totals")]

    ram1 = [kb_to_gb(r["totals"]["memory_usage_kb"]) for r in phase1_rows if r.get("totals")]
    ram2 = [kb_to_gb(r["totals"]["memory_usage_kb"]) for r in phase2_rows if r.get("totals")]

    series["CPU %"] = {"phase1": cpu1, "phase2": cpu2}
    series["RAM GB"] = {"phase1": ram1, "phase2": ram2}

    def per_node_cpu(window):
        out = []
        for r in window:
            procs = r.get("processes") or []
            vals = [p.get("cpu_usage_percent") for p in procs if p.get("cpu_usage_percent") is not None]
            if vals:
                out.append(safe_mean(vals))
        return out

    def per_node_ram(window):
        out = []
        for r in window:
            procs = r.get("processes") or []
            vals = [kb_to_gb(p.get("memory_usage_kb")) for p in procs if p.get("memory_usage_kb") is not None]
            if vals:
                out.append(safe_mean(vals))
        return out

    cpu_node1 = per_node_cpu(phase1_rows)
    cpu_node2 = per_node_cpu(phase2_rows)
    ram_node1 = per_node_ram(phase1_rows)
    ram_node2 = per_node_ram(phase2_rows)

    if cpu_node1 or cpu_node2:
        series["CPU % per node"] = {"phase1": cpu_node1, "phase2": cpu_node2}
    if ram_node1 or ram_node2:
        series["RAM GB per node"] = {"phase1": ram_node1, "phase2": ram_node2}

    return series, aggregates


def compute_network_metrics(run_dir):
    series = {}
    aggregates = {}

    recv_candidates = glob.glob(os.path.join(run_dir, "network_node_bytes_total_received*.csv"))
    tx_candidates = glob.glob(os.path.join(run_dir, "network_node_bytes_total_transmit*.csv"))

    if not recv_candidates or not tx_candidates:
        csv_files = glob.glob(os.path.join(run_dir, "*.csv"))
        lower_names = {p: os.path.basename(p).lower() for p in csv_files}

        recv_candidates = [p for p, name in lower_names.items() if "received" in name]
        tx_candidates = [p for p, name in lower_names.items() if "transmit" in name]

    if not recv_candidates or not tx_candidates:
        return series, aggregates

    recv_path = sorted(recv_candidates)[0]
    tx_path = sorted(tx_candidates)[0]

    recv_df = pd.read_csv(recv_path)
    tx_df = pd.read_csv(tx_path)

    recv_df = recv_df.iloc[:51]
    tx_df = tx_df.iloc[:51]

    recv_nodes = [c for c in recv_df.columns if c.lower() != "time"]
    tx_nodes = [c for c in tx_df.columns if c.lower() != "time"]

    def collect_totals(df, node_cols, start_idx, end_idx):
        if df.empty:
            return []
        sub = df.iloc[start_idx:end_idx]
        totals = []
        for _, row in sub[node_cols].iterrows():
            vals = [parse_rate_to_mbps(row[col]) for col in node_cols]
            vals = [v for v in vals if v is not None]
            if vals:
                totals.append(sum(vals))
        return totals

    mid = 25
    rx_phase1 = collect_totals(recv_df, recv_nodes, 0, mid)
    rx_phase2 = collect_totals(recv_df, recv_nodes, mid, 51)
    tx_phase1 = collect_totals(tx_df, tx_nodes, 0, mid)
    tx_phase2 = collect_totals(tx_df, tx_nodes, mid, 51)

    series["Net RX MB/s"] = {"phase1": rx_phase1, "phase2": rx_phase2}
    series["Net TX MB/s"] = {"phase1": tx_phase1, "phase2": tx_phase2}

    return series, aggregates


def compute_spamoor_metrics(spamoor_path):
    series = {}
    aggregates = {}

    if not os.path.exists(spamoor_path):
        return series, aggregates

    with open(spamoor_path) as f:
        spam = json.load(f)

    data = spam.get("data", [])
    data = [
        d
        for d in data
        if d.get("startBlock") is not None
        and d.get("endBlock") is not None
        and d["endBlock"] >= 1
        and d["startBlock"] <= 64
    ]
    data.sort(key=lambda d: d.get("startBlock", 0))

    submitted_vals = {"phase1": [], "phase2": []}
    pending_vals = {"phase1": [], "phase2": []}
    confirmed_vals = {"phase1": [], "phase2": []}

    prev_sub_cum = 0

    for e in data:
        start_b = e.get("startBlock", 0)
        end_b = e.get("endBlock", 0)

        if end_b <= 31:
            phase = "phase1"
        elif start_b >= 32 and end_b <= 64:
            phase = "phase2"
        else:
            continue

        spammers = e.get("spammers") or {}

        cum_sub = sum(s.get("submitted", 0) for s in spammers.values())
        inc_sub = max(cum_sub - prev_sub_cum, 0)
        prev_sub_cum = cum_sub

        total_pending = sum(s.get("pending", 0) for s in spammers.values())
        total_confirmed = sum(s.get("confirmed", 0) for s in spammers.values())

        submitted_vals[phase].append(inc_sub)
        pending_vals[phase].append(total_pending)
        confirmed_vals[phase].append(total_confirmed)

    series["Spam Submitted"] = {
        "phase1": submitted_vals["phase1"],
        "phase2": submitted_vals["phase2"],
    }
    series["Spam Pending"] = {
        "phase1": pending_vals["phase1"],
        "phase2": pending_vals["phase2"],
    }
    series["Spam Confirmed"] = {
        "phase1": confirmed_vals["phase1"],
        "phase2": confirmed_vals["phase2"],
    }

    total_sub1 = sum(submitted_vals["phase1"]) if submitted_vals["phase1"] else None
    total_sub2 = sum(submitted_vals["phase2"]) if submitted_vals["phase2"] else None
    aggregates["Total Spam Submitted"] = {"phase1": total_sub1, "phase2": total_sub2}
    aggregates["Total Spam Submitted 1-64"] = (total_sub1 or 0) + (total_sub2 or 0)

    return series, aggregates


def compute_metrics_for_run(run_dir):
    folder_name = os.path.basename(os.path.normpath(run_dir))
    parts = folder_name.split("_")
    test_suffix = parts[-1].lower()
    client_prefix = "_".join(parts[:-1])

    test_label = TEST_NAME_MAP.get(test_suffix)
    client_label = CLIENT_COLUMN_MAP.get(client_prefix)

    if test_label is None or client_label is None:
        raise ValueError(f"Could not determine test/client for folder '{folder_name}'")

    block_metrics_path = os.path.join(run_dir, "block_metrics.json")
    tx_metrics_path = os.path.join(run_dir, "tx_metrics.json")
    client_metrics_path = os.path.join(run_dir, "client_metrics.json")
    spamoor_path = os.path.join(run_dir, "spamoor_dashboard.json")

    blocks_phase1, blocks_phase2, durations, first_ts, last_ts64 = compute_block_splits(block_metrics_path)
    tx_series, tx_aggs = compute_tx_metrics(tx_metrics_path, durations)
    block_series, block_aggs = compute_block_level_metrics(blocks_phase1, blocks_phase2)
    client_series, client_aggs = compute_client_metrics(client_metrics_path)
    net_series, net_aggs = compute_network_metrics(run_dir)
    spam_series, spam_aggs = compute_spamoor_metrics(spamoor_path)

    metrics = {}

    def add_series_stats(base_label, series_data):
        s1 = calc_stats(series_data.get("phase1", []))
        s2 = calc_stats(series_data.get("phase2", []))

        metrics[(f"Avg {base_label}", "Phase 1")] = s1["avg"]
        metrics[(f"Median {base_label}", "Phase 1")] = s1["median"]
        metrics[(f"Min {base_label}", "Phase 1")] = s1["min"]
        metrics[(f"Max {base_label}", "Phase 1")] = s1["max"]

        metrics[(f"Avg {base_label}", "Phase 2")] = s2["avg"]
        metrics[(f"Median {base_label}", "Phase 2")] = s2["median"]
        metrics[(f"Min {base_label}", "Phase 2")] = s2["min"]
        metrics[(f"Max {base_label}", "Phase 2")] = s2["max"]

    def add_aggregate_phase_metric(name, agg):
        metrics[(name, "Phase 1")] = agg.get("phase1")
        metrics[(name, "Phase 2")] = agg.get("phase2")

    for base, ser in tx_series.items():
        add_series_stats(base, ser)
    for base, ser in block_series.items():
        add_series_stats(base, ser)
    for base, ser in client_series.items():
        add_series_stats(base, ser)
    for base, ser in net_series.items():
        add_series_stats(base, ser)
    for base, ser in spam_series.items():
        add_series_stats(base, ser)

    if "TX Count" in tx_aggs:
        add_aggregate_phase_metric("TX Count", tx_aggs["TX Count"])
    if "TPS" in tx_aggs:
        add_aggregate_phase_metric("TPS", tx_aggs["TPS"])
    if "Total TX Count 1-64" in tx_aggs:
        metrics[("Total TX Count (1-64)", "1-64")] = tx_aggs["Total TX Count 1-64"]
    if "Total Gas Used" in block_aggs:
        add_aggregate_phase_metric("Total Gas Used", block_aggs["Total Gas Used"])
    if "Total Spam Submitted" in spam_aggs:
        add_aggregate_phase_metric("Total Spam Submitted", spam_aggs["Total Spam Submitted"])
    if "Total Spam Submitted 1-64" in spam_aggs:
        metrics[("Total Spam Submitted (1-64)", "1-64")] = spam_aggs["Total Spam Submitted 1-64"]

    return test_label, client_label, metrics


def build_summary_table(data_dir="data", results_dir="results", filename="all_metrics.csv"):
    os.makedirs(results_dir, exist_ok=True)

    lookup_rows = []

    for run_dir in sorted(glob.glob(os.path.join(data_dir, "*"))):
        if not os.path.isdir(run_dir):
            continue
        try:
            test_label, client_label, metrics = compute_metrics_for_run(run_dir)
        except Exception as exc:
            print(f"Skipping {run_dir}: {exc}")
            continue

        for (metric_name, phase_tag), value in metrics.items():
            lookup_rows.append(
                {
                    "Test": test_label,
                    "Client": client_label,
                    "Metric": metric_name,
                    "Phase": phase_tag,
                    "Value": value,
                }
            )

    if lookup_rows:
        lookup_df = pd.DataFrame(lookup_rows)
        lookup_df["Value"] = lookup_df["Value"].apply(
            lambda v: format_value(v) if isinstance(v, (int, float)) else v
        )
        lookup_df = lookup_df.sort_values(["Test", "Metric", "Phase", "Client"])

        output_csv = os.path.join(results_dir, filename)
        lookup_df.to_csv(output_csv, index=False)
        print(f"Wrote metrics table to {output_csv}")


if __name__ == "__main__":
    build_summary_table(data_dir="data", results_dir="results", filename="all_metrics.csv")
