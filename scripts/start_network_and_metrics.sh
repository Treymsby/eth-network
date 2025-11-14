#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"
PKG="github.com/Treymsby/ethereum-package"
ARGS_FILE="network_parameters_files/network_params.yaml"

# --- Configurable dstat params ---
DSTAT_INTERVAL="${DSTAT_INTERVAL:-1}"        # seconds between samples
DSTAT_DURATION="${DSTAT_DURATION:-1000}"     # total seconds to run
DSTAT_OUTPUT="${DSTAT_OUTPUT:-data/system_usage.csv}"

# --- Helpers ---
info() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }

run_cmd() {
  local cmd="$1"
  info "Running: $cmd"
  bash -lc "$cmd"
}

open_in_new_terminal() {
  # Run the given command in a new terminal if possible; otherwise background it
  local cmd="$1"
  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal -- bash -lc "$cmd; echo; echo '--- dstat finished ---'; echo 'You can close this window.'; exec bash"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e bash -lc "$cmd; echo; echo '--- dstat finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  elif command -v konsole >/dev/null 2>&1; then
    konsole -e bash -lc "$cmd; echo; echo '--- dstat finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  elif command -v xterm >/dev/null 2>&1; then
    xterm -e bash -lc "$cmd; echo; echo '--- dstat finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  else
    info "No GUI terminal found; running in background: $cmd"
    nohup bash -lc "$cmd" > /tmp/dstat.log 2>&1 &
  fi
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
# 5) Chmod 777 (it's a VM)
run_cmd "chmod -R 777 ./"
run_cmd "python3 scripts/open_web_ui.py"

# Sleep 120sec
read -t 120s -p "Press Enter to contine (wait until slot 10) (auto in 120s): " || true
# 4.5) Start dstat in a new terminal for ${DSTAT_DURATION}s
mkdir -p "$(dirname "$DSTAT_OUTPUT")"
if command -v dstat >/dev/null 2>&1; then
  info "Starting dstat for ${DSTAT_DURATION}s -> ${DSTAT_OUTPUT}"
  open_in_new_terminal "dstat -cdngym --output '$DSTAT_OUTPUT' $DSTAT_INTERVAL $DSTAT_DURATION"
else
  info "dstat not found. Install it outside this script, e.g.: sudo apt-get update && sudo apt-get install -y dstat"
fi

# 5) Chmod 777 (it's a VM)
run_cmd "chmod -R 777 ./"

# 6) Run metric collection scripts
run_cmd "./scripts/metric_collect.sh"

info "All done."
