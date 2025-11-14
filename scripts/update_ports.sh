#!/usr/bin/env bash
# update_ports.sh
# Collect Kurtosis service URLs and write them to ../ports.json

set -u

NETWORK="eth-network"
PROTOCOL="http"
SERVICES=(blockscout blockscout-frontend dora spamoor prometheus grafana)

# Resolve output path to one directory above this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_FILE="${SCRIPT_DIR}/../ports.json"

#######################################
# Build JSON for generic services -> ports.json (HTTP)
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
