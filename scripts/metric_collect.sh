#!/usr/bin/env bash
# run_eth_monitoring.sh
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
    mv ${data_dir}/* "${archive_dir}/"
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

# Show each command as it runs (plus all program output)
set -x

# 1) tx latency
python monitoring/python/tx_latency.py --count 120 --tps 0.1

# Pause and message before proceeding
set +x
echo
read -rp "Press Enter to continue... "
echo "Check block current block number = 100"
echo
set -x

# 2) spamoor dashboard
python monitoring/python/fetch_spamoor_dashboard.py

# 3) slots list
python monitoring/python/fetch_slots_list.py

# 4) blocks [10..110]
python monitoring/python/fetch_blocks.py --start 10 --end 110

# 5) slots [10..110]
python monitoring/python/fetch_slots.py --start 10 --end 110

# 6) block txs [1..110] at rps 0.1
python monitoring/python/fetch_block_txs.py --start 10 --end 110 --rps 0.1

set +x
echo ">>> All tasks completed."

# Deactivate venv if available
type deactivate >/dev/null 2>&1 && deactivate || true
