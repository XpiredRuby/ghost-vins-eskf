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
      sleep 1.0
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

kill_stale() {
  echo "Cleaning stale GHOST processes and ports..."
  pkill -f "ghost_live_apriltag_pose_calibrated.py" 2>/dev/null || true
  pkill -f "ros2 run ghost_sim_ros2 mh_tracker" 2>/dev/null || true
  pkill -f "ros2 run ghost_sim_ros2 trial_recorder" 2>/dev/null || true
  pkill -f "ros2 run ghost_sim_ros2 mh_monitor" 2>/dev/null || true
  pkill -f "ros2 run ghost_sim_ros2 mh_web_dashboard" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8081/tcp 2>/dev/null || true
    fuser -k 8090/tcp 2>/dev/null || true
  fi
}

stop_one camera
stop_one mh_tracker
stop_one trial_recorder
stop_one mh_monitor
stop_one mh_web_dashboard
kill_stale

tmux kill-session -t ghost 2>/dev/null || true

echo "GHOST stopped."
