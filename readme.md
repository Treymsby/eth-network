# eth-network

Thesis project repo for spinning up a **local/private Ethereum network** and running **repeatable experiments** (e.g., load/spam scenarios) while collecting metrics for analysis.

This project uses **Kurtosis** to orchestrate an Ethereum testnet via `ethpandaops/ethereum-package`, plus supporting scripts for monitoring + data processing.

---

## What this repo is for

- Launch a configurable Ethereum network (client mix + parameters)
- Run controlled workloads (e.g., spam / high-tx-rate experiments) **only on a private network**
- Collect metrics/logs and turn them into datasets/plots for thesis analysis

---

## Repo layout

- `client_setups/` – client/network setup helpers (configs, notes, etc.)
- `network_parameters_files/` – Kurtosis/ethereum-package args files (YAML)
- `monitoring/` – monitoring stack/config (dashboards, scraping configs, etc.)
- `spammer_scripts/` – workload generators / tx spam tools (private net only)
- `data/` – raw captures + experiment outputs
- `data_processing/` – dataset cleanup + analysis scripts/notebooks
- `scripts/` – utility scripts for running experiments / automation
- `start_network_and_metrics.sh` – convenience entrypoint to start things

---

## Prerequisites

- Docker (running locally)
- Kurtosis installed + working (`kurtosis` available in your PATH)
- Python 3.x (for analysis tooling)
- Linux/macOS recommended (some commands use `sudo`)

---

## Quickstart

### 1) Start the Kurtosis engine (if needed)

```bash
sudo kurtosis engine restart
