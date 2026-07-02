#!/usr/bin/env bash
set -eo pipefail

PID_DIR="$HOME/ghost_logs/pids"
LOG_DIR="$HOME/ghost_logs/live"

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
check_one mh_monitor
check_one mh_web_dashboard

echo
echo "ROS topics:"
source /opt/ros/jazzy/setup.bash
ros2 topic list | grep ghost || true

echo
echo "Recent dashboard log:"
tail -8 "$LOG_DIR/mh_web_dashboard.log" 2>/dev/null || true
