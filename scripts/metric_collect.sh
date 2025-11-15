#!/usr/bin/env bash
# metric_collect.sh
# Runs the monitoring scripts in order and shows all output in the terminal.

set -Eeuo pipefail

echo ">>> Changing directory to /home/trey-mosby/Project/eth-network"
cd /home/trey-mosby/Project/eth-network

# --- Archive existing data contents ---
timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
archive_dir="archive/${timestamp}"
data_dir="data"

# Ensure archive directory exists
mkdir -p "${archive_dir}"

if [[ -d "${data_dir}" ]]; then
  # Move ALL contents (including hidden files) from data/ into archive/<timestamp>/
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
python monitoring/python/fetch_spamoor_dashboard.py

# 3) slots list
python monitoring/python/fetch_slots_list.py

# 4) blocks [1..64]
python monitoring/python/fetch_blocks.py --start 1 --end 64

# 5) slots [1..64]
python monitoring/python/fetch_slots.py --start 1 --end 64

set +x
echo ">>> All tasks completed."

# Deactivate venv if available
type deactivate >/dev/null 2>&1 && deactivate || true
