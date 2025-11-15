#!/usr/bin/env python3
"""
Collect metrics every SAMPLE_INTERVAL seconds for:
  - all geth / nethermind processes
  - java processes whose cmdline contains "besu"

Per process:
  - CPU Usage (seconds total since start)
  - CPU Usage % (over last interval)
  - Memory Usage (bytes, RSS)
  - Memory Usage %
  - Network Usage (Inbound / Outbound, kB/s from nethogs)

Totals (all those processes together):
  - CPU Usage (seconds)
  - CPU Usage %
  - Memory Usage (bytes)
  - Memory Usage %

Output:
  - one JSON object per line in client_metrics.jsonl

Requirements:
  - psutil (pip install psutil)
  - nethogs (sudo apt install nethogs)
  - run this script as root (sudo python3 metrics.py)
"""

import datetime as dt
import json
import socket
import subprocess

import psutil

# ========= CONFIG =========
SAMPLE_INTERVAL = 10  # seconds
OUTPUT_FILE = "client_metrics.jsonl"

TARGET_NAMES = {"geth", "nethermind"}
BESU_KEYWORD = "besu"  # for java-based Besu client (java cmdline contains "besu")
# ==========================


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


def parse_nethogs_output(output: str):
    """
    Parse `nethogs -t` output and return a dict:
        { pid: { "outbound_kb_per_s": float, "inbound_kb_per_s": float }, ... }

    nethogs columns (trace mode) are effectively:
        <process/command-with-/pid/uid>  <sent>  <recv>

    where <sent>, <recv> are in kB/s by default.
    """
    usage = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Skip non-data lines
        if (line.startswith("Refreshing:")
                or line.startswith("Adding local address")
                or line.startswith("Ethernet link detected")
                or line.startswith("Waiting for first packet")
                or line.startswith("Unknown connection")):
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        # Last two columns are sent and recv (kB/s)
        try:
            sent = float(parts[-2])  # outbound kB/s
            recv = float(parts[-1])  # inbound kB/s
        except ValueError:
            continue

        # Everything before that is "process field"
        proc_field = " ".join(parts[:-2])

        # Ignore generic "unknown" entries
        if proc_field.startswith("unknown"):
            continue

        # Extract PID from something like "/usr/bin/geth/1234/1000"
        # or "sshd: user@pts/0/8130/1000"
        path_parts = proc_field.split("/")
        pid = None
        uid = None

        for part in reversed(path_parts):
            if part.isdigit():
                if uid is None:
                    uid = part  # last numeric is usually UID
                elif pid is None:
                    pid = int(part)  # second last numeric is usually PID
                    break

        if pid is None:
            continue

        usage[pid] = {
            "outbound_kb_per_s": sent,
            "inbound_kb_per_s": recv,
        }

    return usage


def collect_network_usage():
    """
    Run nethogs in trace mode for SAMPLE_INTERVAL seconds and
    return per-PID network usage map.

    Uses:
        nethogs -t -d SAMPLE_INTERVAL -c 1
    """
    cmd = ["nethogs", "-t", "-d", str(SAMPLE_INTERVAL), "-c", "1"]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SAMPLE_INTERVAL + 15,
        )
    except FileNotFoundError:
        print("nethogs not found. Install it with: sudo apt install nethogs")
        return {}
    except Exception as e:
        print(f"Error running nethogs: {e}")
        return {}

    if result.returncode != 0 and result.stderr:
        print(f"nethogs exited with code {result.returncode}: {result.stderr.strip()}")

    return parse_nethogs_output(result.stdout)


def collect_process_metrics(proc: psutil.Process, net_map):
    """
    Collect metrics for a single process and attach per-PID network usage.
    """
    try:
        with proc.oneshot():
            pid = proc.pid
            name = proc.name()
            cmdline = proc.cmdline()

            # CPU
            cpu_percent = proc.cpu_percent(interval=None)  # % since last call
            cpu_times = proc.cpu_times()
            cpu_time_total = cpu_times.user + cpu_times.system

            # Memory
            mem_info = proc.memory_info()
            mem_percent = proc.memory_percent()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

    net_usage = net_map.get(pid, {
        "inbound_kb_per_s": None,
        "outbound_kb_per_s": None,
    })

    return {
        "pid": pid,
        "name": name,
        "cmdline": cmdline,
        "cpu_usage_seconds": cpu_time_total,
        "cpu_usage_percent": cpu_percent,
        "memory_usage_bytes": mem_info.rss,      # resident set size
        "memory_usage_percent": mem_percent,
        "network_usage": net_usage,
    }


def warm_up_cpu_percent():
    """
    Initial cpu_percent() calls to establish a baseline.
    """
    for proc in find_target_processes():
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def main():
    hostname = socket.gethostname()
    warm_up_cpu_percent()

    while True:
        # 1) Network usage over the last SAMPLE_INTERVAL seconds
        net_map = collect_network_usage()

        # 2) Timestamp at the moment we log
        timestamp = dt.datetime.utcnow().isoformat() + "Z"

        # 3) Per-process CPU & memory, plus attach network usage
        processes_data = []
        for proc in find_target_processes():
            data = collect_process_metrics(proc, net_map)
            if data is not None:
                processes_data.append(data)

        # 4) Totals across all tracked processes
        total_cpu_seconds = sum(p["cpu_usage_seconds"] for p in processes_data)
        total_cpu_percent = sum(p["cpu_usage_percent"] for p in processes_data)
        total_mem_bytes = sum(p["memory_usage_bytes"] for p in processes_data)
        total_mem_percent = sum(p["memory_usage_percent"] for p in processes_data)

        record = {
            "timestamp": timestamp,
            "hostname": hostname,
            "interval_seconds": SAMPLE_INTERVAL,
            "processes": processes_data,
            "totals": {
                "cpu_usage_seconds": total_cpu_seconds,
                "cpu_usage_percent": total_cpu_percent,
                "memory_usage_bytes": total_mem_bytes,
                "memory_usage_percent": total_mem_percent,
            },
        }

        try:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record))
                f.write("\n")
        except OSError as e:
            print(f"Error writing to {OUTPUT_FILE}: {e}")


if __name__ == "__main__":
    main()
