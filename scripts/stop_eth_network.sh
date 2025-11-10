#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"

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

# 1) Stop enclave
run_cmd "kurtosis enclave stop ${ENCLAVE}"

# 2) Remove enclave
run_cmd "kurtosis enclave rm ${ENCLAVE}"

# 3) Clean everything
run_cmd "kurtosis clean --all"

# 4) Restart engine
run_cmd "kurtosis engine restart"

# 5) Chmod 777 (its a vm so idk)
# Recursively give read, write, execute to everyone
run_cmd "chmod -R 777 ./"

info "All done."
info "Stopped"
