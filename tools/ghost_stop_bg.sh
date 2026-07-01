#!/usr/bin/env bash
set -euo pipefail

PID_DIR="$HOME/ghost_logs/pids"

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name pid=$pid"
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    else
      echo "$name not running"
    fi
    rm -f "$pid_file"
  else
    echo "$name pid file missing"
  fi
}

stop_one camera
stop_one mh_tracker
stop_one mh_monitor
stop_one mh_web_dashboard

tmux kill-session -t ghost 2>/dev/null || true

echo "GHOST stopped."
