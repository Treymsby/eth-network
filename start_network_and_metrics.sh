#!/usr/bin/env bash
# eth-network reset & redeploy (no waits, no sudo inside)

set -Eeuo pipefail

# ============================================
# Global configuration
# ============================================
WORKDIR="${WORKDIR:-/home/trey-mosby/Project/eth-network}"
ENCLAVE="${ENCLAVE:-eth-network}"
PKG="${PKG:-github.com/Treymsby/ethereum-package}"
ARGS_FILE="${ARGS_FILE:-network_parameters_files/network_params.yaml}"

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

# PIDs of background monitoring scripts (so we can clean up)
monitor_pids=()

# Will be set after user selection
ARCHIVE_FOLDER_NAME=""

# ============================================
# Helpers
# ============================================
info() {
  printf "\n\033[1;34m==> %s\033[0m\n" "$*"
}

error() {
  printf "\n\033[0;31m[ERROR] %s\033[0m\n" "$*" >&2
}

run_cmd() {
  info "Running: $*"
  bash -lc "$*"
}

open_in_new_terminal() {
  # Run the given command in a new terminal if possible; otherwise background it
  local cmd="$1"

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal -- bash -lc "$cmd; echo; echo '--- command finished ---'; echo 'You can close this window.'; exec bash"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
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

select_option() {
  # Usage: select_option "Prompt text" "${options[@]}"
  local prompt=$1
  shift
  local options=("$@")

  info "$prompt"
  local idx=1
  for opt in "${options[@]}"; do
    printf "  %2d) %s\n" "$idx" "$opt"
    ((idx++))
  done

  local selection
  while true; do
    read -rp "Select option [1-${#options[@]}]: " selection
    if [[ "$selection" =~ ^[0-9]+$ ]] && ((selection >= 1 && selection <= ${#options[@]})); then
      printf '%s\n' "${options[selection-1]}"
      return 0
    fi
    echo "Invalid selection. Please choose a number from the list."
  done
}

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
    for pid in "${monitor_pids[@]}"; do
      wait "${pid}" 2>/dev/null || true
    done
  fi
}

on_interrupt() {
  echo -e "\nAborted by user."
  exit 130
}

trap cleanup EXIT
trap on_interrupt INT

# ============================================
# Step 0: User selections
# ============================================
select_user_options() {
  local client_type import_type

  client_type=$(select_option \
    "Option 1: Select client / network configuration (used for archive name)" \
    "${CLIENT_OPTIONS[@]}")
  info "Selected client configuration: ${client_type}"

  import_type=$(select_option \
    "Option 2: Select import profile (used for archive name AND import script)" \
    "${IMPORT_OPTIONS[@]}")
  info "Selected import profile: ${import_type}"

  ARCHIVE_FOLDER_NAME="${client_type}_${import_type}"
  info "Archive folder will be: archive/${ARCHIVE_FOLDER_NAME}"

  # Export for reuse in called functions if needed
  CLIENT_TYPE="${client_type}"
  IMPORT_TYPE="${import_type}"
}

# ============================================
# Step 1: Main network setup
# ============================================
setup_network() {
  info "Switching to working directory: $WORKDIR"
  cd "$WORKDIR"

  # Optional: show Kurtosis version
  if command -v kurtosis >/dev/null 2>&1; then
    info "Kurtosis version:"
    kurtosis version || true
  fi

  info "Resetting Kurtosis environment..."
  run_cmd "kurtosis clean --all"
  run_cmd "kurtosis engine restart"

  info "Running Kurtosis package..."
  run_cmd "kurtosis run --enclave ${ENCLAVE} ${PKG} --args-file ${ARGS_FILE}"

  info "Updating ports.json and opening web UIs..."
  run_cmd "scripts/update_ports.sh"

  info "Setting broad permissions on working directory (VM environment)..."
  run_cmd "chmod -R 777 ./"

  info "Extracting container setup..."
  run_cmd "python3 scripts/extract_container_setup.py"

  info "Starting import_spamoor_spammers.py in a separate terminal..."
  open_in_new_terminal "cd '$WORKDIR' && python3 scripts/import_spamoor_spammers.py --import '${IMPORT_TYPE}'"
}

# ============================================
# Step 2: Metric collection
# ============================================
run_metric_collection() {
  info "Starting metric collection and monitoring..."

  if [[ ! -f ".venv/bin/activate" ]]; then
    error "Could not find .venv/bin/activate in $(pwd)"
    exit 1
  fi

  echo ">>> Activating virtual environment: .venv"
  # shellcheck disable=SC1091
  source .venv/bin/activate

  if ! command -v python >/dev/null 2>&1; then
    error "'python' not found after activating the virtualenv."
    exit 1
  fi

  # Start monitoring scripts in parallel (background)
  set -x

  python monitoring/python/live_collection/tx_metrics_ws.py --duration 950 &
  monitor_pids+=("$!")

  python monitoring/python/live_collection/block_metrics_ws.py --duration 900 &
  monitor_pids+=("$!")

  python monitoring/python/live_collection/cpu_mem_net_colletion.py --duration 800 --interval 1 &
  monitor_pids+=("$!")

  set +x

  echo
  echo ">>> Monitoring scripts started in background (PIDs: ${monitor_pids[*]})"
  echo ">>> They will run for up to 950 seconds (or until they exit on their own)."

  # Wait for monitoring scripts to finish on their own
  set -x
  if ((${#monitor_pids[@]} > 0)); then
    for pid in "${monitor_pids[@]}"; do
      wait "${pid}" || true
    done
  fi
  set +x
  monitor_pids=()   # so cleanup trap doesn't try again

  python monitoring/python/api_calls/fetch_spamoor_dashboard.py

  echo ">>> All monitoring & fetch tasks completed."

  # Deactivate venv if available
  type deactivate >/dev/null 2>&1 && deactivate || true
}

# ============================================
# Step 3: Grafana data + stop network
# ============================================
finalize_network() {
  sleep 60s
  run_cmd "kurtosis service stop eth-network spamoor"
}

# ============================================
# Step 4: Archive data
# ============================================
archive_data() {
  info "Archiving data directory contents using name: ${ARCHIVE_FOLDER_NAME}"

  local archive_dir="archive/${ARCHIVE_FOLDER_NAME}"
  local data_dir="data"

  mkdir -p "${archive_dir}"

  if [[ -d "${data_dir}" ]]; then
    # Move ALL contents (including hidden files) from data/ into archive/<name>/
    shopt -s dotglob nullglob
    if compgen -G "${data_dir}/*" >/dev/null; then
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
}

# ============================================
# Main
# ============================================
main() {
  select_user_options
  setup_network
  run_metric_collection
  finalize_network
  archive_data
}

main "$@"
