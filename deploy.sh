#!/usr/bin/env bash

# Fail fast on errors, unset vars, and failed pipes
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$APP_DIR/packages.pip}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

choose_python() {
  if [[ -n "$PYTHON_BIN" && -x "$(command -v "$PYTHON_BIN")" ]]; then
    echo "$PYTHON_BIN"
    return
  fi

  local candidate
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done

  log "ERROR: No suitable python3 interpreter found."
  exit 1
}

ensure_venv() {
  local python_bin
  python_bin="$(choose_python)"

  if [[ ! -d "$VENV_PATH" ]]; then
    log "Creating virtual environment at $VENV_PATH"
    "$python_bin" -m venv "$VENV_PATH"
  elif [[ ! -f "$VENV_PATH/bin/activate" ]]; then
    if [[ -z "$VENV_PATH" || "$VENV_PATH" == "/" ]]; then
      log "ERROR: Refusing to recreate virtual environment; invalid VENV_PATH='$VENV_PATH'."
      exit 1
    fi
    log "Virtual environment at $VENV_PATH is incomplete; recreating."
    rm -rf "$VENV_PATH"
    "$python_bin" -m venv "$VENV_PATH"
  fi

  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
  log "Using Python interpreter: $(command -v python)"
}

install_dependencies() {
  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    log "No requirements file found at $REQUIREMENTS_FILE; skipping dependency install."
    return
  fi

  log "Upgrading pip in virtual environment"
  if ! python -m pip install --upgrade pip; then
    log "WARNING: Failed to upgrade pip; continuing with existing version."
  fi

  log "Installing dependencies from $REQUIREMENTS_FILE"
  python -m pip install -r "$REQUIREMENTS_FILE"

  if python -m pip show dotenv >/dev/null 2>&1; then
    log "Removing incompatible 'dotenv' package"
    if ! python -m pip uninstall -y dotenv; then
      log "WARNING: Failed to remove 'dotenv'; python-dotenv may still be shadowed."
    fi
  fi
}

restart_services() {
  if [[ -n "${SYSTEMD_SERVICE:-}" ]]; then
    if command -v systemctl >/dev/null 2>&1; then
      log "Restarting systemd service $SYSTEMD_SERVICE"
      systemctl restart "$SYSTEMD_SERVICE"
    else
      log "systemctl not found; cannot restart $SYSTEMD_SERVICE"
    fi
    return
  fi

  if [[ -n "${PM2_PROCESS:-}" ]]; then
    if command -v pm2 >/dev/null 2>&1; then
      if pm2 describe "$PM2_PROCESS" >/dev/null 2>&1; then
        log "Restarting pm2 process $PM2_PROCESS"
        pm2 restart "$PM2_PROCESS"
      else
        if [[ -n "${PM2_START_COMMAND:-}" ]]; then
          log "PM2 process $PM2_PROCESS not found; starting with PM2_START_COMMAND"
          eval "$PM2_START_COMMAND"
        else
          log "PM2 process $PM2_PROCESS not found and PM2_START_COMMAND not set; skipping."
        fi
      fi
    else
      log "pm2 not found; cannot restart $PM2_PROCESS"
    fi
    return
  fi

  if [[ -n "${SUPERVISOR_PROGRAM:-}" ]]; then
    if command -v supervisorctl >/dev/null 2>&1; then
      log "Restarting supervisor program $SUPERVISOR_PROGRAM"
      supervisorctl restart "$SUPERVISOR_PROGRAM"
    else
      log "supervisorctl not found; cannot restart $SUPERVISOR_PROGRAM"
    fi
    return
  fi

  if [[ -n "${RESTART_COMMAND:-}" ]]; then
    log "Running custom restart command"
    eval "$RESTART_COMMAND"
    return
  fi

  log "No restart command configured; leaving running processes untouched."
}

main() {
  cd "$APP_DIR"
  ensure_venv
  install_dependencies
  restart_services
  log "Deployment completed."
}

main "$@"
