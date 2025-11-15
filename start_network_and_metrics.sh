#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

WORKDIR="/home/trey-mosby/Project/eth-network"
ENCLAVE="eth-network"
PKG="github.com/Treymsby/ethereum-package"
ARGS_FILE="network_parameters_files/network_params.yaml"

# --- Configurable dstat params ---
DSTAT_INTERVAL="${DSTAT_INTERVAL:-1}"        # seconds between samples
DSTAT_DURATION="${DSTAT_DURATION:-800}"      # total seconds to run
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
    gnome-terminal -- bash -lc "$cmd; echo; echo '--- command finished ---'; echo 'You can close this window.'; exec bash"
  elif command -v x-terminal-emulator >/devnull 2>&1; then
    x-terminal-emulator -e bash -lc "$cmd; echo; echo '--- command finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  elif command -v konsole >/dev/null 2>&1; then
    konsole -e bash -lc "$cmd; echo; echo '--- command finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  elif command -v xterm >/dev/null 2>&1; then
    xterm -e bash -lc "$cmd; echo; echo '--- command finished ---'; read -n 1 -s -r -p 'Press any key to close...'"
  else
    info "No GUI terminal found; running in background: $cmd"
    nohup bash -lc "$cmd" > /tmp/import_spamoor_spammers.log 2>&1 &
  fi
}

trap 'echo -e "\nAborted by user."; exit 130' INT

# ============================================
# 0) Ask user for archive & import naming
# ============================================
CLIENT_OPTIONS=(
  "besu_lighthouse"
  "geth_lighthouse"
  "nethermind_lighthouse"
  "equalweight_mixed_el_lighthouse"
  "mainnet_mixed_el_lighthouse"
)

IMPORT_OPTIONS=(
  "bigblock"
  "highcompute"
  "highgas"
  "max-tx"
)

info "Option 1: Select client / network configuration (used for archive name)"
echo "  - besu_lighthouse"
echo "  - geth_lighthouse"
echo "  - nethermind_lighthouse"
echo "  - equalweight_mixed_el_lighthouse"
echo "  - mainnet_mixed_el_lighthouse"

select CLIENT_TYPE in "${CLIENT_OPTIONS[@]}"; do
  if [[ -n "${CLIENT_TYPE:-}" ]]; then
    info "Selected client configuration: ${CLIENT_TYPE}"
    break
  else
    echo "Invalid selection. Please choose a number from the list."
  fi
done

info "Option 2: Select import profile (used for archive name AND import script)"
echo "  - bigblock"
echo "  - highcompute"
echo "  - highgas"
echo "  - max-tx"

select IMPORT_TYPE in "${IMPORT_OPTIONS[@]}"; do
  if [[ -n "${IMPORT_TYPE:-}" ]]; then
    info "Selected import profile: ${IMPORT_TYPE}"
    break
  else
    echo "Invalid selection. Please choose a number from the list."
  fi
done

ARCHIVE_FOLDER_NAME="${CLIENT_TYPE}_${IMPORT_TYPE}"
info "Archive folder will be: archive/${ARCHIVE_FOLDER_NAME}"

# ============================================
# 1) Main network setup
# ============================================
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
run_cmd "python3 scripts/extract_container_setup.py"

# 5.5) Import spamoor spammers with chosen profile in an independent terminal
info "Starting import_spamoor_spammers.py in a separate terminal..."
open_in_new_terminal "cd '$WORKDIR' && python3 scripts/import_spamoor_spammers.py --import '${IMPORT_TYPE}'"

run_cmd "python3 scripts/open_web_ui.py"

# ============================================
# 2) Metric collection (inline metric_collect.sh)
# ============================================
info "Starting metric collection and monitoring..."

# Activate virtual environment
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: Could not find .venv/bin/activate in $(pwd)"
  exit 1
fi

echo ">>> Activating virtual environment: .venv"
# shellcheck disable=SC1091
source .venv/bin/activate

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: 'python' not found after activating the virtualenv."
  exit 1
fi

# PIDs of background monitoring scripts (so we can clean up)
monitor_pids=()

cleanup() {
  # Called on exit (success or error) to stop monitoring scripts if still running
  if ((${#monitor_pids[@]} > 0)); then
    echo
    echo ">>> Cleaning up background monitoring processes..."
    for pid in "${monitor_pids[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
      fi
    done
    # Wait for them to exit
    wait || true
  fi
}
trap cleanup EXIT

# Show each command as it runs (plus all program output)
set -x

# -------------------------------
# Start monitoring scripts in parallel (background)
python monitoring/python/live_collection/tx_metrics_ws.py --duration 800 &
monitor_pids+=($!)

python monitoring/python/live_collection/block_metrics_ws.py --duration 800 &
monitor_pids+=($!)

python monitoring/python/live_collection/mempool_metrics_ws.py --duration 800 &
monitor_pids+=($!)

python monitoring/python/live_collection/cpu_mem_net_colletion.py --duration 800 --interval 1 &
monitor_pids+=($!)

set +x
echo
echo ">>> Monitoring scripts started in background (PIDs: ${monitor_pids[*]})"
echo ">>> They will run for up to 800 seconds."
read -r -t 800 -p "Press Enter to stop monitoring early (auto-continues after 800s)... " || true
echo
set -x

# Stop monitoring scripts (if still running) and wait for them
for pid in "${monitor_pids[@]}"; do
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
  fi
done
wait || true
monitor_pids=()   # so cleanup trap doesn't try again

# 2) spamoor dashboard
python monitoring/python/api_calls/fetch_spamoor_dashboard.py

# 3) slots list
python monitoring/python/api_calls/fetch_slots_list.py

# 4) blocks [1..64]
python monitoring/python/api_calls/fetch_blocks.py --start 1 --end 64

# 5) slots [1..64]
python monitoring/python/api_calls/fetch_slots.py --start 1 --end 64

set +x
echo ">>> All monitoring & fetch tasks completed."

# Deactivate venv if available
type deactivate >/dev/null 2>&1 && deactivate || true

# ============================================
# 3) Optional Grafana data collection + stop network
# ============================================
echo
info "Take Screenshots from Spamoor!"
info "If you still need to collect data from Grafana, do that now."
read -r -p "Press Enter AFTER you have collected the data from Grafana to stop the Ethereum network (or Ctrl+C to keep it running): " _

run_cmd "scripts/stop_eth_network.sh"

# ============================================
# 4) Archive data at the end
# ============================================
info "Archiving data directory contents using name: ${ARCHIVE_FOLDER_NAME}"

archive_dir="archive/${ARCHIVE_FOLDER_NAME}"
data_dir="data"

# Ensure archive directory exists
mkdir -p "${archive_dir}"

if [[ -d "${data_dir}" ]]; then
  # Move ALL contents (including hidden files) from data/ into archive/<name>/
  shopt -s dotglob nullglob
  if compgen -G "${data_dir}/*" > /dev/null; then
    echo ">>> Archiving contents of ${data_dir}/ to ${archive_dir}/"
    mv "${data_dir}"/* "${archive_dir}/"
  else
    echo ">>> ${data_dir}/ is empty; nothing to archive."
  fi
  shopt -u dotglob nullglob
else
  echo ">>> ${data_dir}/ does not exist; creating it."
  mkdir -p "${data_dir}"
fi

echo ">>> Archive complete: ${archive_dir}"

info "All done."