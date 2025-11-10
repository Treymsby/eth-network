#!/usr/bin/env bash
# update_ports.sh
# Collect Kurtosis service URLs and write them to ../ports.json
# Also collect EL/CL node RPC URLs and write them to ../rpc.json

set -u

NETWORK="eth-network"
PROTOCOL="http"
SERVICES=(blockscout blockscout-frontend dora spamoor prometheus grafana)

# EL/CL node names for RPC collection
NODES=(
  "el-1-geth-lighthouse"
  "el-1-nethermind-lighthouse"
  "el-1-geth-prysm"
  "el-1-nethermind-prysm"
)

# Resolve output paths to one directory above this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_FILE="${SCRIPT_DIR}/../ports.json"
RPC_OUT_FILE="${SCRIPT_DIR}/../rpc.json"

#######################################
# Build JSON for generic services -> ports.json
#######################################
entries=()

for svc in "${SERVICES[@]}"; do
  # Trim whitespace from stdout; on failure or empty output, write null
  if url="$(kurtosis port print "$NETWORK" "$svc" "$PROTOCOL" 2>/dev/null | tr -d '[:space:]')"; then
    if [[ -n "$url" ]]; then
      # escape any quotes just in case (not expected in URLs)
      url_escaped=${url//\"/\\\"}
      entries+=( "\"$svc\": \"$url_escaped\"" )
    else
      entries+=( "\"$svc\": null" )
    fi
  else
    entries+=( "\"$svc\": null" )
  fi
done

# Write ports.json atomically
tmp="$(mktemp)"
{
  printf "{\n"
  for i in "${!entries[@]}"; do
    [[ $i -gt 0 ]] && printf ",\n"
    printf "  %s" "${entries[$i]}"
  done
  printf "\n}\n"
} > "$tmp"

mv "$tmp" "$OUT_FILE"
echo "Wrote ${OUT_FILE}"

#######################################
# Build JSON for node RPC URLs -> rpc.json
#######################################
rpc_entries=()

for node in "${NODES[@]}"; do
  # As requested, call with port name 'rpc' (no protocol arg)
  if rpc_url="$(kurtosis port print "$NETWORK" "$node" rpc 2>/dev/null | tr -d '[:space:]')"; then
    if [[ -n "$rpc_url" ]]; then
      rpc_url_escaped=${rpc_url//\"/\\\"}
      rpc_entries+=( "\"$node\": \"$rpc_url_escaped\"" )
    else
      rpc_entries+=( "\"$node\": null" )
    fi
  else
    rpc_entries+=( "\"$node\": null" )
  fi
done

# Write rpc.json atomically (create if not present)
rpc_tmp="$(mktemp)"
{
  printf "{\n"
  for i in "${!rpc_entries[@]}"; do
    [[ $i -gt 0 ]] && printf ",\n"
    printf "  %s" "${rpc_entries[$i]}"
  done
  printf "\n}\n"
} > "$rpc_tmp"

mv "$rpc_tmp" "$RPC_OUT_FILE"
echo "Wrote ${RPC_OUT_FILE}"
