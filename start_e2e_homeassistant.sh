#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
E2E_VENV="$ROOT_DIR/.venv-e2e-ha"
HA_CONFIG_DIR="$ROOT_DIR/.e2e-homeassistant"
CUSTOM_COMPONENTS_DIR="$HA_CONFIG_DIR/custom_components"
HASS_BIN="$E2E_VENV/bin/hass"

find_running_ha_pids() {
  pgrep -f "$HASS_BIN -c $HA_CONFIG_DIR" || true
}

prompt_and_kill_running_ha() {
  local pids
  pids="$(find_running_ha_pids)"

  if [[ -z "$pids" ]]; then
    return 0
  fi

  echo "A Home Assistant E2E instance is already running for $HA_CONFIG_DIR."
  echo "Running PID(s): $(echo "$pids" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"

  if [[ ! -t 0 ]]; then
    echo "Refusing to kill the running instance without interactive confirmation."
    return 1
  fi

  local reply
  read -r -p "Kill the running instance and continue? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo "Aborted."
    return 1
  fi

  kill $pids

  for _ in {1..30}; do
    sleep 1
    if [[ -z "$(find_running_ha_pids)" ]]; then
      return 0
    fi
  done

  echo "Timed out waiting for the running Home Assistant instance to stop."
  return 1
}

if [[ ! -d "$E2E_VENV" ]]; then
  python3 -m venv "$E2E_VENV"
fi

"$E2E_VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$E2E_VENV/bin/python" -m pip install homeassistant >/dev/null

mkdir -p "$CUSTOM_COMPONENTS_DIR"
ln -sfn "$ROOT_DIR/custom_components/unipi" "$CUSTOM_COMPONENTS_DIR/unipi"

prompt_and_kill_running_ha

exec "$HASS_BIN" -c "$HA_CONFIG_DIR"
