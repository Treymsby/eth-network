#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"
PKG="github.com/Treymsby/ethereum-package"
# Changes this for every network
ARGS_FILE="network_parameters_files/network_params.yaml"

# --- Helpers ---
info() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }

run_cmd() {
  local cmd="$1"
  info "Running: $cmd"
  bash -c "$cmd"
}

trap 'echo -e "\nAborted by user."; exit 130' INT

# --- Begin ---
info "Switching to working directory: $WORKDIR"
cd "$WORKDIR"

# Optional: show Kurtosis version
if command -v kurtosis >/dev/null 2>&1; then
  info "Kurtosis version:"
  kurtosis version || true
fi

# 1) Clean everything
run_cmd "bash scripts/stop_eth_network.sh"

# 2) Restart engine
run_cmd "bash scripts/start_eth_network.sh"

info "All done."
info "Started"