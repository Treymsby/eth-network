#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"
PKG="github.com/Treymsby/ethereum-package"
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
run_cmd "kurtosis clean --all"

# 2) Restart engine
run_cmd "kurtosis engine restart"

# 3) Run package
run_cmd "kurtosis run --enclave ${ENCLAVE} ${PKG} --args-file ${ARGS_FILE}"

# 4) Update ports.json and open web UIs
run_cmd "scripts/update_ports.sh"
run_cmd "python3 scripts/open_web_ui.py 
# 5) Chmod 777 (its a vm so idk)
# Recursively give read, write, execute to everyone
run_cmd "chmod -R 777 ./"

# 6) Run metric collection pythin scripts
run_cmd "./scripts/metric_collect.sh"

info "All done."
info "Started"