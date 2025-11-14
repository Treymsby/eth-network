#!/usr/bin/env python3
import subprocess
import json
import re
import sys
from typing import List, Dict, Any


def run_kurtosis_inspect(enclave_name: str = "eth-network") -> str:
    """
    Run `kurtosis enclave inspect <enclave_name> --full-uuids`
    and return the stdout as text.
    """
    cmd = ["kurtosis", "enclave", "inspect", enclave_name, "--full-uuids"]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def parse_user_services(output: str) -> List[Dict[str, Any]]:
    """
    Parse the 'User Services' section of the kurtosis inspect output.

    Returns a list of dicts:
        {
            "uuid": str,
            "name": str,
            "status": str,
            "ports": {
                "<alias>": "<dest>",
                ...
            }
        }
    """
    lines = output.splitlines()
    services: List[Dict[str, Any]] = []

    # Find the "User Services" section
    start_idx = None
    for i, line in enumerate(lines):
        if "User Services" in line:
            start_idx = i
            break

    if start_idx is None:
        return services  # no user services section found

    # Skip down to the "UUID  Name  Ports  Status" header line
    i = start_idx + 1
    while i < len(lines) and not lines[i].strip().startswith("UUID"):
        i += 1

    # Skip the header row itself
    i += 1

    # Regex for the first line of a service
    service_line_re = re.compile(
        r"^([0-9a-f]{32})\s+(.+?)\s{2,}(.+?)\s+([A-Z]+)\s*$"
    )

    # Regex to capture port mappings like:
    #   http: 3000/tcp -> http://127.0.0.1:3000
    #   rpc: 8545/tcp -> 127.0.0.1:33535
    port_re = re.compile(
        r"([A-Za-z0-9_-]+):\s+(\d+)/(tcp|udp)\s*->\s*(\S+)"
    )

    current = None

    while i < len(lines):
        line = lines[i]
        i += 1

        if not line.strip():
            # Blank line, just skip
            continue

        m = service_line_re.match(line)
        if m:
            # Starting a new service
            if current is not None:
                services.append(current)

            uuid, name, ports_chunk, status = m.groups()
            current = {
                "uuid": uuid.strip(),
                "name": name.strip(),
                "status": status.strip(),
                "ports": {}
            }

            for pm in port_re.finditer(ports_chunk):
                alias = pm.group(1).lower()
                dest = pm.group(4)
                current["ports"][alias] = dest

        else:
            # Continuation line for ports for the current service
            if current is None:
                continue

            for pm in port_re.finditer(line):
                alias = pm.group(1).lower()
                dest = pm.group(4)
                current["ports"][alias] = dest

    # Add the last service if present
    if current is not None:
        services.append(current)

    return services


def filter_relevant_services(services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Keep only:
      - el-* nodes (el_nodes)
      - grafana
      - prometheus
      - spamoor
      - blockscout-frontend
      - blockscout
      - dora

    And for each, keep Name, UUID, WS, RPC, HTTP.
    """
    wanted_names = {
        "grafana",
        "prometheus",
        "spamoor",
        "blockscout-frontend",
        "blockscout",
        "dora",
    }

    result = []
    for svc in services:
        name = svc["name"]
        uuid = svc["uuid"]
        ports = svc.get("ports", {})

        if name.startswith("el-") or name in wanted_names:
            result.append(
                {
                    "name": name,
                    "uuid": uuid,
                    "ws": ports.get("ws"),
                    "rpc": ports.get("rpc"),
                    "http": ports.get("http"),
                }
            )

    return result


def main():
    # Optional args:
    #   1: enclave name (default: eth-network)
    #   2: output json file (default: eth-network-services.json)
    enclave_name = sys.argv[1] if len(sys.argv) > 1 else "eth-network"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "eth-network-services.json"

    raw_output = run_kurtosis_inspect(enclave_name)
    services = parse_user_services(raw_output)
    filtered = filter_relevant_services(services)

    with open(output_file, "w") as f:
        json.dump(filtered, f, indent=2)

    print(f"Wrote {len(filtered)} service entries to {output_file}")


if __name__ == "__main__":
    main()
