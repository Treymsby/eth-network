#!/usr/bin/env bash
# eth-network reset & redeploy with skippable waits

set -Eeuo pipefail

# --- Configuration ---
# You can override this at runtime:  SUDO_PASS='...' ./reset_eth_network.sh
SUDO_PASS="${SUDO_PASS:-djclimex0201}"

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"
PKG="github.com/ethpandaops/ethereum-package"
ARGS_FILE="network_parameters_files/network_geth_lighthouse.yaml"

# --- Helpers ---
info() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[skip]\033[0m %s\n" "$*"; }

wait_or_skip() {
  local seconds="$1"
  local label="${2:-"Waiting $seconds seconds. Press 's' to skip..."}"
  info "$label"
  for ((i=seconds; i>0; i--)); do
    printf "\r%2d seconds remaining... (press 's' to skip) " "$i"
    if read -t 1 -n 1 key 2>/dev/null; then
      if [[ "$key" == "s" || "$key" == "S" ]]; then
        printf "\n"
        warn "Wait skipped."
        return 0
      fi
    fi
  done
  printf "\n"
}

run_sudo() {
  local cmd="$1"
  info "Running: sudo $cmd"
  if [[ -n "${SUDO_PASS:-}" ]]; then
    # -S reads password from stdin; -E preserves PATH/environment
    printf '%s\n' "$SUDO_PASS" | sudo -SE bash -c "$cmd"
  else
    sudo -E bash -c "$cmd"
  fi
}

trap 'echo -e "\nAborted by user."; exit 130' INT

# --- Begin ---
info "Switching to working directory: $WORKDIR"
cd "$WORKDIR"

# Validate sudo early so later steps stream output without pausing for auth
if [[ -n "${SUDO_PASS:-}" ]]; then
  if ! printf '%s\n' "$SUDO_PASS" | sudo -S -v; then
    echo "sudo authentication failed. Check SUDO_PASS."
    exit 1
  fi
else
  sudo -v
fi

# Optional: show versions to confirm environment
if command -v kurtosis >/dev/null 2>&1; then
  info "Kurtosis version:"
  kurtosis version || true
fi

# 1) Stop enclave
run_sudo "kurtosis enclave stop ${ENCLAVE}"

# 2) Wait 60s (skippable)
wait_or_skip 60 "Waiting 60s before removing enclave. Press 's' to skip..."

# 3) Remove enclave
run_sudo "kurtosis enclave rm ${ENCLAVE}"

# 4) Wait 10s (skippable)
wait_or_skip 10 "Waiting 10s before restarting engine. Press 's' to skip..."

# 5) Restart engine
run_sudo "kurtosis engine restart"

# 6) Wait 30s (skippable)
wait_or_skip 30 "Waiting 30s before starting the network. Press 's' to skip..."

# 7) Run package
run_sudo "kurtosis run --enclave ${ENCLAVE} ${PKG} --args-file ${ARGS_FILE}"

info "All done."
