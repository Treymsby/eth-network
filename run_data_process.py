#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional


def run_command(folder: Path, name: str, script: Path, args: List[str], required_inputs: List[Path]):
    """Run a processing command if all required input files exist."""
    missing = [p for p in required_inputs if not p.exists()]
    if missing:
        missing_names = ", ".join(m.name for m in missing)
        print(f"[SKIP] {name} for '{folder.name}': missing {missing_names}")
        return

    print(f"[RUN ] {name} for '{folder.name}'")
    try:
        # Always use the same Python interpreter that runs this script
        subprocess.run(
            [sys.executable, str(script), *args],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[ERR ] {name} for '{folder.name}' failed with code {e.returncode}")


def find_latest_matching_file(folder: Path, token: str) -> Optional[Path]:
    """
    Find the most recently modified file in `folder` whose name contains `token`.
    Returns None if no such file exists.
    """
    matches = [p for p in folder.iterdir() if p.is_file() and token in p.name]
    if not matches:
        return None
    # Pick the most recently modified file
    return max(matches, key=lambda p: p.stat().st_mtime)


def main():
    base_dir = Path(__file__).resolve().parent
    data_root = base_dir / "data"
    dp_root = base_dir / "data_processing"

    if not data_root.is_dir():
        print(f"Data directory not found: {data_root}")
        sys.exit(1)

    # Iterate over each subfolder inside data/
    for folder in sorted(p for p in data_root.iterdir() if p.is_dir()):
        print("=" * 60)
        print(f"Processing folder: {folder.relative_to(base_dir)}")
        print("=" * 60)

        # Paths to expected input JSON files
        block_metrics     = folder / "block_metrics.json"
        blocks_1_64       = folder / "blocks_1_64.json"
        client_metrics    = folder / "client_metrics.json"
        spamoor_dashboard = folder / "spamoor_dashboard.json"
        tx_metrics        = folder / "tx_metrics.json"

        # Find CSVs by substring in filename
        received_csv = find_latest_matching_file(
            folder, "network_node_bytes_total_received-data-as-joinbyfield"
        )
        transmit_csv = find_latest_matching_file(
            folder, "network_node_bytes_total_transmit-data-as-joinbyfield"
        )

        # Output directories (ensure they exist before calling the scripts)
        block_plots            = folder / "block_plots"
        block_plots2           = folder / "block_plots2"
        hardware_metrics_plots = folder / "hardware_metrics_plots"
        network_plots          = folder / "network_plots"
        mempool_plots          = folder / "mempool_plots"
        tx_charts              = folder / "tx_charts"

        for out_dir in [
            block_plots,
            block_plots2,
            hardware_metrics_plots,
            network_plots,
            mempool_plots,
            tx_charts,
        ]:
            out_dir.mkdir(parents=True, exist_ok=True)

        # 1) Block metrics grapher
        run_command(
            folder=folder,
            name="block_metrics_grapher",
            script=dp_root / "block_metrics_grapher.py",
            args=[
                "--input", str(block_metrics),
                "--output", str(block_plots),
                "--x-axis", "block",
            ],
            required_inputs=[block_metrics],
        )

        # 2) Plot blocks
        run_command(
            folder=folder,
            name="plot_blocks",
            script=dp_root / "plot_blocks.py",
            args=[
                "--input", str(blocks_1_64),
                "--output", str(block_plots2),
            ],
            required_inputs=[blocks_1_64],
        )

        # 3) Visualize hardware/client metrics
        run_command(
            folder=folder,
            name="visualize_metrics",
            script=dp_root / "visualize_metrics.py",
            args=[
                "--input", str(client_metrics),
                "--output", str(hardware_metrics_plots),
            ],
            required_inputs=[client_metrics],
        )

        # 4) Network traffic plots (two CSV inputs, searched by substring)
        if received_csv is None or transmit_csv is None:
            print(
                f"[SKIP] plot_network_traffic for '{folder.name}': "
                f"missing received or transmit CSV "
                f"(received={received_csv}, transmit={transmit_csv})"
            )
        else:
            run_command(
                folder=folder,
                name="plot_network_traffic",
                script=dp_root / "plot_network_traffic.py",
                args=[
                    "--input",
                    str(received_csv),
                    str(transmit_csv),
                    "--output",
                    str(network_plots),
                ],
                required_inputs=[received_csv, transmit_csv],
            )

        # 5) Mempool metrics grapher
        run_command(
            folder=folder,
            name="mempool_metrics_grapher",
            script=dp_root / "mempool_metrics_grapher.py",
            args=[
                "--input", str(spamoor_dashboard),
                "--output", str(mempool_plots),
            ],
            required_inputs=[spamoor_dashboard],
        )

        # 6) Visualize tx metrics
        run_command(
            folder=folder,
            name="visualize_tx_metrics",
            script=dp_root / "visualize_tx_metrics.py",
            args=[
                "--input", str(tx_metrics),
                "--output", str(tx_charts),
            ],
            required_inputs=[tx_metrics],
        )

        print(f"Done with folder: {folder.name}\n")

    print("All folders processed.")


if __name__ == "__main__":
    main()
