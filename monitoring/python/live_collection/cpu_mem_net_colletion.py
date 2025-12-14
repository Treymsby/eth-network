#!/usr/bin/env python3
"""
Collect metrics every SAMPLE_INTERVAL seconds for:
  - all geth / nethermind processes
  - java processes whose cmdline contains "besu"

Per process:
  - node_name (derived from flags like p2p-host / ExternalIp / datadir)
  - CPU Usage (seconds total since start)
  - CPU Usage % (over last interval)
  - Memory Usage (kB, RSS)
  - Memory Usage %

"""

import argparse
import datetime as dt
import json
import time

import psutil

SAMPLE_INTERVAL = 10
OUTPUT_FILE = "data/client_metrics.json"

TARGET_NAMES = {"geth", "nethermind"}
BESU_KEYWORD = "besu"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect metrics for geth / nethermind / besu processes."
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Total duration to run in seconds (default: run indefinitely)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=SAMPLE_INTERVAL,
        help=f"Sampling interval in seconds (default: {SAMPLE_INTERVAL})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help=f"Output file (default: {OUTPUT_FILE})",
    )
    return parser.parse_args()


def find_target_processes():
    """
    Return psutil.Process objects for:
      - geth
      - nethermind
      - java processes whose cmdline contains 'besu'
    """
    targets = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmdline_list = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline_list).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

        if name in TARGET_NAMES:
            targets.append(proc)
        elif name == "java" and BESU_KEYWORD in cmdline_str:
            targets.append(proc)

    return targets


def _get_flag_value(cmdline, prefixes):
    """
    Helper: given a cmdline list and a list of possible prefixes, return the
    value after the prefix (either in the same arg --flag=VALUE or next arg).
    """
    for i, arg in enumerate(cmdline):
        for prefix in prefixes:
            if arg.startswith(prefix):
                if "=" in arg:
                    value = arg.split("=", 1)[1]
                    if value.startswith("extip:"):
                        return value.split("extip:", 1)[1]
                    return value
                if i + 1 < len(cmdline):
                    return cmdline[i + 1]
    return None


def extract_node_name(proc: psutil.Process) -> str:
    """
    Derive a stable-ish node name for this process based on cmdline flags.

    For geth:
      geth-<ip from --nat=extip:IP or --p2p-host>

    For besu (java):
      besu-<ip from --p2p-host>
      or besu-<basename of --data-path>

    For nethermind:
      nethermind-<ip from --Network.ExternalIp>
      or nethermind-<basename of --datadir>

    Falls back to "<name>-<pid>".
    """
    try:
        name = (proc.name() or "").lower()
        cmd = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return f"unknown-{proc.pid}"

    client = name
    cmd_str_lower = " ".join(cmd).lower()
    if name == "java" and BESU_KEYWORD in cmd_str_lower:
        client = "besu"

    ip = None
    if client == "geth":
        ip = _get_flag_value(
            cmd,
            ["--nat=extip:", "--nat=", "--p2p-host=", "--p2p.host="],
        )
    elif client == "besu":
        ip = _get_flag_value(cmd, ["--p2p-host=", "--p2p-host"])
    elif client == "nethermind":
        ip = _get_flag_value(cmd, ["--Network.ExternalIp=", "--Network.ExternalIp"])

    if ip:
        return f"{client}-{ip}"

    path = None
    if client == "geth":
        path = _get_flag_value(cmd, ["--datadir=", "--datadir"])
    elif client == "besu":
        path = _get_flag_value(cmd, ["--data-path=", "--data-path"])
    elif client == "nethermind":
        path = _get_flag_value(cmd, ["--datadir=", "--datadir"])

    if path:
        base = path.rstrip("/").split("/")[-1]
        return f"{client}-{base}"

    return f"{client}-{proc.pid}"


def collect_process_metrics(proc: psutil.Process, prev_cpu_info, sample_time_monotonic):
    """
    Collect metrics for a single process and compute CPU % over the last interval.

    Returns dict with:
      node_name, cpu_usage_seconds, cpu_usage_percent,
      memory_usage_kb, memory_usage_percent
    """
    try:
        with proc.oneshot():
            pid = proc.pid
            cpu_times = proc.cpu_times()
            cpu_time_total = cpu_times.user + cpu_times.system
            mem_info = proc.memory_info()
            mem_percent = proc.memory_percent()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

    prev = prev_cpu_info.get(pid)
    if prev is not None:
        dt_wall = sample_time_monotonic - prev["timestamp"]
        d_cpu = cpu_time_total - prev["cpu_time"]
        if dt_wall > 0 and d_cpu >= 0:
            cpu_percent = (d_cpu / dt_wall) * 100.0
        else:
            cpu_percent = 0.0
    else:
        cpu_percent = 0.0

    prev_cpu_info[pid] = {
        "cpu_time": cpu_time_total,
        "timestamp": sample_time_monotonic,
    }

    node_name = extract_node_name(proc)

    cpu_time_total = round(cpu_time_total, 3)
    cpu_percent = round(cpu_percent, 1)
    mem_kb = int(mem_info.rss / 1024)
    mem_percent = round(mem_percent, 2)

    return {
        "node_name": node_name,
        "cpu_usage_seconds": cpu_time_total,
        "cpu_usage_percent": cpu_percent,
        "memory_usage_kb": mem_kb,
        "memory_usage_percent": mem_percent,
    }


def main(duration, base_interval, output_file):
    start_time = time.monotonic()
    prev_cpu_info = {}

    while True:
        loop_start = time.monotonic()

        if duration is not None:
            elapsed = loop_start - start_time
            remaining = duration - elapsed
            if remaining <= 0:
                break
            interval = min(base_interval, max(1, int(remaining)))
        else:
            interval = base_interval

        timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

        processes_data = []
        for proc in find_target_processes():
            data = collect_process_metrics(proc, prev_cpu_info, loop_start)
            if data is not None:
                processes_data.append(data)

        total_cpu_seconds = round(
            sum(p["cpu_usage_seconds"] for p in processes_data), 3
        )
        total_cpu_percent = round(
            sum(p["cpu_usage_percent"] for p in processes_data), 1
        )
        total_mem_kb = int(sum(p["memory_usage_kb"] for p in processes_data))
        total_mem_percent = round(
            sum(p["memory_usage_percent"] for p in processes_data), 2
        )

        record = {
            "timestamp": timestamp,
            "interval_seconds": interval,
            "processes": processes_data,
            "totals": {
                "cpu_usage_seconds": total_cpu_seconds,
                "cpu_usage_percent": total_cpu_percent,
                "memory_usage_kb": total_mem_kb,
                "memory_usage_percent": total_mem_percent,
            },
        }

        try:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record))
                f.write("\n")
        except OSError as e:
            print(f"Error writing to {output_file}: {e}")

        if duration is not None and (time.monotonic() - start_time) >= duration:
            break

        elapsed_this_loop = time.monotonic() - loop_start
        sleep_time = interval - elapsed_this_loop
        if sleep_time > 0:
            try:
                time.sleep(sleep_time)
            except KeyboardInterrupt:
                print("Interrupted by user, exiting...")
                break


if __name__ == "__main__":
    args = parse_args()
    main(duration=args.duration, base_interval=args.interval, output_file=args.output)
