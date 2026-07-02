#!/usr/bin/env bash
set -eo pipefail

PID_DIR="$HOME/ghost_logs/pids"
LOG_DIR="$HOME/ghost_logs/live"
TRIAL_DIR="$HOME/ghost_logs/trials"

check_one() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "OK   $name pid=$pid"
    else
      echo "DEAD $name pid=$pid"
      echo "--- last log: $LOG_DIR/${name}.log ---"
      tail -20 "$LOG_DIR/${name}.log" 2>/dev/null || true
    fi
  else
    echo "MISS $name no pid file"
  fi
}

check_one camera
check_one mh_tracker
check_one trial_recorder
check_one mh_monitor
check_one mh_web_dashboard

echo
echo "Listening ports 8081/8090:"
ss -ltnp 2>/dev/null | grep -E ':(8081|8090)\b' || echo "No 8081/8090 listeners found"

echo
echo "ROS topics:"
source /opt/ros/jazzy/setup.bash
ros2 topic list | grep ghost || true

echo
echo "Latest trial:"
latest="$(ls -td "$TRIAL_DIR"/* 2>/dev/null | head -1 || true)"
if [ -n "$latest" ]; then
  echo "$latest"
  if [ -f "$latest/summary.md" ]; then
    echo "--- summary.md ---"
    sed -n '1,80p' "$latest/summary.md"
  fi
else
  echo "No trial folders yet."
fi

echo
echo "Recent dashboard log:"
tail -8 "$LOG_DIR/mh_web_dashboard.log" 2>/dev/null || true

echo
echo "Recent trial recorder log:"
tail -8 "$LOG_DIR/trial_recorder.log" 2>/dev/null || true
